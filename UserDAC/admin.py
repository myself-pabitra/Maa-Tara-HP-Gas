from django.contrib import admin
from .models import DACEntry


@admin.register(DACEntry)
class DACEntryAdmin(admin.ModelAdmin):
    list_display = (
        'subdealer',
        'entry_date',
        'transaction_type',
        'transaction_quantity',
        'opening_balance',
        'closing_balance',
        'description',
        'created_at',
    )

    list_filter = (
        'transaction_type',
        'entry_date',
        'subdealer',
    )

    search_fields = (
        'subdealer__name',
        'description',
    )

    ordering = (
        '-entry_date',
        '-created_at',
    )

    readonly_fields = (
        'opening_balance',
        'closing_balance',
        'created_at',
        'updated_at',
    )