import json
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO
from itertools import product

from django.contrib import messages
from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.db.models.deletion import ProtectedError
from django.db.models.functions import ExtractMonth, ExtractYear
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

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
    subdealers = Subdealer.objects.all().order_by("name")
    return render(
        request,
        "SubDealers/view_subdealers.html",
        {
            "subdealers": subdealers,
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

    # Discounts map: {subdealer_code: {product_id: discount}}
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
                ):
                    raise ValueError("Line items arrays are inconsistent in length.")

                subtotal = Decimal("0.00")
                total_other_expense = Decimal("0.00")
                modes_seen = set()

                for i in range(n):
                    product_code = product_codes[i]
                    sub_code = subdealers_codes[i]
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

                    if product.product_quantity < qty:
                        raise ValueError(
                            f"Insufficient stock for {product.product_name} "
                            f"(Available: {product.product_quantity}, "
                            f"Requested: {qty})"
                        )

                    # ----------------------------------------------------------
                    # Reduce Stock
                    # ----------------------------------------------------------

                    product.product_quantity -= qty

                    product.in_stock = product.product_quantity > 0

                    product.save(
                        update_fields=[
                            "product_quantity",
                            "in_stock",
                        ]
                    )

                    # create line item with per-line payment_status
                    DailyInvoiceLineItem.objects.create(
                        invoice=invoice,
                        subdealer=subdealer,
                        product=product,
                        quantity=qty,
                        submitted_blank=submitted_blank,
                        discounted_price=discounted_price,
                        line_total=line_total,
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

                    if product.dac_applicable:
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
    invoices = DailyInvoice.objects.all().order_by("-invoice_date", "-invoice_number")
    return render(
        request,
        "billing/view_daily_sell_invoices.html",
        {
            "invoices": invoices,
            "page_type": "view_invoices",
        },
    )


def download_invoice_pdf(request, invoice_id):
    invoice = get_object_or_404(DailyInvoice, pk=invoice_id)
    buffer = BytesIO()

    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.units import inch
        from reportlab.pdfgen import canvas
    except ImportError:
        messages.error(
            request, "PDF generation is not available. Please install reportlab."
        )
        return redirect("view_daily_sell_invoices")

    page_width, page_height = letter
    pdf = canvas.Canvas(buffer, pagesize=letter)
    x = 50
    y = page_height - 50

    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(x, y, "Invoice")
    pdf.setFont("Helvetica", 10)
    y -= 30
    pdf.drawString(x, y, f"Invoice No: {invoice.invoice_number}")
    pdf.drawString(x + 300, y, f"Date: {invoice.invoice_date.strftime('%Y-%m-%d')}")
    y -= 18
    pdf.drawString(x, y, f"Payment Mode: {invoice.payment_mode}")
    y -= 18
    pdf.drawString(x, y, f"Subtotal: {invoice.subtotal}")
    pdf.drawString(x + 300, y, f"Expenses: {invoice.other_expense}")
    y -= 18
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(x, y, f"Grand Total: {invoice.grand_total}")
    pdf.drawString(
        x + 300,
        y,
        f"Total Quantity: {invoice.line_items.aggregate(total_qty=Sum('quantity'))['total_qty'] or 0}",
    )

    y -= 30
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(x, y, "Subdealer")
    pdf.drawString(x + 120, y, "Product")
    pdf.drawString(x + 260, y, "Qty")
    pdf.drawString(x + 310, y, "Line Total")
    pdf.drawString(x + 370, y, "AC Amount")
    pdf.drawString(x + 420, y, "Cash Amount")
    y -= 14
    pdf.line(x, y, page_width - x, y)
    y -= 14
    pdf.setFont("Helvetica", 10)

    for item in invoice.line_items.all():
        if y < 100:
            pdf.showPage()
            y = page_height - 50
            pdf.setFont("Helvetica-Bold", 10)
            pdf.drawString(x, y, "Subdealer")
            pdf.drawString(x + 120, y, "Product")
            pdf.drawString(x + 260, y, "Qty")
            pdf.drawString(x + 310, y, "Line Total")
            pdf.drawString(x + 370, y, "AC Amount")
            pdf.drawString(x + 420, y, "Cash Amount")
            y -= 20
            pdf.setFont("Helvetica", 10)

        pdf.drawString(x, y, item.subdealer.name if item.subdealer else "")
        pdf.drawString(x + 120, y, item.product.product_name if item.product else "")
        pdf.drawString(x + 260, y, str(item.quantity))
        pdf.drawString(x + 310, y, f"{item.line_total}")
        pdf.drawString(x + 370, y, f"{item.ac_amount}")
        pdf.drawString(x + 420, y, f"{item.cash_amount}")
        y -= 16

    if invoice.expenses.exists():
        y -= 10
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(x, y, "Expenses")
        y -= 18
        pdf.setFont("Helvetica", 10)
        for exp in invoice.expenses.all():
            if y < 100:
                pdf.showPage()
                y = page_height - 50
                pdf.setFont("Helvetica", 10)
            pdf.drawString(x, y, f"{exp.expense_name}: {exp.expense_amount}")
            y -= 14

    pdf.save()
    buffer.seek(0)

    response = HttpResponse(buffer, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="invoice_{invoice.invoice_number}.pdf"'
    )
    return response


def print_invoice(request, invoice_id):
    invoice = get_object_or_404(DailyInvoice, pk=invoice_id)
    total_qty = (
        invoice.line_items.aggregate(total_qty=Sum("quantity"))["total_qty"] or 0
    )

    summary_items = []
    product_totals = {}
    for item in invoice.line_items.all():
        if item.due_cyl and item.due_cyl > 0:
            summary_items.append(
                {
                    "text": f"{item.subdealer.name} : {item.product.product_name} {item.due_cyl} pis Due"
                }
            )
        elif item.submitted_blank > item.quantity:
            diff = item.submitted_blank - item.quantity
            summary_items.append(
                {
                    "text": f"{item.subdealer.name} : {item.product.product_name} {diff} pis joma"
                }
            )

        product_name = item.product.product_name if item.product else "Unknown"
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
        for item in invoice.line_items.all()
        if item.ac_amount and item.ac_amount > 0
    ]

    total_ac_amount = sum(item.ac_amount for item in invoice.line_items.all())
    total_cash_amount = invoice.grand_total - total_ac_amount

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
            Q(submitted_blank__lt=F("quantity")) | Q(submitted_blank__gt=F("quantity"))
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

    mismatch_items = []

    total_difference = 0

    for item in queryset:
        difference = item.quantity - item.submitted_blank

        total_difference += abs(difference)

        mismatch_items.append(
            {
                "invoice_number": item.invoice.invoice_number,
                "invoice_date": item.invoice.invoice_date,
                "subdealer": item.subdealer,
                "product": item.product.product_name,
                "quantity": item.quantity,
                "submitted_blank": item.submitted_blank,
                "difference": difference,
            }
        )

    total_subdealers = queryset.values("subdealer").distinct().count()

    context = {
        "mismatch_items": mismatch_items,
        "total_records": len(mismatch_items),
        "total_difference": total_difference,
        "subdealers": Subdealer.objects.all().order_by("name"),
        "selected_subdealer": subdealer,
        "invoice_search": invoice,
        "total_subdealers": total_subdealers,
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
        if item.submitted_blank != item.quantity
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
        discounts_map.setdefault(sub_code, {})[str(d.product.id)] = float(
            d.product_discount or 0
        )
    discounts_map_json = json.dumps(discounts_map)

    selected_employee_ids = list(invoice.employees.values_list("id", flat=True))
    line_items_data = [
        {
            "subdealer_code": item.subdealer.subdealerCode,
            "product_id": str(item.product.id),
            "quantity": item.quantity,
            "submitted_blank": item.submitted_blank,
            "discounted_price": str(item.discounted_price),
            "line_total": str(item.line_total),
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

                products_ids = request.POST.getlist("product_id[]")
                subdealers_codes = request.POST.getlist("subdealer_code[]")
                qtys = request.POST.getlist("quantity[]")
                submitted_list = request.POST.getlist("submitted_blank[]")
                discounted_prices = request.POST.getlist("discounted_price[]")
                line_totals = request.POST.getlist("line_total[]")
                due_cyls = request.POST.getlist("due_cyl[]")
                payment_modes = request.POST.getlist("payment_mode[]")
                cash_amounts = request.POST.getlist("cash_amount[]")
                ac_amounts = request.POST.getlist("ac_amount[]")

                n = len(products_ids)
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
                ):
                    raise ValueError("Line items arrays are inconsistent in length.")

                subtotal = Decimal("0.00")
                total_other_expense = Decimal("0.00")
                modes_seen = set()

                for i in range(n):
                    prod_id = products_ids[i]
                    sub_code = subdealers_codes[i]
                    try:
                        product = ProductInventory.objects.get(id=prod_id)
                    except ProductInventory.DoesNotExist:
                        raise ValueError(
                            f"Product id {prod_id} not found (row {i + 1})."
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

                    subtotal += line_total

                    DailyInvoiceLineItem.objects.create(
                        invoice=invoice,
                        subdealer=subdealer,
                        product=product,
                        quantity=qty,
                        submitted_blank=submitted_blank,
                        discounted_price=discounted_price,
                        line_total=line_total,
                        due_cyl=due_cyl,
                        payment_mode=pmode,
                        cash_amount=cash_amt,
                        ac_amount=ac_amt,
                        payment_status=payment_status,
                    )

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
