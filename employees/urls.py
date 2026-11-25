from . import views
from django.urls import path

urlpatterns = [
    path("add-new-employee/", views.add_new_employees, name="add_new_employees"),
    path("view-employees/", views.view_employees, name="view_employees"),
    path(
        "delete-employee/<int:employee_id>/",
        views.delete_employee,
        name="delete_employee",
    ),
    path(
        "edit-employee/<str:employee_code>/", views.edit_employee, name="edit_employee"
    ),
    path(
        "add-employee-predefined-expences/",
        views.add_Employee_Predefined_Expences,
        name="add_Employee_Predefined_Expences",
    ),
    path(
        "view-predefined-expences/",
        views.view_Predefined_Expences,
        name="view_Predefined_Expences",
    ),
    path(
        "edit-predefined-expense/<int:expense_id>/",
        views.edit_predefined_expense,
        name="edit_predefined_expense",
    ),
    path(
        "delete-predefined-expense/<int:expense_id>/",
        views.delete_predefined_expense,
        name="delete_predefined_expense",
    ),
    # Operational Expenses (Manual Expenses)
    path("expenses/add/", views.add_operational_expense, name="add_operational_expense"),
    path("expenses/history/", views.operational_expenses_history, name="operational_expenses_history"),
    path("expenses/edit/<int:expense_id>/", views.edit_operational_expense, name="edit_operational_expense"),
    path("expenses/delete/<int:expense_id>/", views.delete_operational_expense, name="delete_operational_expense"),
]
