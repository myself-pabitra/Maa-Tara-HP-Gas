from datetime import date

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import LicenseRenewal


def add_expiry_reminders(request):
    """
    Recalculates remaining days and statuses for all license records,
    saving records if status or remaining days have changed,
    and adds warning flash messages for records expiring within 5 days.
    """
    records = LicenseRenewal.objects.all()
    reminder_count = 0

    for record in records:
        prev_days = record.remaining_days
        prev_status = record.status

        record.update_status(record.expire_date)
        if record.remaining_days != prev_days or record.status != prev_status:
            record.save(update_fields=["remaining_days", "status"])

        if 0 <= record.remaining_days <= 5:
            messages.warning(
                request,
                f"Reminder: {record.vehicle_no} ({record.paper_display}) expires in {record.remaining_days} day(s).",
            )
            reminder_count += 1

    return reminder_count


def license_renewal_view(request):
    """
    List vehicle licenses and compliance records with search, filtering,
    KPI summary metrics, and pagination.
    """
    # Sync statuses and surface any 5-day expiry warnings
    add_expiry_reminders(request)

    all_records = LicenseRenewal.objects.all().order_by("expire_date")

    # Overall KPIs (calculated across all records)
    total_count = all_records.count()
    active_count = all_records.filter(status="Active").count()
    expiring_count = all_records.filter(status="Expiring Soon").count()
    expired_count = all_records.filter(status="Expired").count()
    critical_count = all_records.filter(remaining_days__gte=0, remaining_days__lte=5).count()

    # Search and filtering
    records = all_records
    q = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "").strip()
    paper_filter = request.GET.get("paper", "").strip()

    if q:
        records = records.filter(
            Q(vehicle_no__icontains=q)
            | Q(vehicle_name__icontains=q)
            | Q(custom_paper_name__icontains=q)
        )

    if status_filter:
        records = records.filter(status=status_filter)

    if paper_filter:
        records = records.filter(paper=paper_filter)

    # Critical records for page banner (expiring within 5 days)
    critical_records = all_records.filter(remaining_days__gte=0, remaining_days__lte=5)[:5]

    # Pagination: 10 items per page
    paginator = Paginator(records, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "records": page_obj,
        "page_obj": page_obj,
        "total_count": total_count,
        "active_count": active_count,
        "expiring_count": expiring_count,
        "expired_count": expired_count,
        "critical_count": critical_count,
        "critical_records": critical_records,
        "q": q,
        "selected_status": status_filter,
        "selected_paper": paper_filter,
        "paper_choices": LicenseRenewal.PAPER_CHOICES,
        "status_choices": LicenseRenewal.STATUS_CHOICES,
        "page_type": "license_renewal_view",
    }
    return render(request, "license_renewal/view_license_renewal.html", context)


def license_renewal_update(request, record_id=None):
    """
    Create a new license record or update an existing one.
    """
    record = get_object_or_404(LicenseRenewal, pk=record_id) if record_id else None

    if request.method == "POST":
        vehicle_no = request.POST.get("vehicle_no", "").strip().upper()
        vehicle_name = request.POST.get("vehicle_name", "").strip()
        paper = request.POST.get("paper", "RC").strip()
        custom_paper_name = request.POST.get("custom_paper_name", "").strip()
        expire_date_raw = request.POST.get("expire_date", "").strip()

        form_context = {
            "record": record,
            "vehicle_no": vehicle_no,
            "vehicle_name": vehicle_name,
            "paper": paper,
            "custom_paper_name": custom_paper_name,
            "expire_date": expire_date_raw,
            "paper_choices": LicenseRenewal.PAPER_CHOICES,
            "page_type": "license_renewal_update",
        }

        if paper == "Other" and not custom_paper_name:
            messages.error(request, "Please enter the custom paper category name.")
            return render(
                request,
                "license_renewal/update_license_renewal.html",
                form_context,
            )

        if not vehicle_no or not vehicle_name or not expire_date_raw:
            messages.error(request, "Please fill in all required fields.")
            return render(
                request,
                "license_renewal/update_license_renewal.html",
                form_context,
            )

        try:
            expire_date = date.fromisoformat(expire_date_raw)
        except ValueError:
            messages.error(request, "Please enter a valid date for expiry (YYYY-MM-DD).")
            return render(
                request,
                "license_renewal/update_license_renewal.html",
                form_context,
            )

        if record is None:
            record = LicenseRenewal()

        record.vehicle_no = vehicle_no
        record.vehicle_name = vehicle_name
        record.paper = paper
        record.custom_paper_name = custom_paper_name if paper == "Other" else ""
        record.expire_date = expire_date
        record.save()

        messages.success(
            request,
            f"License renewal for {record.vehicle_no} ({record.paper_display}) saved successfully.",
        )
        return redirect("license_renewal_view")

    context = {
        "record": record,
        "paper_choices": LicenseRenewal.PAPER_CHOICES,
        "page_type": "license_renewal_update",
    }
    return render(request, "license_renewal/update_license_renewal.html", context)


def license_renewal_delete(request, record_id):
    """
    Delete a license renewal record safely via POST.
    """
    record = get_object_or_404(LicenseRenewal, pk=record_id)
    if request.method == "POST":
        vehicle_info = f"{record.vehicle_no} ({record.paper_display})"
        record.delete()
        messages.success(request, f"License record for {vehicle_info} was deleted successfully.")
        return redirect("license_renewal_view")

    messages.error(request, "Invalid delete request method.")
    return redirect("license_renewal_view")
