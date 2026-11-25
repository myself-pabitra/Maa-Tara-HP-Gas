from django.contrib import admin
from .models import Employee, OperationalExpense


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("employeeCode", "name", "phone", "is_active", "created_at")
    search_fields = ("name", "employeeCode", "phone")
    list_filter = ("is_active",)


@admin.register(OperationalExpense)
class OperationalExpenseAdmin(admin.ModelAdmin):
    list_display = ("expense_date", "category", "amount", "payment_mode", "reference_no", "created_by")
    search_fields = ("category", "reference_no", "description")
    list_filter = ("expense_date", "category", "payment_mode")
