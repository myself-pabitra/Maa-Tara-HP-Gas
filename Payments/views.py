from datetime import timedelta, timezone
from decimal import Decimal

from django.contrib import messages
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.core.paginator import Paginator

from SubDealers.models import DailyInvoice, DailyInvoiceLineItem, Subdealer


def CheckPendingVerification(request):
    # Include PARTIAL items too — they should remain in verification until fully paid
    pending_payments_qs = (
        DailyInvoiceLineItem.objects.filter(
            payment_status__in=["PENDING", "PARTIAL"],
            payment_mode__in=["AC", "Mixed"],
        )
        .select_related("invoice", "subdealer", "product")
        .order_by("created_at", "subdealer__name")
    )

    paginator = Paginator(pending_payments_qs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "payments/payment_verification.html",
        {
            "pending_payments": page_obj,
            "page_obj": page_obj,
            "page_type": "payment_verification",
        },
    )


def verify_payment(request, item_id):
    """
    Verify a payment for a specific invoice line item. Accepts a POST with:
      - received_amount: amount being paid now
      - next: optional, 'due' to redirect back to due payments after verifying
    """
    if request.method != "POST":
        return redirect("CheckPendingVerification")

    item = get_object_or_404(DailyInvoiceLineItem, pk=item_id)
    invoice = item.invoice

    # Determine where to redirect after verifying
    next_page = request.POST.get("next", "verify")

    try:
        received = Decimal(request.POST.get("received_amount", "0"))
    except Exception:
        messages.error(request, "Invalid amount.")
        if next_page == "due":
            return redirect("payment_due_list")
        return redirect("CheckPendingVerification")

    expected = item.due_amount

    if received <= Decimal("0"):
        messages.error(request, "Received amount must be greater than zero.")
        if next_page == "due":
            return redirect("payment_due_list")
        return redirect("CheckPendingVerification")

    if received > expected:
        messages.error(
            request,
            f"Received amount ₹{received} cannot exceed outstanding due ₹{expected}.",
        )
        if next_page == "due":
            return redirect("payment_due_list")
        return redirect("CheckPendingVerification")

    item.verified_ac_amount += received
    item.due_amount -= received

    if item.due_amount == 0:
        item.payment_status = "PAID"
    else:
        item.payment_status = "PARTIAL"

    item.save()

    messages.success(
        request,
        f"Payment for {item.display_name} (Invoice {invoice.invoice_number}): ₹{received} verified successfully.",
    )

    if next_page == "due":
        return redirect("payment_due_list")
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
        # filter by subdealer code instead of ID
        due_items = due_items.filter(subdealer__subdealerCode=subdealer_filter)

    if invoice_filter:
        due_items = due_items.filter(invoice__invoice_number__icontains=invoice_filter)

    total_due = due_items.aggregate(total=Sum("due_amount"))["total"] or Decimal("0.00")

    total_pending_invoices = due_items.values("invoice").distinct().count()

    total_pending_subdealers = due_items.values("subdealer").distinct().count()

    paginator = Paginator(due_items, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        "due_items": page_obj,
        "page_obj": page_obj,
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
