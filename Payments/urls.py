from django.urls import path

from . import views

urlpatterns = [
    path(
        "payments-pending-verification/",
        views.CheckPendingVerification,
        name="CheckPendingVerification",
    ),
    path(
        "verify-payment/<str:invoice_number>/",
        views.verify_payment,
        name="verify_payment",
    ),
    path("payments-due/", views.due_payments, name="payment_due_list"),
]
