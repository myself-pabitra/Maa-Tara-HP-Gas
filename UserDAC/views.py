from datetime import datetime, date
import calendar
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
            # Snapshot DAC % at time of this entry so future % changes
            # never retroactively alter credited amounts.
            dac_percentage_at_entry=(
                subdealer.dac_percentage if transaction_type == "CR" else None
            ),
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
    today = timezone.localdate()

    # Dynamic available years
    db_years = {d.year for d in DACEntry.objects.dates("entry_date", "year")}
    db_years.add(today.year)
    for y in range(today.year - 2, today.year + 2):
        db_years.add(y)
    available_years = sorted(list(db_years), reverse=True)

    # 1. Year filter (defaults to current year)
    year_param = request.GET.get("year", "").strip()
    try:
        selected_year = int(year_param) if year_param else today.year
    except ValueError:
        selected_year = today.year

    # 2. Month filter (empty string = All Months; if first load, default to current month)
    is_first_load = ("year" not in request.GET and "month" not in request.GET)
    month_param = request.GET.get("month", "").strip()

    if is_first_load:
        selected_month = today.month
    elif month_param == "" or month_param == "all":
        selected_month = None
    elif "-" in month_param:
        # Backward compatibility for 'YYYY-MM' format
        try:
            y_part, m_part = map(int, month_param.split("-"))
            selected_year = y_part
            selected_month = m_part
        except ValueError:
            selected_month = None
    else:
        try:
            selected_month = int(month_param)
            if not (1 <= selected_month <= 12):
                selected_month = None
        except ValueError:
            selected_month = None

    MONTH_CHOICES = [
        (1, "January"), (2, "February"), (3, "March"), (4, "April"),
        (5, "May"), (6, "June"), (7, "July"), (8, "August"),
        (9, "September"), (10, "October"), (11, "November"), (12, "December")
    ]
    MONTH_NAMES = dict(MONTH_CHOICES)

    if selected_month:
        selected_month_name = MONTH_NAMES.get(selected_month, "")
        period_label = f"{selected_month_name} {selected_year}"
        entries = (
            DACEntry.objects
            .select_related("subdealer")
            .filter(entry_date__year=selected_year, entry_date__month=selected_month)
        )
    else:
        selected_month_name = "All Months"
        period_label = f"All Months ({selected_year})"
        entries = (
            DACEntry.objects
            .select_related("subdealer")
            .filter(entry_date__year=selected_year)
        )

    if subdealer_filter:
        entries = entries.filter(subdealer_id=subdealer_filter)

    # Latest entries first
    entries = entries.order_by("-entry_date", "-created_at", "-id")
    total_entries_count = entries.count()

    paginator = Paginator(entries, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # -----------------------------
    # Summary for the filtered period
    # -----------------------------
    total_punched_cr = Decimal("0.00")
    total_actual_cr = Decimal("0.00")
    for entry in entries.filter(transaction_type="CR"):
        total_punched_cr += entry.transaction_quantity
        pct = (
            entry.dac_percentage_at_entry
            if entry.dac_percentage_at_entry is not None
            else (entry.subdealer.dac_percentage or Decimal("100"))
        )
        total_actual_cr += (entry.transaction_quantity * pct / Decimal("100")).quantize(Decimal("0.01"))

    total_debit = entries.filter(transaction_type="DR").aggregate(
        total=Sum("transaction_quantity")
    )["total"] or Decimal("0.00")

    period_net_balance = (total_actual_cr - total_debit).quantize(Decimal("0.01"))

    context = {
        "entries": page_obj,
        "page_obj": page_obj,
        "total_entries_count": total_entries_count,
        "subdealers": Subdealer.objects.all().order_by("name"),
        "selected_subdealer": subdealer_filter,
        "available_years": available_years,
        "month_choices": MONTH_CHOICES,
        "selected_year": selected_year,
        "selected_month": selected_month,
        "selected_month_name": selected_month_name,
        "period_label": period_label,
        "total_punched_cr": total_punched_cr,
        "total_actual_cr": total_actual_cr,
        "total_debit": total_debit,
        "period_net_balance": period_net_balance,
        "month_net_balance": period_net_balance,
        "page_type": "view_dac",
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
        # Re-snapshot DAC % for CR entries (uses whichever subdealer is now assigned)
        entry.dac_percentage_at_entry = (
            subdealer.dac_percentage if transaction_type == "CR" else None
        )

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
    today = timezone.localdate()

    # Dynamic available years
    db_years = {d.year for d in DACEntry.objects.dates("entry_date", "year")}
    db_years.add(today.year)
    for y in range(today.year - 2, today.year + 2):
        db_years.add(y)
    available_years = sorted(list(db_years), reverse=True)

    # 1. Year filter (defaults to current year)
    year_param = request.GET.get("year", "").strip()
    try:
        selected_year = int(year_param) if year_param else today.year
    except ValueError:
        selected_year = today.year

    # 2. Month filter (empty string = All Months; if first load, default to current month)
    is_first_load = ("year" not in request.GET and "month" not in request.GET)
    month_param = request.GET.get("month", "").strip()

    if is_first_load:
        selected_month = today.month
    elif month_param == "" or month_param == "all":
        selected_month = None
    elif "-" in month_param:
        # Backward compatibility for 'YYYY-MM' format
        try:
            y_part, m_part = map(int, month_param.split("-"))
            selected_year = y_part
            selected_month = m_part
        except ValueError:
            selected_month = None
    else:
        try:
            selected_month = int(month_param)
            if not (1 <= selected_month <= 12):
                selected_month = None
        except ValueError:
            selected_month = None

    MONTH_CHOICES = [
        (1, "January"), (2, "February"), (3, "March"), (4, "April"),
        (5, "May"), (6, "June"), (7, "July"), (8, "August"),
        (9, "September"), (10, "October"), (11, "November"), (12, "December")
    ]
    MONTH_NAMES = dict(MONTH_CHOICES)

    from datetime import timedelta

    if selected_month:
        selected_month_name = MONTH_NAMES.get(selected_month, "")
        period_label = f"{selected_month_name} {selected_year}"
        period_start = date(selected_year, selected_month, 1)
        prev_period_end = period_start - timedelta(days=1)
        period_cr_kwargs = {"entry_date__year": selected_year, "entry_date__month": selected_month}
        period_dr_kwargs = {"entry_date__year": selected_year, "entry_date__month": selected_month}
    else:
        selected_month_name = "All Months"
        period_label = f"All Months ({selected_year})"
        period_start = date(selected_year, 1, 1)
        prev_period_end = period_start - timedelta(days=1)
        period_cr_kwargs = {"entry_date__year": selected_year}
        period_dr_kwargs = {"entry_date__year": selected_year}

    subdealers = Subdealer.objects.all().order_by("name")
    if subdealer_filter:
        subdealers = subdealers.filter(id=subdealer_filter)

    rows = []

    for subdealer in subdealers:

        # Step 1: Punched & Actual Credit in this period (excluding invoice reconciliation refunds)
        period_cr_entries = DACEntry.objects.filter(
            subdealer=subdealer,
            transaction_type="CR",
            **period_cr_kwargs,
        ).exclude(description__istartswith="Refund")
        period_raw_credit = Decimal("0")
        period_dac_credited = Decimal("0")
        for entry in period_cr_entries:
            qty = entry.transaction_quantity
            pct = (
                entry.dac_percentage_at_entry
                if entry.dac_percentage_at_entry is not None
                else (subdealer.dac_percentage or Decimal("100"))
            )
            period_raw_credit += qty
            period_dac_credited += qty * pct / Decimal("100")
        period_dac_credited = period_dac_credited.quantize(Decimal("0.01"))

        # Step 2: Previous Balance (Rolled over prior to period_start)
        prev_cr_entries = DACEntry.objects.filter(
            subdealer=subdealer,
            transaction_type="CR",
            entry_date__lte=prev_period_end,
        )
        effective_up_to_prev = Decimal("0")
        for entry in prev_cr_entries:
            qty = entry.transaction_quantity
            pct = (
                entry.dac_percentage_at_entry
                if entry.dac_percentage_at_entry is not None
                else (subdealer.dac_percentage or Decimal("100"))
            )
            effective_up_to_prev += qty * pct / Decimal("100")
        effective_up_to_prev = effective_up_to_prev.quantize(Decimal("0.01"))

        total_dr_before = (
            DACEntry.objects.filter(
                subdealer=subdealer,
                transaction_type="DR",
                entry_date__lte=prev_period_end,
            ).aggregate(total=Sum("transaction_quantity"))["total"]
            or Decimal("0")
        )

        prev_balance = (effective_up_to_prev - total_dr_before).quantize(Decimal("0.01"))

        # Step 3: Total Available Bal
        available_dac_balance = (period_dac_credited + prev_balance).quantize(Decimal("0.01"))

        # Step 4: Net Cylinders Delivered in this period (gross DR minus reconciliation refunds)
        total_dr_period = (
            DACEntry.objects.filter(
                subdealer=subdealer,
                transaction_type="DR",
                **period_dr_kwargs,
            ).aggregate(total=Sum("transaction_quantity"))["total"]
            or Decimal("0")
        )

        total_refund_period = (
            DACEntry.objects.filter(
                subdealer=subdealer,
                transaction_type="CR",
                description__istartswith="Refund",
                **period_cr_kwargs,
            ).aggregate(total=Sum("transaction_quantity"))["total"]
            or Decimal("0")
        )

        refills_period = max(Decimal("0"), total_dr_period - total_refund_period)

        # Step 5: Final Remaining DAC Balance
        final_remaining = (available_dac_balance - refills_period).quantize(Decimal("0.01"))

        # Skip all-zero inactive rows unless specifically filtered
        is_all_zero = (
            period_raw_credit == Decimal("0")
            and prev_balance == Decimal("0")
            and refills_period == Decimal("0")
            and final_remaining == Decimal("0")
        )

        if not subdealer_filter and is_all_zero:
            continue

        latest_entry = (
            DACEntry.objects.filter(subdealer=subdealer)
            .order_by("-entry_date", "-created_at", "-id")
            .first()
        )
        overall_ledger_balance = latest_entry.closing_balance if latest_entry else Decimal("0")

        rows.append({
            "subdealer": subdealer,
            "dac_percentage": subdealer.dac_percentage or Decimal("0"),
            "this_month_raw_credit": period_raw_credit,
            "this_month_dac_credited": period_dac_credited,
            "prev_month_balance": prev_balance,
            "available_dac_balance": available_dac_balance,
            "refills_this_month": refills_period,
            "final_remaining": final_remaining,
            "overall_ledger_balance": overall_ledger_balance,
        })

    # Sort: largest pending (positive remaining) first, then over-delivered last
    rows.sort(key=lambda x: x["final_remaining"], reverse=True)

    sum_pending_positive = sum(r["final_remaining"] for r in rows if r["final_remaining"] > 0)
    pending_subdealers_count = sum(1 for r in rows if r["final_remaining"] > 0)

    # Extra delivered (negative balance in Final Remaining DAC Balance column)
    sum_negative_remaining = abs(sum(r["final_remaining"] for r in rows if r["final_remaining"] < 0))
    negative_subdealers_count = sum(1 for r in rows if r["final_remaining"] < 0)

    stats = {
        "total_subdealers": len(rows),
        "sum_raw_credit": sum(r["this_month_raw_credit"] for r in rows),
        "sum_dac_credited": sum(r["this_month_dac_credited"] for r in rows),
        "sum_prev_balances": sum(r["prev_month_balance"] for r in rows),
        "sum_available": sum(r["available_dac_balance"] for r in rows),
        "sum_refills": sum(r["refills_this_month"] for r in rows),
        "sum_pending_positive": sum_pending_positive,
        "pending_subdealers_count": pending_subdealers_count,
        "sum_negative_remaining": sum_negative_remaining,
        "negative_subdealers_count": negative_subdealers_count,
    }

    paginator = Paginator(rows, 20)
    page_number = request.GET.get("page")
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
            "available_years": available_years,
            "month_choices": MONTH_CHOICES,
            "selected_year": selected_year,
            "selected_month": selected_month,
            "selected_month_name": selected_month_name,
            "period_label": period_label,
            # For backward compatibility with any template variable
            "year": selected_year,
            "month": selected_month,
            "page_type": "pending_dac_orders",
        },
    )