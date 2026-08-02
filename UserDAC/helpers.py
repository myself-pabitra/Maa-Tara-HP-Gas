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
            balance += entry.transaction_quantity
        else:
            balance -= entry.transaction_quantity

        entry.closing_balance = balance

        DACEntry.objects.filter(pk=entry.pk).update(
            opening_balance=entry.opening_balance,
            closing_balance=entry.closing_balance
        )