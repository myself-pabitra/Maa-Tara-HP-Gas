from . import views
from django.urls import path

urlpatterns = [
    path("add-new-employee/", views.add_new_employees, name="add_new_employees"),
    path("view-employees/", views.view_employees, name="view_employees"),
    path("delete-employee/<int:employee_id>/", views.delete_employee, name="delete_employee"),
    path("edit-employee/<str:employee_code>/", views.edit_employee, name="edit_employee"),
    ]