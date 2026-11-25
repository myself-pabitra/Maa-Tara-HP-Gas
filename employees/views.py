from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import IntegrityError
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.core.paginator import Paginator
from django.utils import timezone
from django.utils.dateparse import parse_date

from SubDealers.models import PredefinedExpense

from .models import Employee, OperationalExpense


def add_new_employees(request):
    if request.method == "POST":
        employee_name = request.POST.get("employee_name", "").strip()
        employee_phone = request.POST.get("phone", "").strip()
        employee_address = request.POST.get("address", "").strip()

        # Validation
        if not employee_name or not employee_phone or not employee_address:
            messages.error(request, "Please fill in all required fields.")
            return redirect("add_new_employees")

        # Save employee
        Employee.objects.create(
            name=employee_name, phone=employee_phone, address=employee_address
        )
        messages.success(request, f"Employee '{employee_name}' created successfully!")
        return redirect("add_new_employees")

    # GET request
    recent_employees = Employee.objects.all().order_by("-id")[:5]
    total_employees = Employee.objects.count()
    context = {
        "recent_employees": recent_employees,
        "total_employees": total_employees,
        "page_type": "add_new_employees",
    }
    return render(request, "employees/add_new_employees.html", context)


def view_employees(request):
    search = request.GET.get("search", "").strip()

    all_employees = Employee.objects.all()
    total_employees = all_employees.count()
    active_employees = all_employees.filter(is_active=True).count()
    inactive_employees = all_employees.filter(is_active=False).count()

    employees = all_employees.order_by("name")

    if search:
        employees = employees.filter(
            Q(name__icontains=search)
            | Q(phone__icontains=search)
            | Q(address__icontains=search)
            | Q(employeeCode__icontains=search)
        )

    filtered_count = employees.count()

    paginator = Paginator(employees, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        "employees": page_obj,
        "page_obj": page_obj,
        "total_employees": total_employees,
        "active_employees": active_employees,
        "inactive_employees": inactive_employees,
        "filtered_count": filtered_count,
        "search": search,
        "page_type": "view_employees",
    }

    return render(
        request,
        "employees/view_employees.html",
        context,
    )


def delete_employee(request, employee_id):

    employee = get_object_or_404(
        Employee,
        id=employee_id,
    )

    if request.method == "POST":
        employee.delete()

        messages.success(
            request,
            "Employee deleted successfully.",
        )

    return redirect("view_employees")


def edit_employee(request, employee_code):

    employee = get_object_or_404(
        Employee,
        employeeCode=employee_code,
    )

    if request.method == "POST":
        employee.name = request.POST.get("employee_name")
        employee.phone = request.POST.get("phone")
        employee.address = request.POST.get("address")
        employee.is_active = request.POST.get("is_active") == "on"

        employee.save()

        messages.success(
            request,
            "Employee updated successfully.",
        )

        return redirect("view_employees")

    return render(
        request,
        "employees/edit_employee.html",
        {
            "employee": employee,
            "page_type": "view_employees",
        },
    )


def add_Employee_Predefined_Expences(request):
    if request.method == "POST":
        expense_name = request.POST.get("expence_name", "").strip()
        expense_amount = request.POST.get("expence_amount", "").strip()

        if not expense_name or not expense_amount:
            messages.error(request, "Expense Name and Amount are required.")
            return redirect("add_Employee_Predefined_Expences")

        try:
            expense_amount = Decimal(expense_amount)
        except InvalidOperation:
            messages.error(request, "Please enter a valid expense amount.")
            return redirect("add_Employee_Predefined_Expences")

        if expense_amount <= 0:
            messages.error(request, "Expense amount must be greater than zero.")
            return redirect("add_Employee_Predefined_Expences")

        if PredefinedExpense.objects.filter(name__iexact=expense_name).exists():
            messages.warning(request, f"'{expense_name}' already exists.")
            return redirect("add_Employee_Predefined_Expences")

        try:
            PredefinedExpense.objects.create(
                name=expense_name,
                default_amount=expense_amount,
            )

            messages.success(
                request, f"Predefined Expense '{expense_name}' created successfully!"
            )

            return redirect("view_Predefined_Expences")

        except IntegrityError:
            messages.error(request, "Unable to create predefined expense.")

            return redirect("add_Employee_Predefined_Expences")

    return render(
        request,
        "employees/Employee_Predefined_Expences.html",
        {
            "page_type": "add_Predefined_Expenses",
        },
    )


def view_Predefined_Expences(request):

    search = request.GET.get("search", "").strip()

    predefined_expenses = PredefinedExpense.objects.all().order_by("name")

    if search:
        predefined_expenses = predefined_expenses.filter(
            Q(name__icontains=search) | Q(default_amount__icontains=search)
        )

    context = {
        "predefined_expenses": predefined_expenses,
        "total_predefined_expenses": predefined_expenses.count(),
        "search": search,
        "page_type": "view_Predefined_Expences",
    }

    return render(
        request,
        "employees/view_Predefined_Expences.html",
        context,
    )


def edit_predefined_expense(request, expense_id):
    expense = get_object_or_404(PredefinedExpense, id=expense_id)

    if request.method == "POST":
        name = request.POST.get("expence_name", "").strip()
        amount = request.POST.get("expence_amount", "").strip()

        if not name or not amount:
            messages.error(request, "Name and amount are required.")
            return redirect("view_Predefined_Expences")

        try:
            amount = Decimal(amount)
        except InvalidOperation:
            messages.error(request, "Please enter a valid amount.")
            return redirect("view_Predefined_Expences")

        if amount <= 0:
            messages.error(request, "Amount must be greater than zero.")
            return redirect("view_Predefined_Expences")

        # Check uniqueness (exclude current)
        if PredefinedExpense.objects.filter(name__iexact=name).exclude(id=expense_id).exists():
            messages.warning(request, f"'{name}' already exists.")
            return redirect("view_Predefined_Expences")

        expense.name = name
        expense.default_amount = amount
        expense.save()
        messages.success(request, f"Expense '{name}' updated successfully!")

    return redirect("view_Predefined_Expences")


def delete_predefined_expense(request, expense_id):
    expense = get_object_or_404(PredefinedExpense, id=expense_id)

    if request.method == "POST":
        name = expense.name
        expense.delete()
        messages.success(request, f"Expense '{name}' deleted successfully.")

    return redirect("view_Predefined_Expences")


###############################################################
# OPERATIONAL EXPENSES (MANUAL EXPENSES)
###############################################################


def add_operational_expense(request):
    today = timezone.localdate()
    default_categories = [
        "Vehicle Fuel / Diesel",
        "Vehicle Maintenance",
        "Vehicle Tyres",
        "Vehicle License & Renewal",
        "Driver / Delivery Allowance",
        "Tea & Breakfast",
        "Office Supplies & Electricity",
        "Chanda / Local Donation",
        "Miscellaneous Repair",
    ]
    predefined_names = list(PredefinedExpense.objects.values_list("name", flat=True))
    used_categories = list(OperationalExpense.objects.values_list("category", flat=True).distinct())
    all_categories = sorted(list(set(default_categories + predefined_names + used_categories)))

    if request.method == "POST":
        date_raw = request.POST.get("expense_date", "").strip()
        cat_select = request.POST.get("category_select", "").strip()
        cat_custom = request.POST.get("custom_category", "").strip()
        amount_raw = request.POST.get("amount", "").strip()
        payment_mode = request.POST.get("payment_mode", "Cash").strip()
        reference_no = request.POST.get("reference_no", "").strip()
        description = request.POST.get("description", "").strip()

        category = cat_custom if (cat_select == "__other__" or not cat_select) else cat_select
        category = category.strip()

        if not category:
            messages.error(request, "Please select or enter an expense category.")
            return redirect("add_operational_expense")

        try:
            amount = Decimal(amount_raw)
            if amount <= Decimal("0.00"):
                raise ValueError
        except (InvalidOperation, ValueError):
            messages.error(request, "Please enter a valid expense amount greater than 0.")
            return redirect("add_operational_expense")

        expense_date = parse_date(date_raw) if date_raw else today
        if not expense_date:
            expense_date = today

        user = request.user if request.user.is_authenticated else None

        OperationalExpense.objects.create(
            expense_date=expense_date,
            category=category,
            amount=amount,
            payment_mode=payment_mode or "Cash",
            reference_no=reference_no or None,
            description=description or None,
            created_by=user,
        )

        messages.success(request, f"Expense of ₹{amount:,.2f} for '{category}' recorded successfully!")
        return redirect("operational_expenses_history")

    # GET
    recent_expenses = OperationalExpense.objects.select_related("created_by").order_by("-id")[:5]
    this_month_total = (
        OperationalExpense.objects.filter(
            expense_date__year=today.year,
            expense_date__month=today.month,
        ).aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )

    context = {
        "today": today,
        "categories": all_categories,
        "recent_expenses": recent_expenses,
        "this_month_total": this_month_total,
        "page_type": "add_operational_expense",
    }
    return render(request, "employees/add_operational_expense.html", context)


def operational_expenses_history(request):
    today = timezone.localdate()
    selected_month = request.GET.get("month", "").strip()
    selected_category = request.GET.get("category", "").strip()
    from_date_raw = request.GET.get("from_date", "").strip()
    to_date_raw = request.GET.get("to_date", "").strip()
    q = request.GET.get("q", "").strip()

    # If no filters provided at all, default to current month
    if "month" not in request.GET and not from_date_raw and not to_date_raw:
        selected_month = today.strftime("%Y-%m")

    expenses_qs = OperationalExpense.objects.select_related("created_by").all()

    # Apply date filters
    if selected_month and selected_month != "all":
        try:
            year_str, month_str = selected_month.split("-")
            expenses_qs = expenses_qs.filter(
                expense_date__year=int(year_str),
                expense_date__month=int(month_str),
            )
        except ValueError:
            pass
    elif from_date_raw or to_date_raw:
        if from_date_raw:
            expenses_qs = expenses_qs.filter(expense_date__gte=from_date_raw)
        if to_date_raw:
            expenses_qs = expenses_qs.filter(expense_date__lte=to_date_raw)

    # Category filter
    if selected_category and selected_category != "all":
        expenses_qs = expenses_qs.filter(category__iexact=selected_category)

    # Search query
    if q:
        expenses_qs = expenses_qs.filter(
            Q(category__icontains=q)
            | Q(reference_no__icontains=q)
            | Q(description__icontains=q)
            | Q(payment_mode__icontains=q)
        )

    # KPI Aggregates
    total_amount = expenses_qs.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    total_count = expenses_qs.count()

    # Category-wise breakdown (as requested by user: "মাসের শেষে আমার এই এই খাতে...")
    category_summary = []
    raw_breakdown = (
        expenses_qs.values("category")
        .annotate(total=Sum("amount"), count=Count("id"))
        .order_by("-total")
    )
    for item in raw_breakdown:
        pct = (item["total"] / total_amount * 100) if total_amount > 0 else Decimal("0.00")
        category_summary.append({
            "category": item["category"],
            "total": item["total"],
            "count": item["count"],
            "percentage": round(float(pct), 1),
        })

    # Available categories for dropdown filter
    all_categories = (
        OperationalExpense.objects.values_list("category", flat=True)
        .distinct()
        .order_by("category")
    )

    # Pagination (25 items per page)
    paginator = Paginator(expenses_qs, 25)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "expenses": page_obj,
        "page_obj": page_obj,
        "total_amount": total_amount,
        "total_count": total_count,
        "category_summary": category_summary,
        "all_categories": all_categories,
        "selected_month": selected_month,
        "selected_category": selected_category,
        "from_date": from_date_raw,
        "to_date": to_date_raw,
        "q": q,
        "page_type": "operational_expenses_history",
    }
    return render(request, "employees/operational_expenses_history.html", context)


def edit_operational_expense(request, expense_id):
    expense = get_object_or_404(OperationalExpense, id=expense_id)
    default_categories = [
        "Vehicle Fuel / Diesel",
        "Vehicle Maintenance",
        "Vehicle Tyres",
        "Vehicle License & Renewal",
        "Driver / Delivery Allowance",
        "Tea & Breakfast",
        "Office Supplies & Electricity",
        "Chanda / Local Donation",
        "Miscellaneous Repair",
    ]
    predefined_names = list(PredefinedExpense.objects.values_list("name", flat=True))
    used_categories = list(OperationalExpense.objects.values_list("category", flat=True).distinct())
    all_categories = sorted(list(set(default_categories + predefined_names + used_categories)))

    if request.method == "POST":
        date_raw = request.POST.get("expense_date", "").strip()
        cat_select = request.POST.get("category_select", "").strip()
        cat_custom = request.POST.get("custom_category", "").strip()
        amount_raw = request.POST.get("amount", "").strip()
        payment_mode = request.POST.get("payment_mode", "Cash").strip()
        reference_no = request.POST.get("reference_no", "").strip()
        description = request.POST.get("description", "").strip()

        category = cat_custom if (cat_select == "__other__" or not cat_select) else cat_select
        category = category.strip()

        if not category:
            messages.error(request, "Category is required.")
            return redirect("edit_operational_expense", expense_id=expense.id)

        try:
            amount = Decimal(amount_raw)
            if amount <= Decimal("0.00"):
                raise ValueError
        except (InvalidOperation, ValueError):
            messages.error(request, "Valid amount greater than 0 is required.")
            return redirect("edit_operational_expense", expense_id=expense.id)

        expense_date = parse_date(date_raw) if date_raw else expense.expense_date
        if not expense_date:
            expense_date = expense.expense_date

        expense.expense_date = expense_date
        expense.category = category
        expense.amount = amount
        expense.payment_mode = payment_mode or "Cash"
        expense.reference_no = reference_no or None
        expense.description = description or None
        expense.save()

        messages.success(request, f"Expense #{expense.id} updated successfully!")
        return redirect("operational_expenses_history")

    context = {
        "expense": expense,
        "categories": all_categories,
        "page_type": "edit_operational_expense",
    }
    return render(request, "employees/edit_operational_expense.html", context)


def delete_operational_expense(request, expense_id):
    expense = get_object_or_404(OperationalExpense, id=expense_id)
    if request.method == "POST":
        category = expense.category
        amount = expense.amount
        expense.delete()
        messages.success(request, f"Expense of ₹{amount:,.2f} for '{category}' deleted successfully.")
    return redirect("operational_expenses_history")
