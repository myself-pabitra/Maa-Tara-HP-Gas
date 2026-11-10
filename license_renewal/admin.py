from django.contrib import admin

from .models import LicenseRenewal


@admin.register(LicenseRenewal)
class LicenseRenewalAdmin(admin.ModelAdmin):
    list_display = (
        "vehicle_no",
        "vehicle_name",
        "paper_display",
        "expire_date",
        "remaining_days",
        "status",
    )
    list_filter = ("status", "paper")
    search_fields = ("vehicle_no", "vehicle_name", "custom_paper_name")
    ordering = ("expire_date",)
