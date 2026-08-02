from decimal import Decimal

from django.db import models

from SubDealers.models import Subdealer


class DACEntry(models.Model):

    TRANSACTION_TYPES = (
        ("CR", "Credit"),
        ("DR", "Debit"),
    )

    subdealer = models.ForeignKey(
        Subdealer,
        on_delete=models.CASCADE,
        related_name="dac_entries"
    )

    entry_date = models.DateField()

    transaction_type = models.CharField(
        max_length=2,
        choices=TRANSACTION_TYPES
    )

    transaction_quantity = models.DecimalField(
        max_digits=14,
        decimal_places=2
    )

    opening_balance = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        editable=False
    )

    closing_balance = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        editable=False
    )

    description = models.TextField(
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "DACEntry"
        ordering = ["entry_date", "created_at"]

    def __str__(self):
        return f"{self.subdealer.name} - {self.get_transaction_type_display()} - {self.transaction_quantity}"