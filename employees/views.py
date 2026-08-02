from django.shortcuts import render, redirect
from django.contrib import messages
from .models import Employee
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.db.models import Q
from django.shortcuts import render


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
