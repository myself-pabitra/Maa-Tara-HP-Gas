from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import IntegrityError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from SubDealers.models import PredefinedExpense

from .models import Employee


def add_new_employees(request):
    if request.method == "POST":
        employee_name = request.POST.get("employee_name")
        employee_phone = request.POST.get("phone")
        employee_address = request.POST.get("address")

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
    employees = Employee.objects.all()  # Optional: list all employees below the form
    context = {"employees": employees, "page_type": "add_new_employees"}
    return render(request, "employees/add_new_employees.html", context)


def view_employees(request):

    search = request.GET.get("search", "").strip()

    employees = Employee.objects.all().order_by("name")

    if search:
        employees = employees.filter(
            Q(name__icontains=search)
            | Q(phone__icontains=search)
            | Q(address__icontains=search)
        )

    context = {
        "employees": employees,
        "total_employees": employees.count(),
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
