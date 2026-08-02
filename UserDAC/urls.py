from . import views
from django.urls import path

urlpatterns = [
    path("userdac/dac-entry/", views.dac_entry, name="dac_entry"),
    path("userdac/dac-view/", views.view_dac, name="view_dac"),
    path("userdac/dac-edit/<int:entry_id>/", views.dac_edit, name="dac_edit"),
    path("userdac/dac-delete/<int:entry_id>/", views.dac_delete, name="dac_delete"),
    path("userdac/pending-dac-orders/", views.Pending_DAC_Orders, name="pending_dac_orders"),
]
