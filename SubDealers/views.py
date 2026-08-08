import json
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO
from itertools import product

from django.contrib import messages
from django.conf import settings
from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.db.models.deletion import ProtectedError
from django.db.models.functions import ExtractMonth, ExtractYear
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.core.paginator import Paginator

from employees.models import Employee
from inventory.models import ProductInventory
from UserDAC.models import DACEntry

from .models import (
    Cylender_information,
    DailyInvoice,
    DailyInvoiceExpense,
    DailyInvoiceLineItem,
    PredefinedExpense,
    Subdealer,
    SubDealerSKUDiscount,
)


def CreateNewSubDealers(request):

    if request.method == "POST":
        subDealer_name = request.POST.get("name", "").strip()
        phone_number = request.POST.get("phone_number", "").strip()
        address = request.POST.get("address", "").strip()

        dac_percentage_raw = request.POST.get("dac_percentage", "100").strip()

        try:
            dac_percentage = Decimal(dac_percentage_raw)
        except InvalidOperation:
            dac_percentage = Decimal("100")

        # Address is optional
        if subDealer_name and phone_number:
            Subdealer.objects.create(
                name=subDealer_name,
                phone_number=phone_number,
                address=address,
                dac_percentage=dac_percentage,
            )

            messages.success(
                request, f"Subdealer '{subDealer_name}' created successfully!"
            )

            return redirect("CreateNewSubDealers")

        messages.error(request, "Subdealer Name and Phone Number are required.")

    return render(
        request,
        "SubDealers/Createnew_subdealers.html",
        {
            "page_type": "create_subdealer",
        },
    )

def view_subdealers(request):
    search = (request.GET.get("search") or request.GET.get("q") or "").strip()
    subdealers_qs = Subdealer.objects.all().order_by("name")

    if search:
        subdealers_qs = subdealers_qs.filter(
            Q(name__icontains=search)
            | Q(phone_number__icontains=search)
            | Q(address__icontains=search)
            | Q(subdealerCode__icontains=search)
        )

    paginator = Paginator(subdealers_qs, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(
        request,
        "SubDealers/view_subdealers.html",
        {
            "subdealers": page_obj,
            "page_obj": page_obj,
            "search": search,
            "total_subdealers": Subdealer.objects.count(),
            "filtered_count": subdealers_qs.count(),
            "page_type": "view_subdealers",
        },
    )


def edit_subdealer(request, subdealer_id):
    subdealer = get_object_or_404(Subdealer, pk=subdealer_id)

    if request.method == "POST":
        name = request.POST.get("name")
        phone_number = request.POST.get("phone_number")
        address = request.POST.get("address")
        dac_percentage_raw = request.POST.get("dac_percentage", "100")

        try:
            dac_percentage = Decimal(dac_percentage_raw)
        except InvalidOperation:
            dac_percentage = Decimal("100")

        if not name or not phone_number or not address:
            messages.error(request, "Please fill in all fields before saving.")
            return redirect("edit_subdealer", subdealer_id=subdealer.id)

        subdealer.name = name
        subdealer.phone_number = phone_number
        subdealer.address = address
        subdealer.dac_percentage = dac_percentage
        subdealer.save()

        messages.success(request, "Subdealer updated successfully.")
        return redirect("view_subdealers")

    return render(
        request,
        "SubDealers/edit_subdealer.html",
        {
            "subdealer": subdealer,
            "page_type": "edit_subdealer",
        },
    )


def delete_subdealer(request, subdealer_id):
    subdealer = get_object_or_404(Subdealer, pk=subdealer_id)

    if request.method == "POST":
        try:
            subdealer.delete()
            messages.success(request, "Subdealer deleted successfully.")
        except ProtectedError:
            messages.error(
                request,
                "Cannot delete this subdealer because it is linked to other records.",
            )
        return redirect("view_subdealers")

    messages.error(request, "Invalid delete request.")
    return redirect("view_subdealers")


def addSubDealersProductDiscount(request):
    subdealer_code = request.GET.get("subdealer_code")
    product_id = request.GET.get("product_id")

    existing_discount = None
    if subdealer_code and product_id:
        existing_discount = SubDealerSKUDiscount.objects.filter(
            subdealer__subdealerCode=subdealer_code, product__id=product_id
        ).first()

    if request.method == "POST":
        subdealer_code = request.POST.get("subdealer_code")
        product_id = request.POST.get("product_name")
        discount_amount = request.POST.get("discount_amount")

        if not subdealer_code or not product_id or not discount_amount:
            messages.error(request, "Please fill in all required fields.")
            return redirect("addSubDealersProductDiscount")

        subdealer = Subdealer.objects.get(subdealerCode=subdealer_code)
        product = ProductInventory.objects.get(id=product_id)

        existing_discount = SubDealerSKUDiscount.objects.filter(
            subdealer=subdealer, product=product
        ).first()
        if existing_discount:
            old_discount = existing_discount.product_discount
            existing_discount.product_discount = discount_amount
            existing_discount.save()
            messages.info(
                request,
                f"Discount updated for {subdealer.name} on {product.product_name}: {old_discount} to {discount_amount}",
            )
        else:
            SubDealerSKUDiscount.objects.create(
                subdealer=subdealer, product=product, product_discount=discount_amount
            )
            messages.success(
                request,
                f"New discount added for {subdealer.name} on {product.product_name} ({discount_amount})!",
            )

        return redirect("view_subdealer_discounts")

    subdealers = Subdealer.objects.all()
    products = ProductInventory.objects.all()

    context = {
        "subdealers": subdealers,
        "products": products,
        "existing_discount": existing_discount,
        "page_type": "add_discount",
    }
    return render(request, "SubDealers/add_subdealer_product_discount.html", context)


def view_subdealer_discounts(request):
    subdealer_filter = request.GET.get("subdealer")
    product_filter = request.GET.get("product")

    discounts = SubDealerSKUDiscount.objects.select_related(
        "subdealer", "product"
    ).all()

    if subdealer_filter:
        discounts = discounts.filter(subdealer__id=subdealer_filter)
    if product_filter:
        discounts = discounts.filter(product__id=product_filter)

    subdealers = Subdealer.objects.all()
    products = ProductInventory.objects.all()

    context = {
        "discounts": discounts,
        "subdealers": subdealers,
        "products": products,
        "selected_subdealer": subdealer_filter,
        "selected_product": product_filter,
        "page_type": "view_discount",
    }
    return render(request, "SubDealers/view_subdealer_discounts.html", context)


def create_invoice(request):
    subdealers = Subdealer.objects.all()
    products = ProductInventory.objects.filter(
        product_quantity__gt=0,
        in_stock=True,
    )
    employees = Employee.objects.all()

    # Predefined expenses
    predefined_expenses_qs = PredefinedExpense.objects.values_list(
        "name", "default_amount"
    )
    predefined_expenses_dict = {
        name: float(amount) for name, amount in predefined_expenses_qs
    }
    predefined_expenses_json = json.dumps(predefined_expenses_dict)

    # Discounts map: {subdealer_code: {product_code: discount}}
    discounts_map = {}
    for d in SubDealerSKUDiscount.objects.select_related("subdealer", "product").all():
        sub_code = d.subdealer.subdealerCode
        discounts_map.setdefault(sub_code, {})[d.product.productCode] = float(
            d.product_discount or 0
        )
    discounts_map_json = json.dumps(discounts_map)

    if request.method == "POST":
        try:
            with transaction.atomic():
                invoice_date_raw = request.POST.get("invoice_date")
                if not invoice_date_raw:
                    raise ValueError("Invoice date is required.")

                invoice = DailyInvoice.objects.create(
                    invoice_date=invoice_date_raw,
                    payment_mode="",  # will derive after line processing
                    notes="",
                )

                # Assign employees
                employee_ids = request.POST.getlist("employee_ids")
                if employee_ids:
                    invoice.employees.set(employee_ids)

                # Line items arrays
                product_codes = request.POST.getlist("product_code[]")
                subdealers_codes = request.POST.getlist("subdealer_code[]")
                qtys = request.POST.getlist("quantity[]")
                submitted_list = request.POST.getlist("submitted_blank[]")
                discounted_prices = request.POST.getlist("discounted_price[]")
                line_totals = request.POST.getlist("line_total[]")
                due_cyls = request.POST.getlist("due_cyl[]")
                payment_modes = request.POST.getlist("payment_mode[]")
                cash_amounts = request.POST.getlist("cash_amount[]")
                ac_amounts = request.POST.getlist("ac_amount[]")
                remarks_list = request.POST.getlist("remarks[]")
                buying_prices = request.POST.getlist("buying_price[]")

                # Basic length validation
                n = len(product_codes)
                if not (
                    n
                    and len(subdealers_codes)
                    == n
                    == len(qtys)
                    == len(submitted_list)
                    == len(discounted_prices)
                    == len(line_totals)
                    == len(due_cyls)
                    == len(payment_modes)
                    == len(cash_amounts)
                    == len(ac_amounts)
                    == len(remarks_list)
                    == len(buying_prices)
                ):
                    raise ValueError("Line items arrays are inconsistent in length.")

                subtotal = Decimal("0.00")
                total_other_expense = Decimal("0.00")
                modes_seen = set()

                for i in range(n):
                    product_code = product_codes[i]
                    sub_code = subdealers_codes[i]
                    is_other = product_code == "__other__"
                    product = None
                    remarks = remarks_list[i].strip()
                    if is_other:
                        if not remarks:
                            raise ValueError(f"Remarks are required for Other on row {i + 1}.")
                    else:
                        try:
                            product = ProductInventory.objects.select_for_update().get(
                                productCode=product_code
                            )
                        except ProductInventory.DoesNotExist:
                            raise ValueError(
                                f"Product '{product_code}' not found (row {i + 1})."
                            )
                    try:
                        subdealer = Subdealer.objects.get(subdealerCode=sub_code)
                    except Subdealer.DoesNotExist:
                        raise ValueError(
                            f"Subdealer code {sub_code} not found (row {i + 1})."
                        )

                    try:
                        qty = int(float(qtys[i] or 0))
                    except Exception:
                        raise ValueError(f"Invalid quantity on row {i + 1}.")
                    if qty < 0:
                        raise ValueError(f"Quantity must be >= 0 on row {i + 1}.")

                    try:
                        submitted_blank = int(float(submitted_list[i] or 0))
                    except Exception:
                        raise ValueError(f"Invalid submitted value on row {i + 1}.")
                    if submitted_blank < 0:
                        raise ValueError(f"Submitted cannot be negative (row {i + 1}).")

                    try:
                        discounted_price = Decimal(discounted_prices[i] or "0")
                        line_total = Decimal(line_totals[i] or "0")
                    except InvalidOperation:
                        raise ValueError(f"Invalid price/line total on row {i + 1}.")
                    if line_total < 0:
                        raise ValueError(f"Line total must be positive on row {i + 1}.")

                    if is_other:
                        try:
                            buying_price = Decimal(buying_prices[i] or "0")
                        except InvalidOperation:
                            raise ValueError(f"Invalid buying price on row {i + 1}.")
                        if buying_price < 0:
                            raise ValueError(f"Buying price cannot be negative on row {i + 1}.")
                        discounted_price = line_total
                    else:
                        buying_price = product.buy_price * qty
                        remarks = ""

                    try:
                        due_cyl = int(float(due_cyls[i] or 0))
                    except Exception:
                        due_cyl = 0

                    pmode = payment_modes[i] if payment_modes[i] else "Cash"
                    pmode = pmode if pmode in ("Cash", "Mixed", "AC") else "Cash"
                    modes_seen.add(pmode)

                    # parse cash/ac amounts
                    try:
                        cash_amt = Decimal(cash_amounts[i] or "0")
                        ac_amt = Decimal(ac_amounts[i] or "0")
                    except InvalidOperation:
                        raise ValueError(f"Invalid cash/ac amount on row {i + 1}.")

                    # Validate payment arithmetic
                    if pmode == "Cash":
                        ac_amt = Decimal("0.00")
                        if cash_amt != line_total:
                            raise ValueError(
                                f"Cash amount should equal line total on row {i + 1}."
                            )
                        payment_status = "PAID"
                    elif pmode == "AC":
                        if ac_amt != line_total:
                            raise ValueError(
                                f"AC amount must equal line total on row {i + 1}"
                            )
                        cash_amt = Decimal("0.00")
                        payment_status = "PENDING"
                    else:  # Mixed
                        if cash_amt + ac_amt != line_total:
                            raise ValueError(
                                f"Cash + AC amount mismatch on row {i + 1}"
                            )
                        if cash_amt > 0 and ac_amt == 0:
                            ac_amt = max(line_total - cash_amt, Decimal("0.00"))
                        elif ac_amt > 0 and cash_amt == 0:
                            cash_amt = max(line_total - ac_amt, Decimal("0.00"))
                        payment_status = "PENDING"

                    subtotal += line_total

                    if pmode == "Cash":
                        due_amount = Decimal("0.00")
                    elif pmode == "AC":
                        due_amount = ac_amt
                    else:  # Mixed
                        due_amount = ac_amt

                    # ----------------------------------------------------------
                    # Inventory Validation
                    # ----------------------------------------------------------

                    if product:
                        if product.product_quantity < qty:
                            raise ValueError(
                                f"Insufficient stock for {product.product_name} "
                                f"(Available: {product.product_quantity}, "
                                f"Requested: {qty})"
                            )
                        product.product_quantity -= qty
                        product.in_stock = product.product_quantity > 0
                        product.save(update_fields=["product_quantity", "in_stock"])

                    # create line item with per-line payment_status
                    DailyInvoiceLineItem.objects.create(
                        invoice=invoice,
                        subdealer=subdealer,
                        product=product,
                        is_other=is_other,
                        remarks=remarks,
                        quantity=qty,
                        submitted_blank=submitted_blank,
                        discounted_price=discounted_price,
                        line_total=line_total,
                        buying_price=buying_price,
                        due_cyl=due_cyl,
                        payment_mode=pmode,
                        cash_amount=cash_amt,
                        ac_amount=ac_amt,
                        verified_ac_amount=Decimal("0.00"),
                        due_amount=due_amount,
                        payment_status=payment_status,
                    )

                    # ----------------------------------------------------------
                    # Deduct DAC only for DAC applicable products
                    # ----------------------------------------------------------

                    if product and product.dac_applicable:
                        latest_entry = (
                            DACEntry.objects.filter(subdealer=subdealer)
                            .order_by("-entry_date", "-created_at")
                            .first()
                        )

                        opening_balance = (
                            latest_entry.closing_balance
                            if latest_entry
                            else Decimal("0.00")
                        )

                        closing_balance = opening_balance - Decimal(qty)

                        DACEntry.objects.create(
                            subdealer=subdealer,
                            entry_date=invoice.invoice_date,
                            transaction_type="DR",
                            transaction_quantity=Decimal(qty),
                            opening_balance=opening_balance,
                            closing_balance=closing_balance,
                            description=f"Invoice {invoice.invoice_number}",
                        )

                    # update or create cylinder info
                    if product:
                        cyl_info, created = Cylender_information.objects.get_or_create(
                            Subdealer=subdealer,
                            product=product,
                            defaults={"due_cylender_qty": due_cyl},
                        )
                        if not created:
                            cyl_info.due_cylender_qty += due_cyl
                            cyl_info.save()

                # Expenses parsing
                for key in request.POST:
                    if key.startswith("expense_type_"):
                        idx = key.split("_")[-1]
                        etype = request.POST.get(f"expense_type_{idx}")
                        if not etype:
                            continue
                        amount_raw = request.POST.get(f"expense_amount_{idx}", "0")
                        desc = request.POST.get(f"expense_desc_{idx}", "") or ""
                        try:
                            amount = Decimal(amount_raw or "0")
                        except InvalidOperation:
                            raise ValueError(
                                f"Invalid expense amount for expense #{idx}"
                            )
                        if amount > 0:
                            DailyInvoiceExpense.objects.create(
                                invoice=invoice,
                                expense_name=(desc if etype == "other" else etype),
                                expense_amount=amount,
                            )
                            total_other_expense += amount

                # Determine invoice-level payment_mode (convenience only)
                if modes_seen == {"Cash"}:
                    invoice_mode = "Cash"
                elif "Mixed" in modes_seen:
                    invoice_mode = "Mixed"
                elif modes_seen == {"AC"}:
                    invoice_mode = "AC"
                else:
                    # e.g., mix of Cash & AC -> Mixed
                    invoice_mode = (
                        "Mixed"
                        if ("Mixed" in modes_seen or "AC" in modes_seen)
                        else "Cash"
                    )

                invoice.payment_mode = invoice_mode
                invoice.subtotal = subtotal
                invoice.other_expense = total_other_expense
                invoice.grand_total = subtotal - total_other_expense
                invoice.save()

                messages.success(
                    request, f"Invoice {invoice.invoice_number} created successfully!"
                )
                return redirect("view_daily_sell_invoices")

        except Exception as exc:
            messages.error(request, f"Could not create invoice: {str(exc)}")
            context = {
                "subdealers": subdealers,
                "products": products,
                "employees": employees,
                "today": timezone.now(),
                "predefined_expenses_json": predefined_expenses_json,
                "discounts_map_json": discounts_map_json,
                "selected_employee_ids": [],
                "page_type": "create_invoice",
            }
            return render(request, "billing/create_daily_sell_invoice.html", context)

    # GET
    context = {
        "subdealers": subdealers,
        "products": products,
        "employees": employees,
        "today": timezone.now(),
        "predefined_expenses_json": predefined_expenses_json,
        "discounts_map_json": discounts_map_json,
        "selected_employee_ids": [],
        "page_type": "create_invoice",
    }
    return render(request, "billing/create_daily_sell_invoice.html", context)


def view_invoices(request):
    invoices_qs = DailyInvoice.objects.all().order_by("-invoice_date", "-invoice_number")
    paginator = Paginator(invoices_qs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(
        request,
        "billing/view_daily_sell_invoices.html",
        {
            "invoices": page_obj,
            "page_obj": page_obj,
            "page_type": "view_invoices",
        },
    )


def download_invoice_pdf(request, invoice_id):
    invoice = get_object_or_404(DailyInvoice, pk=invoice_id)
    buffer = BytesIO()

    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            SimpleDocTemplate,
            Table,
            TableStyle,
            Paragraph,
            Spacer,
            HRFlowable,
            Image as RLImage,
            KeepTogether,
        )
    except ImportError:
        messages.error(request, "PDF generation is not available. Please install reportlab.")
        return redirect("view_daily_sell_invoices")

    line_items = invoice.line_items.select_related("subdealer", "product")
    total_qty = line_items.aggregate(total_qty=Sum("quantity"))["total_qty"] or 0

    summary_items = []
    product_totals = {}
    for item in line_items:
        if item.due_cyl and item.due_cyl > 0:
            summary_items.append(
                {"text": f"{item.subdealer.name} : {item.display_name} {item.due_cyl} pis Due"}
            )
        elif item.submitted_blank > item.quantity:
            diff = item.submitted_blank - item.quantity
            summary_items.append(
                {"text": f"{item.subdealer.name} : {item.display_name} {diff} pis joma"}
            )

        product_name = item.display_name
        if product_name not in product_totals:
            product_totals[product_name] = {"quantity": 0, "submitted": 0}
        product_totals[product_name]["quantity"] += item.quantity
        product_totals[product_name]["submitted"] += item.submitted_blank

    product_totals_list = [
        {
            "product_name": name,
            "quantity": values["quantity"],
            "submitted": values["submitted"],
        }
        for name, values in product_totals.items()
    ]

    expense_summaries = [
        {
            "label": exp.expense_name,
            "amount": exp.expense_amount,
        }
        for exp in invoice.expenses.all()
    ]

    ac_summaries = [
        {
            "label": f"{item.subdealer.name} AC",
            "amount": item.ac_amount,
        }
        for item in line_items
        if item.ac_amount and item.ac_amount > 0
    ]

    total_ac_amount = sum(
        (item.ac_amount or Decimal("0.00")) for item in line_items
    )
    total_cash_collected = sum(
        (item.cash_amount or Decimal("0.00")) for item in line_items
    )
    total_cash_amount = total_cash_collected - invoice.other_expense

    # Document setup (A4 with 12mm margins)
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=12 * mm,
        leftMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=16 * mm,
        title=f"Invoice {invoice.invoice_number}",
    )
    page_w = A4[0] - 24 * mm  # usable width

    # Theme colors
    BRAND_BLUE = colors.HexColor("#1e3a5f")
    LIGHT_BLUE = colors.HexColor("#eff6ff")
    BORDER_COLOR = colors.HexColor("#e5e7eb")
    TEXT_DARK = colors.HexColor("#111827")
    TEXT_MUTED = colors.HexColor("#6b7280")
    AMBER_BG = colors.HexColor("#fffbeb")
    AMBER_BORDER = colors.HexColor("#fde68a")
    AMBER_TEXT = colors.HexColor("#b45309")
    ORANGE_BG = colors.HexColor("#fff7ed")
    ORANGE_BORDER = colors.HexColor("#fed7aa")
    ORANGE_TEXT = colors.HexColor("#c2410c")
    RED_TEXT = colors.HexColor("#dc2626")

    # Status / Badge text colors
    PAID_TEXT = colors.HexColor("#166534")
    PARTIAL_TEXT = colors.HexColor("#92400e")
    PENDING_TEXT = colors.HexColor("#991b1b")
    AC_TEXT = colors.HexColor("#92400e")
    CASH_TEXT = colors.HexColor("#166534")
    MIXED_TEXT = colors.HexColor("#1e40af")

    styles = getSampleStyleSheet()

    brand_title_style = ParagraphStyle(
        "BrandTitle",
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=17,
        textColor=BRAND_BLUE,
    )
    brand_sub_style = ParagraphStyle(
        "BrandSub",
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#d97706"),
    )
    brand_tag_style = ParagraphStyle(
        "BrandTag",
        fontName="Helvetica",
        fontSize=7.5,
        leading=9,
        textColor=TEXT_MUTED,
    )

    inv_title_style = ParagraphStyle(
        "InvTitle",
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=18,
        textColor=BRAND_BLUE,
        alignment=2,
    )
    inv_meta_label = ParagraphStyle(
        "InvMetaLabel",
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#374151"),
        alignment=2,
    )
    inv_meta_val = ParagraphStyle(
        "InvMetaVal",
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        textColor=TEXT_DARK,
        alignment=0,
    )

    section_hdr_style = ParagraphStyle(
        "SectionHdr",
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
        textColor=BRAND_BLUE,
        spaceAfter=3,
    )

    cell_style = ParagraphStyle(
        "CellLeft",
        fontName="Helvetica",
        fontSize=7.5,
        leading=9.5,
        textColor=TEXT_DARK,
    )
    cell_center = ParagraphStyle(
        "CellCenter",
        fontName="Helvetica",
        fontSize=7.5,
        leading=9.5,
        textColor=TEXT_DARK,
        alignment=1,
    )
    cell_right = ParagraphStyle(
        "CellRight",
        fontName="Helvetica",
        fontSize=7.5,
        leading=9.5,
        textColor=TEXT_DARK,
        alignment=2,
    )

    def th_cell(txt, align=0):
        return Paragraph(
            f"<b>{txt}</b>",
            ParagraphStyle(
                "TH",
                fontName="Helvetica-Bold",
                fontSize=7.5,
                leading=9.5,
                textColor=colors.white,
                alignment=align,
            ),
        )

    def badge_p(text, txt_color):
        return Paragraph(
            f"<b>{text}</b>",
            ParagraphStyle(
                "Badge",
                fontName="Helvetica-Bold",
                fontSize=6.5,
                leading=8,
                textColor=txt_color,
                alignment=1,
            ),
        )

    story = []

    # 1. Header (Brand + Invoice Meta)
    logo_path = settings.BASE_DIR / "static" / "images" / "maa-tara-hp-gas-logo.png"
    if logo_path.exists():
        logo = RLImage(str(logo_path), width=16 * mm, height=16 * mm)
    else:
        logo = Paragraph("", styles["Normal"])

    brand_text = [
        Paragraph("MAA TARA", brand_title_style),
        Spacer(1, 1),
        Paragraph("HP GAS", brand_sub_style),
        Spacer(1, 1),
        Paragraph("LPG Distribution · Reliable Energy, Every Day", brand_tag_style),
    ]

    brand_table = Table([[logo, brand_text]], colWidths=[18 * mm, None])
    brand_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    employees_list = [e.name for e in invoice.employees.all()]
    emp_str = ", ".join(employees_list) if employees_list else None

    meta_rows = [
        [Paragraph("TAX INVOICE", inv_title_style), ""],
        [Paragraph("Invoice No:", inv_meta_label), Paragraph(f"<b>{invoice.invoice_number}</b>", inv_meta_val)],
        [Paragraph("Date:", inv_meta_label), Paragraph(invoice.invoice_date.strftime("%d %b %Y") if hasattr(invoice.invoice_date, "strftime") else str(invoice.invoice_date), inv_meta_val)],
        [Paragraph("Payment Mode:", inv_meta_label), Paragraph(str(invoice.payment_mode or "—"), inv_meta_val)],
    ]
    if emp_str:
        meta_rows.append([
            Paragraph("Employees:", inv_meta_label),
            Paragraph(emp_str, inv_meta_val),
        ])

    meta_table = Table(meta_rows, colWidths=[28 * mm, 42 * mm])
    meta_table.setStyle(TableStyle([
        ("SPAN", (0, 0), (1, 0)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 1),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))

    top_table = Table(
        [[brand_table, meta_table]],
        colWidths=[page_w - 72 * mm, 72 * mm],
    )
    top_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(top_table)

    # Blue divider line
    story.append(HRFlowable(width="100%", thickness=1.5, color=BRAND_BLUE, spaceBefore=2, spaceAfter=4 * mm))

    # 2. Notes (if present)
    if invoice.notes:
        notes_content = [
            Paragraph("<b>Notes</b>", ParagraphStyle(
                "NotesHdr", fontName="Helvetica-Bold", fontSize=8, textColor=AMBER_TEXT, spaceAfter=1
            )),
            Paragraph(invoice.notes, ParagraphStyle(
                "NotesBody", fontName="Helvetica", fontSize=7.5, leading=9.5, textColor=TEXT_DARK
            )),
        ]
        notes_table = Table([[notes_content]], colWidths=[page_w])
        notes_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), AMBER_BG),
            ("BOX", (0, 0), (-1, -1), 0.5, AMBER_BORDER),
            ("ROUNDEDCORNERS", [3]),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(notes_table)
        story.append(Spacer(1, 3 * mm))

    # 3. Invoice Line Items Table
    story.append(Paragraph("INVOICE LINE ITEMS", section_hdr_style))

    col_w = [
        page_w * 0.15,   # Subdealer
        page_w * 0.18,   # Product
        page_w * 0.06,   # Qty
        page_w * 0.10,   # Submitted
        page_w * 0.08,   # Mode
        page_w * 0.11,   # Line Total
        page_w * 0.11,   # Cash
        page_w * 0.10,   # AC
        page_w * 0.11,   # Status
    ]

    items_data = [[
        th_cell("Subdealer", 0),
        th_cell("Product", 0),
        th_cell("Qty", 1),
        th_cell("Submitted", 1),
        th_cell("Mode", 1),
        th_cell("Line Total", 2),
        th_cell("Cash", 2),
        th_cell("AC", 2),
        th_cell("Status", 1),
    ]]

    all_lines = list(line_items)
    if all_lines:
        for item in all_lines:
            m = (item.payment_mode or "").strip()
            if m == "Cash":
                mode_el = badge_p("Cash", CASH_TEXT)
            elif m == "AC":
                mode_el = badge_p("AC", AC_TEXT)
            else:
                mode_el = badge_p(m or "—", MIXED_TEXT)

            st = (item.payment_status or "").strip()
            if st == "PAID":
                status_el = badge_p("PAID", PAID_TEXT)
            elif st == "PARTIAL":
                status_el = badge_p("PARTIAL", PARTIAL_TEXT)
            else:
                status_el = badge_p(st or "PENDING", PENDING_TEXT)

            items_data.append([
                Paragraph(item.subdealer.name if item.subdealer else "—", cell_style),
                Paragraph(item.display_name, cell_style),
                Paragraph(str(item.quantity), cell_center),
                Paragraph(str(item.submitted_blank), cell_center),
                mode_el,
                Paragraph(f"Rs.{item.line_total}", cell_right),
                Paragraph(f"Rs.{item.cash_amount}", cell_right),
                Paragraph(f"Rs.{item.ac_amount}", cell_right),
                status_el,
            ])
    else:
        items_data.append([
            Paragraph("No line items.", cell_center),
            "", "", "", "", "", "", "", ""
        ])

    items_table = Table(items_data, colWidths=col_w, repeatRows=1)
    items_style = [
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_BLUE),
        ("GRID", (0, 0), (-1, -1), 0.3, BORDER_COLOR),
        ("BOX", (0, 0), (-1, -1), 0.5, BRAND_BLUE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]
    if not all_lines:
        items_style.append(("SPAN", (0, 1), (-1, 1)))

    for i in range(1, len(items_data)):
        if i % 2 == 0:
            items_style.append(("BACKGROUND", (0, i), (-1, i), LIGHT_BLUE))

    items_table.setStyle(TableStyle(items_style))
    story.append(items_table)
    story.append(Spacer(1, 3.5 * mm))

    # 4. Expenses Table (if present)
    if expense_summaries:
        story.append(Paragraph("EXPENSES", section_hdr_style))
        exp_data = [[
            th_cell("Expense", 0),
            th_cell("Amount", 2),
        ]]
        for exp in expense_summaries:
            exp_data.append([
                Paragraph(exp["label"], cell_style),
                Paragraph(f"Rs.{exp['amount']}", cell_right),
            ])
        exp_table = Table(exp_data, colWidths=[page_w * 0.7, page_w * 0.3])
        exp_style = [
            ("BACKGROUND", (0, 0), (-1, 0), BRAND_BLUE),
            ("GRID", (0, 0), (-1, -1), 0.3, BORDER_COLOR),
            ("BOX", (0, 0), (-1, -1), 0.5, BRAND_BLUE),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]
        for i in range(1, len(exp_data)):
            if i % 2 == 0:
                exp_style.append(("BACKGROUND", (0, i), (-1, i), LIGHT_BLUE))
        exp_table.setStyle(TableStyle(exp_style))
        story.append(exp_table)
        story.append(Spacer(1, 3.5 * mm))

    # 5. Cylinder Notes (if present)
    if summary_items:
        cyl_notes_content = [
            Paragraph("<b>CYLINDER NOTES</b>", ParagraphStyle(
                "CylHdr", fontName="Helvetica-Bold", fontSize=8, textColor=ORANGE_TEXT, spaceAfter=2
            )),
        ]
        for s in summary_items:
            cyl_notes_content.append(
                Paragraph(f"• {s['text']}", ParagraphStyle(
                    "CylItem", fontName="Helvetica", fontSize=7.5, leading=9.5, textColor=TEXT_DARK
                ))
            )
        cyl_table = Table([[cyl_notes_content]], colWidths=[page_w])
        cyl_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), ORANGE_BG),
            ("BOX", (0, 0), (-1, -1), 0.5, ORANGE_BORDER),
            ("ROUNDEDCORNERS", [3]),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(cyl_table)
        story.append(Spacer(1, 3.5 * mm))

    # 6. Product Totals Table (if present)
    if product_totals_list:
        story.append(Paragraph("PRODUCT TOTALS", section_hdr_style))
        pt_data = [[
            th_cell("Product", 0),
            th_cell("Total Qty", 1),
            th_cell("Submitted", 1),
        ]]
        for pt in product_totals_list:
            pt_data.append([
                Paragraph(pt["product_name"], cell_style),
                Paragraph(f"<b>{pt['quantity']}</b>", cell_center),
                Paragraph(str(pt["submitted"]), cell_center),
            ])
        pt_table = Table(pt_data, colWidths=[page_w * 0.5, page_w * 0.25, page_w * 0.25])
        pt_style = [
            ("BACKGROUND", (0, 0), (-1, 0), BRAND_BLUE),
            ("GRID", (0, 0), (-1, -1), 0.3, BORDER_COLOR),
            ("BOX", (0, 0), (-1, -1), 0.5, BRAND_BLUE),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]
        for i in range(1, len(pt_data)):
            if i % 2 == 0:
                pt_style.append(("BACKGROUND", (0, i), (-1, i), LIGHT_BLUE))
        pt_table.setStyle(TableStyle(pt_style))
        story.append(pt_table)
        story.append(Spacer(1, 3.5 * mm))

    # 7. Totals Summary (Right aligned)
    tot_label = ParagraphStyle(
        "TotLabel", fontName="Helvetica", fontSize=8, textColor=TEXT_MUTED
    )
    tot_val = ParagraphStyle(
        "TotVal", fontName="Helvetica-Bold", fontSize=8, textColor=TEXT_DARK, alignment=2
    )
    tot_val_plain = ParagraphStyle(
        "TotValPlain", fontName="Helvetica", fontSize=8, textColor=TEXT_DARK, alignment=2
    )
    tot_val_red = ParagraphStyle(
        "TotValRed", fontName="Helvetica", fontSize=8, textColor=RED_TEXT, alignment=2
    )

    totals_rows = [
        [Paragraph("Total Quantity", tot_label), Paragraph(str(total_qty), tot_val)],
        [Paragraph("Subtotal", tot_label), Paragraph(f"Rs.{invoice.subtotal}", tot_val)],
        [Paragraph("Cash Collected", tot_label), Paragraph(f"Rs.{total_cash_collected}", tot_val_plain)],
    ]
    if ac_summaries or total_ac_amount > 0:
        totals_rows.append([
            Paragraph("Total AC Amount", tot_label),
            Paragraph(f"Rs.{total_ac_amount}", tot_val_plain),
        ])
    if expense_summaries or invoice.other_expense > 0:
        totals_rows.append([
            Paragraph("Other Expenses", tot_label),
            Paragraph(f"- Rs.{invoice.other_expense}", tot_val_red),
        ])
        totals_rows.append([
            Paragraph("Cash After Expenses", tot_label),
            Paragraph(f"Rs.{total_cash_amount}", tot_val),
        ])

    grand_total_label = Paragraph(
        "<b>Grand Total</b>",
        ParagraphStyle("GTLabel", fontName="Helvetica-Bold", fontSize=9.5, textColor=colors.white),
    )
    grand_total_val = Paragraph(
        f"<b>Rs.{invoice.grand_total}</b>",
        ParagraphStyle("GTVal", fontName="Helvetica-Bold", fontSize=9.5, textColor=colors.white, alignment=2),
    )
    totals_rows.append([grand_total_label, grand_total_val])

    totals_table = Table(totals_rows, colWidths=[40 * mm, 35 * mm])
    totals_table_style = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -2), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -2), 2.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, BORDER_COLOR),
        ("BACKGROUND", (0, -1), (-1, -1), BRAND_BLUE),
        ("TOPPADDING", (0, -1), (-1, -1), 4),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 4),
    ]
    totals_table.setStyle(TableStyle(totals_table_style))

    totals_container = Table(
        [[Spacer(page_w - 75 * mm, 1), totals_table]],
        colWidths=[page_w - 75 * mm, 75 * mm],
    )
    totals_container.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    story.append(KeepTogether(totals_container))

    # 8. Running Footer
    def draw_footer(canvas_obj, doc_obj):
        canvas_obj.saveState()
        canvas_obj.setFont("Helvetica", 7)
        canvas_obj.setFillColor(TEXT_MUTED)
        canvas_obj.drawString(12 * mm, 8 * mm, "Maa Tara HP Gas — LPG Distribution · Reliable Energy, Every Day")
        canvas_obj.drawRightString(
            A4[0] - 12 * mm, 8 * mm,
            f"Page {doc_obj.page} · Invoice {invoice.invoice_number}",
        )
        canvas_obj.restoreState()

    doc.build(story, onFirstPage=draw_footer, onLaterPages=draw_footer)
    buffer.seek(0)

    response = HttpResponse(buffer, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="invoice_{invoice.invoice_number}.pdf"'
    )
    return response



def print_invoice(request, invoice_id):
    invoice = get_object_or_404(DailyInvoice, pk=invoice_id)
    line_items = invoice.line_items.select_related("subdealer", "product")
    total_qty = line_items.aggregate(total_qty=Sum("quantity"))["total_qty"] or 0

    summary_items = []
    product_totals = {}
    for item in line_items:
        if item.due_cyl and item.due_cyl > 0:
            summary_items.append(
                {
                    "text": f"{item.subdealer.name} : {item.display_name} {item.due_cyl} pis Due"
                }
            )
        elif item.submitted_blank > item.quantity:
            diff = item.submitted_blank - item.quantity
            summary_items.append(
                {
                    "text": f"{item.subdealer.name} : {item.display_name} {diff} pis joma"
                }
            )

        product_name = item.display_name
        if product_name not in product_totals:
            product_totals[product_name] = {"quantity": 0, "submitted": 0}
        product_totals[product_name]["quantity"] += item.quantity
        product_totals[product_name]["submitted"] += item.submitted_blank

    product_totals_list = [
        {
            "product_name": name,
            "quantity": values["quantity"],
            "submitted": values["submitted"],
        }
        for name, values in product_totals.items()
    ]

    expense_summaries = [
        {
            "label": exp.expense_name,
            "amount": exp.expense_amount,
        }
        for exp in invoice.expenses.all()
    ]

    ac_summaries = [
        {
            "label": f"{item.subdealer.name} AC",
            "amount": item.ac_amount,
        }
        for item in line_items
        if item.ac_amount and item.ac_amount > 0
    ]

    total_ac_amount = sum(
        (item.ac_amount or Decimal("0.00")) for item in line_items
    )
    total_cash_collected = sum(
        (item.cash_amount or Decimal("0.00")) for item in line_items
    )
    # Expenses are paid from the cash collected for the day.  Showing this
    # separately prevents AC amounts from being subtracted from cash twice.
    total_cash_amount = total_cash_collected - invoice.other_expense

    return render(
        request,
        "billing/print_daily_sell_invoice.html",
        {
            "invoice": invoice,
            "total_qty": total_qty,
            "summary_items": summary_items,
            "product_totals": product_totals_list,
            "expense_summaries": expense_summaries,
            "ac_summaries": ac_summaries,
            "total_ac_amount": total_ac_amount,
            "total_cash_collected": total_cash_collected,
            "total_cash_amount": total_cash_amount,
            "page_type": "print_invoice",
        },
    )


def Cylender_Mismatch(request):

    subdealer = request.GET.get("subdealer")
    invoice = request.GET.get("invoice")

    queryset = (
        DailyInvoiceLineItem.objects.select_related(
            "invoice",
            "subdealer",
            "product",
        )
        .filter(
            Q(submitted_blank__lt=F("quantity")) | Q(submitted_blank__gt=F("quantity")),
            product__submission_required=True,
        )
        .order_by(
            "-invoice__invoice_date",
            "invoice__invoice_number",
        )
    )

    if subdealer:
        queryset = queryset.filter(subdealer__subdealerCode=subdealer)

    if invoice:
        queryset = queryset.filter(invoice__invoice_number__icontains=invoice)

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    mismatch_items = []

    total_difference = 0

    for item in page_obj:
        difference = item.quantity - item.submitted_blank

        total_difference += abs(difference)

        mismatch_items.append(
            {
                "invoice_number": item.invoice.invoice_number,
                "invoice_date": item.invoice.invoice_date,
                "subdealer": item.subdealer,
                "product": item.display_name,
                "quantity": item.quantity,
                "submitted_blank": item.submitted_blank,
                "difference": difference,
            }
        )

    total_subdealers = queryset.values("subdealer").distinct().count()

    context = {
        "mismatch_items": mismatch_items,
        "total_records": queryset.count(),
        "total_difference": total_difference,
        "subdealers": Subdealer.objects.all().order_by("name"),
        "selected_subdealer": subdealer,
        "invoice_search": invoice,
        "total_subdealers": total_subdealers,
        "page_obj": page_obj,
        "page_type": "cylinder_mismatch",
    }

    return render(
        request,
        "billing/Cylender_Mismatch.html",
        context,
    )


def print_mismatch_record(request, invoice_id):
    invoice = get_object_or_404(DailyInvoice, pk=invoice_id)
    mismatch_items = [
        {
            "item": item,
            "shortage": item.quantity - item.submitted_blank,
        }
        for item in invoice.line_items.all()
        if item.submitted_blank != item.quantity and item.product and item.product.submission_required
    ]
    return render(
        request,
        "billing/print_mismatch_record.html",
        {
            "invoice": invoice,
            "mismatch_items": mismatch_items,
            "page_type": "print_mismatch_record",
        },
    )


def edit_invoice(request, invoice_id):
    invoice = get_object_or_404(DailyInvoice, pk=invoice_id)
    subdealers = Subdealer.objects.all()
    products = ProductInventory.objects.all()
    employees = Employee.objects.all()

    predefined_expenses_qs = PredefinedExpense.objects.values_list(
        "name", "default_amount"
    )
    predefined_expenses_dict = {
        name: float(amount) for name, amount in predefined_expenses_qs
    }
    predefined_expenses_json = json.dumps(predefined_expenses_dict)

    discounts_map = {}
    for d in SubDealerSKUDiscount.objects.select_related("subdealer", "product").all():
        sub_code = d.subdealer.subdealerCode
        discounts_map.setdefault(sub_code, {})[d.product.productCode] = float(
            d.product_discount or 0
        )
    discounts_map_json = json.dumps(discounts_map)

    selected_employee_ids = list(invoice.employees.values_list("id", flat=True))
    line_items_data = [
        {
            "subdealer_code": item.subdealer.subdealerCode,
            "product_code": item.product.productCode if item.product else "",
            "is_other": item.is_other,
            "remarks": item.remarks,
            "quantity": item.quantity,
            "submitted_blank": item.submitted_blank,
            "discounted_price": str(item.discounted_price),
            "line_total": str(item.line_total),
            "buying_price": str(item.buying_price),
            "due_cyl": str(item.due_cyl),
            "payment_mode": item.payment_mode,
            "cash_amount": str(item.cash_amount),
            "ac_amount": str(item.ac_amount),
        }
        for item in invoice.line_items.all()
    ]

    expenses_data = []
    for exp in invoice.expenses.all():
        if exp.expense_name in predefined_expenses_dict:
            expenses_data.append(
                {
                    "expense_type": exp.expense_name,
                    "expense_desc": "",
                    "expense_amount": str(exp.expense_amount),
                }
            )
        else:
            expenses_data.append(
                {
                    "expense_type": "other",
                    "expense_desc": exp.expense_name,
                    "expense_amount": str(exp.expense_amount),
                }
            )

    if request.method == "POST":
        try:
            with transaction.atomic():
                invoice_date_raw = request.POST.get("invoice_date")
                if not invoice_date_raw:
                    raise ValueError("Invoice date is required.")

                invoice.invoice_date = invoice_date_raw
                invoice.save()

                employee_ids = request.POST.getlist("employee_ids")
                if employee_ids:
                    invoice.employees.set(employee_ids)
                else:
                    invoice.employees.clear()

                invoice.line_items.all().delete()
                invoice.expenses.all().delete()

                product_codes = request.POST.getlist("product_code[]")
                subdealers_codes = request.POST.getlist("subdealer_code[]")
                qtys = request.POST.getlist("quantity[]")
                submitted_list = request.POST.getlist("submitted_blank[]")
                discounted_prices = request.POST.getlist("discounted_price[]")
                line_totals = request.POST.getlist("line_total[]")
                due_cyls = request.POST.getlist("due_cyl[]")
                payment_modes = request.POST.getlist("payment_mode[]")
                cash_amounts = request.POST.getlist("cash_amount[]")
                ac_amounts = request.POST.getlist("ac_amount[]")
                remarks_list = request.POST.getlist("remarks[]")
                buying_prices = request.POST.getlist("buying_price[]")

                n = len(product_codes)
                if not (
                    n
                    and len(subdealers_codes)
                    == n
                    == len(qtys)
                    == len(submitted_list)
                    == len(discounted_prices)
                    == len(line_totals)
                    == len(due_cyls)
                    == len(payment_modes)
                    == len(cash_amounts)
                    == len(ac_amounts)
                    == len(remarks_list)
                    == len(buying_prices)
                ):
                    raise ValueError("Line items arrays are inconsistent in length.")

                subtotal = Decimal("0.00")
                total_other_expense = Decimal("0.00")
                modes_seen = set()

                for i in range(n):
                    product_code = product_codes[i]
                    sub_code = subdealers_codes[i]
                    is_other = product_code == "__other__"
                    product = None
                    remarks = remarks_list[i].strip()
                    if is_other:
                        if not remarks:
                            raise ValueError(f"Remarks are required for Other on row {i + 1}.")
                    else:
                        try:
                            product = ProductInventory.objects.get(productCode=product_code)
                        except ProductInventory.DoesNotExist:
                            raise ValueError(
                                f"Product '{product_code}' not found (row {i + 1})."
                            )
                    try:
                        subdealer = Subdealer.objects.get(subdealerCode=sub_code)
                    except Subdealer.DoesNotExist:
                        raise ValueError(
                            f"Subdealer code {sub_code} not found (row {i + 1})."
                        )

                    try:
                        qty = int(float(qtys[i] or 0))
                    except Exception:
                        raise ValueError(f"Invalid quantity on row {i + 1}.")
                    if qty < 0:
                        raise ValueError(f"Quantity must be >= 0 on row {i + 1}.")

                    try:
                        submitted_blank = int(float(submitted_list[i] or 0))
                    except Exception:
                        raise ValueError(f"Invalid submitted value on row {i + 1}.")
                    if submitted_blank < 0:
                        raise ValueError(f"Submitted cannot be negative (row {i + 1}).")

                    try:
                        discounted_price = Decimal(discounted_prices[i] or "0")
                        line_total = Decimal(line_totals[i] or "0")
                    except InvalidOperation:
                        raise ValueError(f"Invalid price/line total on row {i + 1}.")
                    if line_total < 0:
                        raise ValueError(f"Line total cannot be negative on row {i + 1}.")

                    if is_other:
                        try:
                            buying_price = Decimal(buying_prices[i] or "0")
                        except InvalidOperation:
                            raise ValueError(f"Invalid buying price on row {i + 1}.")
                        if buying_price < 0:
                            raise ValueError(f"Buying price cannot be negative on row {i + 1}.")
                        discounted_price = line_total
                    else:
                        buying_price = product.buy_price * qty
                        remarks = ""

                    try:
                        due_cyl = int(float(due_cyls[i] or 0))
                    except Exception:
                        due_cyl = 0

                    pmode = payment_modes[i] if payment_modes[i] else "Cash"
                    pmode = pmode if pmode in ("Cash", "Mixed", "AC") else "Cash"
                    modes_seen.add(pmode)

                    try:
                        cash_amt = Decimal(cash_amounts[i] or "0")
                        ac_amt = Decimal(ac_amounts[i] or "0")
                    except InvalidOperation:
                        raise ValueError(f"Invalid cash/ac amount on row {i + 1}.")

                    if pmode == "Cash":
                        ac_amt = Decimal("0.00")
                        payment_status = "PAID" if cash_amt == line_total else "PENDING"
                    elif pmode == "AC":
                        cash_amt = Decimal("0.00")
                        payment_status = "PENDING"
                    else:  # Mixed
                        payment_status = "PENDING"

                    if pmode == "Cash":
                        due_amount = Decimal("0.00")
                    elif pmode == "AC":
                        due_amount = ac_amt
                    else:  # Mixed
                        due_amount = ac_amt

                    subtotal += line_total

                    DailyInvoiceLineItem.objects.create(
                        invoice=invoice,
                        subdealer=subdealer,
                        product=product,
                        is_other=is_other,
                        remarks=remarks,
                        quantity=qty,
                        submitted_blank=submitted_blank,
                        discounted_price=discounted_price,
                        line_total=line_total,
                        buying_price=buying_price,
                        due_cyl=due_cyl,
                        payment_mode=pmode,
                        cash_amount=cash_amt,
                        ac_amount=ac_amt,
                        verified_ac_amount=Decimal("0.00"),
                        due_amount=due_amount,
                        payment_status=payment_status,
                    )

                    if product:
                        cyl_info, created = Cylender_information.objects.get_or_create(
                            Subdealer=subdealer,
                            product=product,
                            defaults={"due_cylender_qty": due_cyl},
                        )
                        if not created:
                            cyl_info.due_cylender_qty = due_cyl
                            cyl_info.save()

                for key in request.POST:
                    if key.startswith("expense_type_"):
                        idx = key.split("_")[-1]
                        etype = request.POST.get(f"expense_type_{idx}")
                        if not etype:
                            continue
                        amount_raw = request.POST.get(f"expense_amount_{idx}", "0")
                        desc = request.POST.get(f"expense_desc_{idx}", "") or ""
                        try:
                            amount = Decimal(amount_raw or "0")
                        except InvalidOperation:
                            raise ValueError(
                                f"Invalid expense amount for expense #{idx}"
                            )
                        if amount > 0:
                            DailyInvoiceExpense.objects.create(
                                invoice=invoice,
                                expense_name=(desc if etype == "other" else etype),
                                expense_amount=amount,
                            )
                            total_other_expense += amount

                if modes_seen == {"Cash"}:
                    invoice_mode = "Cash"
                elif "Mixed" in modes_seen:
                    invoice_mode = "Mixed"
                elif modes_seen == {"AC"}:
                    invoice_mode = "AC"
                else:
                    invoice_mode = (
                        "Mixed"
                        if ("Mixed" in modes_seen or "AC" in modes_seen)
                        else "Cash"
                    )

                invoice.payment_mode = invoice_mode
                invoice.subtotal = subtotal
                invoice.other_expense = total_other_expense
                invoice.grand_total = subtotal - total_other_expense
                invoice.save()

                messages.success(
                    request, f"Invoice {invoice.invoice_number} updated successfully!"
                )
                return redirect("view_daily_sell_invoices")

        except Exception as exc:
            messages.error(request, f"Could not update invoice: {str(exc)}")

    context = {
        "subdealers": subdealers,
        "products": products,
        "employees": employees,
        "invoice": invoice,
        "today": timezone.now(),
        "selected_employee_ids": selected_employee_ids,
        "invoice_json": json.dumps(
            {
                "invoice_number": invoice.invoice_number,
                "invoice_date": invoice.invoice_date.strftime("%Y-%m-%d"),
            }
        ),
        "line_items_json": json.dumps(line_items_data),
        "expenses_json": json.dumps(expenses_data),
        "predefined_expenses_json": predefined_expenses_json,
        "discounts_map_json": discounts_map_json,
        "page_type": "edit_invoice",
    }
    return render(request, "billing/create_daily_sell_invoice.html", context)
