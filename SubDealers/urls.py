from . import views
from django.urls import path

urlpatterns = [
    path("add-subdealers/", views.CreateNewSubDealers, name="CreateNewSubDealers"),
    path('add-subdealers-product-discount/', views.addSubDealersProductDiscount, name='addSubDealersProductDiscount'),
    path("view-discounts/", views.view_subdealer_discounts, name="view_subdealer_discounts"),
    path("view-subdealers/", views.view_subdealers, name="view_subdealers"),
    path("pending-orders/", views.pending_orders, name="pending_orders"),
    path("edit-subdealer/<int:subdealer_id>/", views.edit_subdealer, name="edit_subdealer"),
    path("delete-subdealer/<int:subdealer_id>/", views.delete_subdealer, name="delete_subdealer"),
    path("create-daily-sell-invoice/", views.create_invoice, name="create_daily_sell_invoice"),
    path("billing/", views.view_invoices, name="view_daily_sell_invoices"),
    path("billing/<int:invoice_id>/edit/", views.edit_invoice, name="edit_daily_sell_invoice"),
    path("billing/<int:invoice_id>/download-pdf/", views.download_invoice_pdf, name="download_invoice_pdf"),
    path("billing/<int:invoice_id>/print/", views.print_invoice, name="print_daily_sell_invoice"),
    path("billing/mismatch-records/", views.mismatch_records, name="mismatch_records"),
    path("billing/<int:invoice_id>/mismatch-record/", views.print_mismatch_record, name="print_mismatch_record"),
    path("billing/payment-verify/<int:item_id>/", views.verify_payment, name="verify_payment"),
    path("billing/payments-verification/", views.payment_verification, name="payment_verification"),
    path("billing/payments-due/", views.due_payments, name="payment_due_list"),
    path("billing/monthly-summary/", views.monthly_summary, name="monthly_summary"),
    path("dac-entry/", views.dac_entry, name="dac_entry"),
    path("dac-view/", views.view_dac, name="view_dac"),
    path("dac-edit/<int:entry_id>/", views.dac_edit, name="dac_edit"),
    path("dac-delete/<int:entry_id>/", views.dac_delete, name="dac_delete"),
]
