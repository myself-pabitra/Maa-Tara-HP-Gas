from . import views
from django.urls import path

urlpatterns = [
    path("dac-entry/", views.dac_entry, name="dac_entry"),
    path("dac-view/", views.view_dac, name="view_dac"),
    path("dac-edit/<int:entry_id>/", views.dac_edit, name="dac_edit"),
    path("dac-delete/<int:entry_id>/", views.dac_delete, name="dac_delete"),
    path("pending-dac-orders/", views.Pending_DAC_Orders, name="pending_dac_orders"),
]
