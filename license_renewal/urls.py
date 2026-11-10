from django.urls import path

from .views import (
    license_renewal_delete,
    license_renewal_update,
    license_renewal_view,
)

urlpatterns = [
    path("", license_renewal_view, name="license_renewal_view"),
    path("view/", license_renewal_view, name="license_renewal_view_alias"),
    path("update/", license_renewal_update, name="license_renewal_update"),
    path("update/<int:record_id>/", license_renewal_update, name="license_renewal_update_record"),
    path("delete/<int:record_id>/", license_renewal_delete, name="license_renewal_delete"),
]
