from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.core.paginator import Paginator
from django.utils import timezone

from SubDealers.models import DailyInvoice, DailyInvoiceLineItem, Subdealer


def CheckPendingVerification(request):
    subdealer_filter = request.GET.get("subdealer", "").strip()
    search = (request.GET.get("search") or request.GET.get("q") or "").strip()

    pending_payments_qs = (
        DailyInvoiceLineItem.objects.filter(
            payment_status__in=["PENDING", "PARTIAL"],
            payment_mode__in=["AC", "Mixed"],
        )
        .select_related("invoice", "subdealer", "product")
        .order_by("-invoice__invoice_date", "subdealer__name")
    )

    if subdealer_filter:
        pending_payments_qs = pending_payments_qs.filter(
            Q(subdealer__subdealerCode=subdealer_filter) | Q(subdealer__name__icontains=subdealer_filter)
        )

    if search:
        pending_payments_qs = pending_payments_qs.filter(
            Q(invoice__invoice_number__icontains=search)
            | Q(subdealer__name__icontains=search)
            | Q(product__product_name__icontains=search)
            | Q(remarks__icontains=search)
        )

    total_pending_count = pending_payments_qs.count()
    total_ac_amount = pending_payments_qs.aggregate(t=Sum("ac_amount"))["t"] or Decimal("0.00")
    total_received_amount = pending_payments_qs.aggregate(t=Sum("verified_ac_amount"))["t"] or Decimal("0.00")
    total_due_amount = pending_payments_qs.aggregate(t=Sum("due_amount"))["t"] or Decimal("0.00")

    paginator = Paginator(pending_payments_qs, 25)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "payments/payment_verification.html",
        {
            "pending_payments": page_obj,
            "page_obj": page_obj,
            "total_pending_count": total_pending_count,
            "total_ac_amount": total_ac_amount,
            "total_received_amount": total_received_amount,
            "total_due_amount": total_due_amount,
            "subdealers": Subdealer.objects.all().order_by("name"),
            "selected_subdealer": subdealer_filter,
            "search": search,
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

    next_page = request.POST.get("next", "verify")

    try:
        received = Decimal(request.POST.get("received_amount", "0").strip())
    except (InvalidOperation, Exception):
        messages.error(request, "Invalid amount provided.")
        return redirect("payment_due_list" if next_page == "due" else "CheckPendingVerification")

    expected = item.due_amount

    if received <= Decimal("0"):
        messages.error(request, "Received amount must be greater than zero.")
        return redirect("payment_due_list" if next_page == "due" else "CheckPendingVerification")

    if received > expected:
        messages.error(
            request,
            f"Received amount ₹{received} cannot exceed outstanding due ₹{expected}.",
        )
        return redirect("payment_due_list" if next_page == "due" else "CheckPendingVerification")

    item.verified_ac_amount += received
    item.due_amount = max(Decimal("0.00"), item.due_amount - received)
    item.verified_at = timezone.now()

    if item.due_amount == Decimal("0.00"):
        item.payment_status = "PAID"
    else:
        item.payment_status = "PARTIAL"

    item.save(update_fields=["verified_ac_amount", "due_amount", "payment_status", "verified_at"])

    messages.success(
        request,
        f"Payment of ₹{received} for {item.display_name} ({item.subdealer.name} - Invoice {invoice.invoice_number}) verified successfully.",
    )

    if next_page == "due":
        return redirect("payment_due_list")
    return redirect("CheckPendingVerification")


def due_payments(request):
    subdealer_filter = request.GET.get("subdealer", "").strip()
    search = (request.GET.get("invoice") or request.GET.get("search") or request.GET.get("q") or "").strip()

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
            "-invoice__invoice_date",
            "subdealer__name",
            "invoice__invoice_number",
        )
    )

    if subdealer_filter:
        due_items = due_items.filter(
            Q(subdealer__subdealerCode=subdealer_filter) | Q(subdealer__name__icontains=subdealer_filter)
        )

    if search:
        due_items = due_items.filter(
            Q(invoice__invoice_number__icontains=search)
            | Q(subdealer__name__icontains=search)
            | Q(product__product_name__icontains=search)
            | Q(remarks__icontains=search)
        )

    total_due = due_items.aggregate(total=Sum("due_amount"))["total"] or Decimal("0.00")
    total_pending_invoices = due_items.values("invoice").distinct().count()
    total_pending_subdealers = due_items.values("subdealer").distinct().count()

    paginator = Paginator(due_items, 25)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "due_items": page_obj,
        "page_obj": page_obj,
        "total_due": total_due,
        "total_pending_invoices": total_pending_invoices,
        "total_pending_subdealers": total_pending_subdealers,
        "subdealers": Subdealer.objects.all().order_by("name"),
        "selected_subdealer": subdealer_filter,
        "invoice_search": search,
        "search": search,
        "page_type": "payment_due_list",
    }

    return render(
        request,
        "payments/payment_due_list.html",
        context,
    )
