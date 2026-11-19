from decimal import Decimal

from .models import DACEntry


def recalculate_balances(subdealer):

    balance = Decimal("0.00")

    entries = (
        DACEntry.objects
        .filter(subdealer=subdealer)
        .order_by("entry_date", "created_at", "id")
    )

    for entry in entries:

        entry.opening_balance = balance

        if entry.transaction_type == "CR":
            pct = (
                entry.dac_percentage_at_entry
                if entry.dac_percentage_at_entry is not None
                else (subdealer.dac_percentage or Decimal("100"))
            )
            credited_amount = (entry.transaction_quantity * pct / Decimal("100")).quantize(Decimal("0.01"))
            balance += credited_amount
        else:
            balance -= entry.transaction_quantity

        entry.closing_balance = balance.quantize(Decimal("0.01"))

        DACEntry.objects.filter(pk=entry.pk).update(
            opening_balance=entry.opening_balance,
            closing_balance=entry.closing_balance
        )