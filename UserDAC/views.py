from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.core.paginator import Paginator
from django.utils import timezone

from SubDealers.models import DailyInvoiceLineItem, Subdealer

from .helpers import recalculate_balances
from .models import DACEntry, Subdealer

###############################################################
# CREATE DAC ENTRY
###############################################################


def dac_entry(request):
    subdealers = Subdealer.objects.all().order_by("name")

    if request.method == "POST":
        subdealer_code = request.POST.get("subdealer_code")
        dac_date = request.POST.get("dac_date")
        transaction_type = request.POST.get("transaction_type")
        quantity_raw = request.POST.get("transaction_quantity")
        description = request.POST.get("description", "")

        if not all([subdealer_code, dac_date, transaction_type, quantity_raw]):
            messages.error(request, "Please fill all required fields.")
            return redirect("dac_entry")

        try:
            quantity = Decimal(quantity_raw)
            if quantity <= 0:
                raise ValueError("Quantity must be greater than zero.")
        except (InvalidOperation, ValueError) as e:
            messages.error(request, f"Invalid quantity: {e}")
            return redirect("dac_entry")

        try:
            subdealer = Subdealer.objects.get(subdealerCode=subdealer_code)
        except Subdealer.DoesNotExist:
            messages.error(request, "Subdealer not found.")
            return redirect("dac_entry")

        entry_date = datetime.strptime(dac_date, "%Y-%m-%d").date()

        DACEntry.objects.create(
            subdealer=subdealer,
            entry_date=entry_date,
            transaction_type=transaction_type,
            transaction_quantity=quantity,
            description=description,
        )

        # Recalculate ledger
        recalculate_balances(subdealer)

        messages.success(
            request,
            f"DAC {transaction_type} of {quantity} for '{subdealer.name}' added successfully."
        )

        return redirect("dac_entry")

    # Fetch latest balance for each subdealer
    subdealer_balances = {}
    for entry in DACEntry.objects.order_by("entry_date", "created_at", "id"):
        subdealer_balances[entry.subdealer_id] = entry.closing_balance

    subdealers_with_balance = []
    for s in subdealers:
        bal = subdealer_balances.get(s.id, Decimal("0.00"))
        subdealers_with_balance.append({
            "id": s.id,
            "name": s.name,
            "code": s.subdealerCode,
            "phone": s.phone_number,
            "dac_percentage": str(s.dac_percentage),
            "current_balance": str(bal),
        })

    recent_entries = (
        DACEntry.objects.select_related("subdealer")
        .order_by("-id")[:8]
    )

    total_cr = DACEntry.objects.filter(transaction_type="CR").aggregate(t=Sum("transaction_quantity"))["t"] or Decimal("0.00")
    total_dr = DACEntry.objects.filter(transaction_type="DR").aggregate(t=Sum("transaction_quantity"))["t"] or Decimal("0.00")

    return render(
        request,
        "Dac/dac_entry.html",
        {
            "today": timezone.localdate(),
            "subdealers": subdealers,
            "subdealers_with_balance": subdealers_with_balance,
            "recent_entries": recent_entries,
            "total_cr": total_cr,
            "total_dr": total_dr,
            "page_type": "entry_dac",
        },
    )


###############################################################
# VIEW DAC
###############################################################


def view_dac(request):

    subdealer_filter = request.GET.get("subdealer")
    from_date = request.GET.get("from_date")
    to_date = request.GET.get("to_date")

    entries = DACEntry.objects.select_related("subdealer").all()

    # -----------------------------
    # Filters
    # -----------------------------

    if subdealer_filter:
        entries = entries.filter(subdealer_id=subdealer_filter)

    if from_date:
        entries = entries.filter(entry_date__gte=from_date)

    if to_date:
        entries = entries.filter(entry_date__lte=to_date)

    # Latest entries first
    entries = entries.order_by("-entry_date", "-created_at", "-id")
    total_entries_count = entries.count()

    paginator = Paginator(entries, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # -----------------------------
    # Summary
    # -----------------------------

    total_credit = entries.filter(transaction_type="CR").aggregate(
        total=Sum("transaction_quantity")
    )["total"] or Decimal("0.00")

    total_debit = entries.filter(transaction_type="DR").aggregate(
        total=Sum("transaction_quantity")
    )["total"] or Decimal("0.00")

    current_balance = total_credit - total_debit

    context = {
        "entries": page_obj,
        "page_obj": page_obj,
        "total_entries_count": total_entries_count,
        "subdealers": Subdealer.objects.all().order_by("name"),
        "selected_subdealer": subdealer_filter,
        "from_date": from_date,
        "to_date": to_date,
        "total_credit": total_credit,
        "total_debit": total_debit,
        "current_balance": current_balance,
        "page_type": "view_dac"
    }

    return render(
        request,
        "Dac/view_dac.html",
        context,
    )


###############################################################
# EDIT DAC ENTRY
###############################################################


def dac_edit(request, entry_id):

    entry = get_object_or_404(
        DACEntry,
        pk=entry_id,
    )

    subdealers = Subdealer.objects.all()

    if request.method == "POST":
        subdealer_code = request.POST.get("subdealer_code")
        dac_date = request.POST.get("dac_date")
        transaction_type = request.POST.get("transaction_type")
        quantity_raw = request.POST.get("transaction_quantity")
        description = request.POST.get("description", "")

        if not all([subdealer_code, dac_date, transaction_type, quantity_raw]):
            messages.error(request, "Please fill all required fields.")
            return redirect(
                "dac_edit",
                entry_id=entry.id,
            )

        try:
            quantity = Decimal(quantity_raw)
        except InvalidOperation:
            messages.error(request, "Invalid Quantity.")
            return redirect(
                "dac_edit",
                entry_id=entry.id,
            )

        try:
            subdealer = Subdealer.objects.get(subdealerCode=subdealer_code)
        except Subdealer.DoesNotExist:
            messages.error(request, "Subdealer not found.")
            return redirect(
                "dac_edit",
                entry_id=entry.id,
            )

        old_subdealer = entry.subdealer

        entry.subdealer = subdealer
        entry.entry_date = datetime.strptime(
            dac_date,
            "%Y-%m-%d",
        ).date()

        entry.transaction_type = transaction_type
        entry.transaction_quantity = quantity
        entry.description = description

        entry.save()

        # Recalculate balances

        recalculate_balances(old_subdealer)

        if old_subdealer != subdealer:
            recalculate_balances(subdealer)

        messages.success(request, "DAC Entry Updated Successfully.")

        return redirect("view_dac")

    context = {
        "entry": entry,
        "subdealers": subdealers,
        "page_type": "edit_dac"
    }

    return render(
        request,
        "Dac/dac_edit.html",
        context,
    )


###############################################################
# DELETE DAC ENTRY
###############################################################


def dac_delete(request, entry_id):

    entry = get_object_or_404(
        DACEntry,
        pk=entry_id,
    )

    subdealer = entry.subdealer

    entry.delete()

    recalculate_balances(subdealer)

    messages.success(request, "DAC Entry Deleted Successfully.")

    return redirect("view_dac")



def Pending_DAC_Orders(request):

    subdealer_filter = request.GET.get("subdealer")
    selected_month = request.GET.get("month")

    # Default to current month
    if selected_month:
        year, month = map(int, selected_month.split("-"))
    else:
        today = timezone.localdate()
        year = today.year
        month = today.month
        selected_month = today.strftime("%Y-%m")

    subdealers = Subdealer.objects.all().order_by("name")

    if subdealer_filter:
        subdealers = subdealers.filter(id=subdealer_filter)

    rows = []

    for subdealer in subdealers:
        # =====================================
        # Monthly DAC Credit
        # =====================================

        total_credit = DACEntry.objects.filter(
            subdealer=subdealer,
            transaction_type="CR",
            entry_date__year=year,
            entry_date__month=month,
        ).aggregate(total=Sum("transaction_quantity"))["total"] or Decimal("0")

        # =====================================
        # Current Ledger Balance (Overall)
        # =====================================

        latest = (
            DACEntry.objects.filter(subdealer=subdealer)
            .order_by("-entry_date", "-created_at", "-id")
            .first()
        )

        current_balance = latest.closing_balance if latest else Decimal("0")

        # =====================================
        # Monthly DAC Applicable Refills Sold
        # =====================================

        total_refills = (
            DailyInvoiceLineItem.objects.filter(
                subdealer=subdealer,
                product__dac_applicable=True,
                invoice__invoice_date__year=year,
                invoice__invoice_date__month=month,
            ).aggregate(total=Sum("quantity"))["total"]
            or 0
        )

        # =====================================
        # Effective DAC
        # =====================================

        effective_dac = int(total_credit * subdealer.dac_percentage / Decimal("100"))

        # =====================================
        # Pending Order
        # =====================================

        pending_order = effective_dac - total_refills

        rows.append(
            {
                "subdealer": subdealer,
                "total_credit": int(total_credit),
                "current_dac": int(current_balance),
                "total_refills": int(total_refills),
                "dac_percentage": subdealer.dac_percentage,
                "effective_dac": effective_dac,
                "pending_order": pending_order,
            }
        )

    rows.sort(
        key=lambda x: x["pending_order"],
        reverse=True,
    )

    stats = {
        "total_subdealers": len(rows),
        "sum_total_refills": sum(r["total_refills"] for r in rows),
        "sum_effective_dac": sum(r["effective_dac"] for r in rows),
        "sum_pending_positive": sum(r["pending_order"] for r in rows if r["pending_order"] > 0),
        "pending_subdealers_count": sum(1 for r in rows if r["pending_order"] > 0),
    }

    paginator = Paginator(rows, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "Dac/pending_dac_orders.html",
        {
            "rows": page_obj,
            "page_obj": page_obj,
            "stats": stats,
            "subdealers": Subdealer.objects.all().order_by("name"),
            "selected_subdealer": subdealer_filter,
            "selected_month": selected_month,
            "page_type": "pending_dac_orders",
        },
    )