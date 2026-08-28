from . import views
from django.urls import path

urlpatterns = [
    path("add-subdealers/", views.CreateNewSubDealers, name="CreateNewSubDealers"),
    path(
        "add-subdealers-product-discount/",
        views.addSubDealersProductDiscount,
        name="addSubDealersProductDiscount",
    ),
    path(
        "view-discounts/",
        views.view_subdealer_discounts,
        name="view_subdealer_discounts",
    ),
    path(
        "delete-discount/<int:discount_id>/",
        views.delete_subdealer_discount,
        name="delete_subdealer_discount",
    ),
    path("view-subdealers/", views.view_subdealers, name="view_subdealers"),
    path(
        "edit-subdealer/<int:subdealer_id>/",
        views.edit_subdealer,
        name="edit_subdealer",
    ),
    path(
        "delete-subdealer/<int:subdealer_id>/",
        views.delete_subdealer,
        name="delete_subdealer",
    ),
    path(
        "create-daily-sell-invoice/",
        views.create_invoice,
        name="create_daily_sell_invoice",
    ),
    path("billing/", views.view_invoices, name="view_daily_sell_invoices"),
    path(
        "billing/<int:invoice_id>/edit/",
        views.edit_invoice,
        name="edit_daily_sell_invoice",
    ),
    path(
        "billing/<int:invoice_id>/download-pdf/",
        views.download_invoice_pdf,
        name="download_invoice_pdf",
    ),
    path(
        "billing/<int:invoice_id>/print/",
        views.print_invoice,
        name="print_daily_sell_invoice",
    ),


    path("billing/cylender-mismatch/", views.Cylender_Mismatch, name="Cylender_Mismatch"),


    path(
        "billing/<int:invoice_id>/mismatch-record/",
        views.print_mismatch_record,
        name="print_mismatch_record",
    ),
]
