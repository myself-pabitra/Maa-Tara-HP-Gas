from decimal import Decimal,InvalidOperation
import json
from django.shortcuts import redirect, render
from django.db import transaction
from employees.models import Employee
from inventory.models import ProductInventory
from .models import Cylender_information, DailyInvoice, DailyInvoiceExpense, DailyInvoiceLineItem, PredefinedExpense, SubDealerSKUDiscount, Subdealer
from django.contrib import messages
from django.utils import timezone
def CreateNewSubDealers(request):
    subDealer_name = request.POST.get("name")
    phone_number = request.POST.get("phone_number")
    address = request.POST.get("address")


    if subDealer_name and phone_number and address:
        subdealer = Subdealer(
            name=subDealer_name,
            phone_number=phone_number,
            address=address,
        )
        subdealer.save()
        messages.success(request, f"Subdealer '{subDealer_name}' created successfully!")
        return redirect("CreateNewSubDealers")

    return render(request,"SubDealers/Createnew_subdealers.html")



def addSubDealersProductDiscount(request):
    subdealer_code = request.GET.get("subdealer_code")
    product_id = request.GET.get("product_id")

    existing_discount = None
    if subdealer_code and product_id:
        existing_discount = SubDealerSKUDiscount.objects.filter(
            subdealer__subdealerCode=subdealer_code,
            product__id=product_id
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

        existing_discount = SubDealerSKUDiscount.objects.filter(subdealer=subdealer, product=product).first()
        if existing_discount:
            old_discount = existing_discount.product_discount
            existing_discount.product_discount = discount_amount
            existing_discount.save()
            messages.info(
                request,
                f"Discount updated for {subdealer.name} on {product.product_name}: {old_discount} to {discount_amount}"
            )
        else:
            SubDealerSKUDiscount.objects.create(
                subdealer=subdealer,
                product=product,
                product_discount=discount_amount
            )
            messages.success(request, f"New discount added for {subdealer.name} on {product.product_name} ({discount_amount})!")

        return redirect("view_subdealer_discounts")

    subdealers = Subdealer.objects.all()
    products = ProductInventory.objects.all()

    context = {
        "subdealers": subdealers,
        "products": products,
        "existing_discount": existing_discount
    }
    return render(request, "SubDealers/add_subdealer_product_discount.html", context)





def view_subdealer_discounts(request):
    subdealer_filter = request.GET.get("subdealer")
    product_filter = request.GET.get("product")

    discounts = SubDealerSKUDiscount.objects.select_related("subdealer", "product").all()

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
    }
    return render(request, "SubDealers/view_subdealer_discounts.html", context)



def create_invoice(request):
    subdealers = Subdealer.objects.all()
    products = ProductInventory.objects.all()
    employees = Employee.objects.all()

    # Predefined expenses
    predefined_expenses_qs = PredefinedExpense.objects.values_list('name', 'default_amount')
    predefined_expenses_dict = {name: float(amount) for name, amount in predefined_expenses_qs}
    predefined_expenses_json = json.dumps(predefined_expenses_dict)

    # Discounts map: {subdealer_code: {product_id: discount}}
    discounts_map = {}
    for d in SubDealerSKUDiscount.objects.select_related('subdealer', 'product').all():
        sub_code = d.subdealer.subdealerCode
        discounts_map.setdefault(sub_code, {})[str(d.product.id)] = float(d.product_discount or 0)
    discounts_map_json = json.dumps(discounts_map)

    if request.method == 'POST':
        try:
            with transaction.atomic():
                invoice_date_raw = request.POST.get('invoice_date')
                if not invoice_date_raw:
                    raise ValueError("Invoice date is required.")

                invoice = DailyInvoice.objects.create(
                    invoice_date=invoice_date_raw,
                    payment_mode='',  # will derive after line processing
                    notes=request.POST.get('notes', '')
                )

                # Assign employees
                employee_ids = request.POST.getlist('employee_ids')
                if employee_ids:
                    invoice.employees.set(employee_ids)

                # Line items arrays
                products_ids = request.POST.getlist('product_id[]')
                subdealers_codes = request.POST.getlist('subdealer_code[]')
                qtys = request.POST.getlist('quantity[]')
                submitted_list = request.POST.getlist('submitted_blank[]')
                discounted_prices = request.POST.getlist('discounted_price[]')
                line_totals = request.POST.getlist('line_total[]')
                due_cyls = request.POST.getlist('due_cyl[]')
                payment_modes = request.POST.getlist('payment_mode[]')
                cash_amounts = request.POST.getlist('cash_amount[]')
                ac_amounts = request.POST.getlist('ac_amount[]')

                # Basic length validation
                n = len(products_ids)
                if not (n and len(subdealers_codes) == n == len(qtys) == len(submitted_list) == len(discounted_prices) == len(line_totals) == len(due_cyls) == len(payment_modes) == len(cash_amounts) == len(ac_amounts)):
                    raise ValueError("Line items arrays are inconsistent in length.")

                subtotal = Decimal('0.00')
                total_other_expense = Decimal('0.00')
                modes_seen = set()

                for i in range(n):
                    prod_id = products_ids[i]
                    sub_code = subdealers_codes[i]
                    try:
                        product = ProductInventory.objects.get(id=prod_id)
                    except ProductInventory.DoesNotExist:
                        raise ValueError(f"Product id {prod_id} not found (row {i+1}).")
                    try:
                        subdealer = Subdealer.objects.get(subdealerCode=sub_code)
                    except Subdealer.DoesNotExist:
                        raise ValueError(f"Subdealer code {sub_code} not found (row {i+1}).")

                    try:
                        qty = int(float(qtys[i] or 0))
                    except Exception:
                        raise ValueError(f"Invalid quantity on row {i+1}.")
                    if qty < 0:
                        raise ValueError(f"Quantity must be >= 0 on row {i+1}.")

                    try:
                        submitted_blank = int(float(submitted_list[i] or 0))
                    except Exception:
                        raise ValueError(f"Invalid submitted value on row {i+1}.")
                    if submitted_blank < 0:
                        raise ValueError(f"Submitted cannot be negative (row {i+1}).")
                    if submitted_blank > qty:
                        raise ValueError(f"Submitted ({submitted_blank}) cannot exceed quantity ({qty}) (row {i+1}).")

                    try:
                        discounted_price = Decimal(discounted_prices[i] or '0')
                        line_total = Decimal(line_totals[i] or '0')
                    except InvalidOperation:
                        raise ValueError(f"Invalid price/line total on row {i+1}.")

                    try:
                        due_cyl = int(float(due_cyls[i] or 0))
                    except Exception:
                        due_cyl = 0

                    pmode = payment_modes[i] if payment_modes[i] else 'Cash'
                    pmode = pmode if pmode in ('Cash', 'Mixed', 'AC') else 'Cash'
                    modes_seen.add(pmode)

                    # parse cash/ac amounts
                    try:
                        cash_amt = Decimal(cash_amounts[i] or '0')
                        ac_amt = Decimal(ac_amounts[i] or '0')
                    except InvalidOperation:
                        raise ValueError(f"Invalid cash/ac amount on row {i+1}.")

                    # Validate payment arithmetic
                    if pmode == 'Cash':
                        if (cash_amt != line_total):
                            raise ValueError(f"Row {i+1}: For Cash mode, Cash amount must equal line total (₹{line_total}).")
                        ac_amt = Decimal('0.00')
                        payment_status = 'PAID'
                    elif pmode == 'AC':
                        if (ac_amt != line_total):
                            raise ValueError(f"Row {i+1}: For AC mode, AC amount must equal line total (₹{line_total}).")
                        cash_amt = Decimal('0.00')
                        payment_status = 'PENDING'
                    else:  # Mixed
                        if abs((cash_amt + ac_amt) - line_total) > Decimal('0.01'):
                            raise ValueError(f"Row {i+1}: For Mixed mode, Cash + AC must equal line total (₹{line_total}).")
                        # Mixed always requires verification of AC portion
                        payment_status = 'PENDING'

                    subtotal += line_total

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
                        payment_status=payment_status
                    )

                    # update or create cylinder info
                    cyl_info, created = Cylender_information.objects.get_or_create(
                        Subdealer=subdealer,
                        product=product,
                        defaults={'due_cylender_qty': due_cyl}
                    )
                    if not created:
                        cyl_info.due_cylender_qty = due_cyl
                        cyl_info.save()

                # Expenses parsing
                for key in request.POST:
                    if key.startswith('expense_type_'):
                        idx = key.split('_')[-1]
                        etype = request.POST.get(f'expense_type_{idx}')
                        if not etype:
                            continue
                        amount_raw = request.POST.get(f'expense_amount_{idx}', '0')
                        desc = request.POST.get(f'expense_desc_{idx}', '') or ''
                        try:
                            amount = Decimal(amount_raw or '0')
                        except InvalidOperation:
                            raise ValueError(f"Invalid expense amount for expense #{idx}")
                        if amount > 0:
                            DailyInvoiceExpense.objects.create(
                                invoice=invoice,
                                expense_name=(desc if etype == 'other' else etype),
                                expense_amount=amount
                            )
                            total_other_expense += amount

                # Determine invoice-level payment_mode (convenience only)
                if modes_seen == {'Cash'}:
                    invoice_mode = 'Cash'
                elif 'Mixed' in modes_seen:
                    invoice_mode = 'Mixed'
                elif modes_seen == {'AC'}:
                    invoice_mode = 'AC'
                else:
                    # e.g., mix of Cash & AC -> Mixed
                    invoice_mode = 'Mixed' if ('Mixed' in modes_seen or 'AC' in modes_seen) else 'Cash'

                invoice.payment_mode = invoice_mode
                invoice.subtotal = subtotal
                invoice.other_expense = total_other_expense
                invoice.grand_total = subtotal - total_other_expense
                invoice.save()

                messages.success(request, f'Invoice {invoice.invoice_number} created successfully!')
                return redirect('create_daily_sell_invoice')

        except Exception as exc:
            messages.error(request, f"Could not create invoice: {str(exc)}")
            context = {
                'subdealers': subdealers,
                'products': products,
                'employees': employees,
                'today': timezone.now(),
                'predefined_expenses_json': predefined_expenses_json,
                'discounts_map_json': discounts_map_json,
                'page_type': 'create_invoice',
            }
            return render(request, "billing/create_daily_sell_invoice.html", context)

    # GET
    context = {
        'subdealers': subdealers,
        'products': products,
        'employees': employees,
        'today': timezone.now(),
        'predefined_expenses_json': predefined_expenses_json,
        'discounts_map_json': discounts_map_json,
        'page_type': 'create_invoice',
    }
    return render(request, "billing/create_daily_sell_invoice.html", context)