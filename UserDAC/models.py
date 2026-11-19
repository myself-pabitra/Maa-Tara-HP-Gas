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

    # Snapshot of the subdealer's DAC % at the time this entry was created.
    # Stored only for CR entries so that changing the subdealer's DAC %
    # later never retroactively changes credited amounts on past entries.
    dac_percentage_at_entry = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )

    description = models.TextField(
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    @property
    def effective_quantity(self):
        """
        For CR entries, returns the actual credited quantity after applying snapshot DAC percentage.
        For DR entries, returns transaction_quantity.
        """
        if self.transaction_type == "CR":
            pct = (
                self.dac_percentage_at_entry
                if self.dac_percentage_at_entry is not None
                else (self.subdealer.dac_percentage or Decimal("100"))
            )
            return (self.transaction_quantity * pct / Decimal("100")).quantize(Decimal("0.01"))
        return self.transaction_quantity

    class Meta:
        db_table = "DACEntry"
        ordering = ["entry_date", "created_at"]

    def __str__(self):
        return f"{self.subdealer.name} - {self.get_transaction_type_display()} - {self.transaction_quantity}"