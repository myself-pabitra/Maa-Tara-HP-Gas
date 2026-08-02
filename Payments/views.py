from datetime import timedelta, timezone
from decimal import Decimal

from django.contrib import messages
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render

from SubDealers.models import DailyInvoice, DailyInvoiceLineItem, Subdealer


def CheckPendingVerification(request):
    pending_payments = (
        DailyInvoiceLineItem.objects.filter(
            payment_status="PENDING",
            payment_mode__in=["AC", "Mixed"],
        )
        .select_related("invoice", "subdealer", "product")
        .order_by("created_at", "subdealer__name")
    )

    return render(
        request,
        "payments/payment_verification.html",
        {
            "pending_payments": pending_payments,
            "page_type": "payment_verification",
        },
    )





def verify_payment(request, invoice_number):

    if request.method != "POST":
        return redirect("CheckPendingVerification")

    invoice = get_object_or_404(
        DailyInvoice,
        invoice_number=invoice_number,
    )

    try:
        received = Decimal(request.POST.get("received_amount", "0"))
    except Exception:
        messages.error(request, "Invalid amount.")
        return redirect("CheckPendingVerification")

    # Find AC/Mixed line items still awaiting payment
    line_items = invoice.line_items.filter(
        payment_status__in=["PENDING", "PARTIAL"],
        payment_mode__in=["AC", "Mixed"],
    )

    expected = sum(item.due_amount for item in line_items)

    if received > expected:
        messages.error(
            request,
            f"Received amount cannot exceed ₹{expected}.",
        )
        return redirect("CheckPendingVerification")

    remaining = received

    for item in line_items.order_by("id"):
        if remaining <= 0:
            break

        pay = min(item.due_amount, remaining)

        item.verified_ac_amount += pay
        item.due_amount -= pay

        if item.due_amount == 0:
            item.payment_status = "PAID"
        else:
            item.payment_status = "PARTIAL"

        item.save()

        remaining -= pay

    messages.success(
        request,
        f"Invoice {invoice.invoice_number} verified successfully.",
    )

    return redirect("CheckPendingVerification")


def due_payments(request):

    subdealer_filter = request.GET.get("subdealer")
    invoice_filter = request.GET.get("invoice")

    due_items = (
        DailyInvoiceLineItem.objects.filter(
            Q(payment_status="PENDING") | Q(payment_status="PARTIAL"),
            due_amount__gt=Decimal("0.00"),
        )
        .select_related(
            "invoice",
            "subdealer",
            "product",
        )
        .order_by(
            "invoice__invoice_date",
            "subdealer__name",
            "invoice__invoice_number",
        )
    )

    if subdealer_filter:
        #filter by subdealer code instead of ID
        due_items = due_items.filter(subdealer__subdealerCode=subdealer_filter)

    if invoice_filter:
        due_items = due_items.filter(invoice__invoice_number__icontains=invoice_filter)

    total_due = due_items.aggregate(total=Sum("due_amount"))["total"] or Decimal("0.00")

    total_pending_invoices = due_items.values("invoice").distinct().count()

    total_pending_subdealers = due_items.values("subdealer").distinct().count()

    context = {
        "due_items": due_items,
        "total_due": total_due,
        "total_pending_invoices": total_pending_invoices,
        "total_pending_subdealers": total_pending_subdealers,
        "subdealers": Subdealer.objects.all().order_by("name"),
        "selected_subdealer": subdealer_filter,
        "invoice_search": invoice_filter,
        "page_type": "payment_due_list",
    }

    return render(
        request,
        "payments/payment_due_list.html",
        context,
    )
