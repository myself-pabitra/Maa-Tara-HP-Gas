from collections import defaultdict
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import models, transaction
from SubDealers.models import DailyInvoiceLineItem, Subdealer
from UserDAC.models import DACEntry
from UserDAC.helpers import recalculate_balances


class Command(BaseCommand):
    help = "Populate DAC percentage snapshots on all entries and recalculate all balances cleanly."

    def add_arguments(self, parser):
        parser.add_argument(
            "--sync-invoices",
            action="store_true",
            help="Scan all invoices for DAC-applicable items and create missing DR entries before recalculating balances.",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Starting complete DAC ledger recalculation..."))

        subdealers = Subdealer.objects.all().order_by("name")
        total_subdealers = subdealers.count()

        with transaction.atomic():
            # 0. Sync missing invoice DAC entries if requested
            if options.get("sync_invoices"):
                self.stdout.write("Scanning invoices for missing DAC debits...")
                required_dr = defaultdict(lambda: {"qty": Decimal("0"), "date": None, "subdealer": None, "invoice_number": None})
                for li in DailyInvoiceLineItem.objects.filter(product__dac_applicable=True).select_related("invoice", "subdealer"):
                    if li.quantity > 0 and li.subdealer:
                        key = (li.invoice.invoice_number, li.subdealer_id)
                        required_dr[key]["qty"] += Decimal(li.quantity)
                        required_dr[key]["date"] = li.invoice.invoice_date
                        required_dr[key]["subdealer"] = li.subdealer
                        required_dr[key]["invoice_number"] = li.invoice.invoice_number

                existing_dr = defaultdict(Decimal)
                for de in DACEntry.objects.filter(models.Q(description__contains="INV-")).select_related("subdealer"):
                    for part in de.description.split():
                        if part.startswith("INV-"):
                            inv_num = part.rstrip("),.:")
                            if de.transaction_type == "DR":
                                existing_dr[(inv_num, de.subdealer_id)] += Decimal(de.transaction_quantity)
                            elif de.transaction_type == "CR":
                                existing_dr[(inv_num, de.subdealer_id)] -= Decimal(de.transaction_quantity)
                            break

                synced_count = 0
                for (inv_num, sub_id), req_data in required_dr.items():
                    act_qty = existing_dr.get((inv_num, sub_id), Decimal("0"))
                    diff = req_data["qty"] - act_qty
                    if diff > 0:
                        DACEntry.objects.create(
                            subdealer=req_data["subdealer"],
                            entry_date=req_data["date"],
                            transaction_type="DR",
                            transaction_quantity=diff,
                            description=f"Invoice {inv_num}",
                        )
                        synced_count += 1
                        self.stdout.write(self.style.SUCCESS(
                            f"Created missing DR entry for {req_data['subdealer'].name} on {inv_num}: Qty {diff}"
                        ))
                self.stdout.write(f"Synchronized {synced_count} missing invoice DAC entries.")

            # 1. Populate dac_percentage_at_entry for all CR entries that don't have it
            refund_count = DACEntry.objects.filter(
                transaction_type="CR",
                description__icontains="refund",
                dac_percentage_at_entry__isnull=True,
            ).update(dac_percentage_at_entry=Decimal("100.00"))

            self.stdout.write(f"Updated {refund_count} invoice refund entries to 100% snapshot.")

            for s in subdealers:
                pct = s.dac_percentage if s.dac_percentage is not None else Decimal("100.00")
                DACEntry.objects.filter(
                    subdealer=s,
                    transaction_type="CR",
                    dac_percentage_at_entry__isnull=True,
                ).exclude(
                    description__icontains="refund"
                ).update(dac_percentage_at_entry=pct)

            # 2. Recalculate balances for all subdealers
            for s in subdealers:
                recalculate_balances(s)

        # 3. Validation step: check mathematical consistency across all entries
        all_entries = DACEntry.objects.select_related("subdealer").order_by("subdealer_id", "entry_date", "created_at", "id")
        math_errors = 0
        current_sub = None
        expected_balance = Decimal("0.00")

        for entry in all_entries:
            if current_sub != entry.subdealer_id:
                current_sub = entry.subdealer_id
                expected_balance = Decimal("0.00")

            if entry.opening_balance != expected_balance:
                math_errors += 1
                self.stdout.write(self.style.ERROR(
                    f"Chain error on entry #{entry.id} ({entry.subdealer.name}): open={entry.opening_balance}, exp={expected_balance}"
                ))

            if entry.transaction_type == "CR":
                pct = (
                    entry.dac_percentage_at_entry
                    if entry.dac_percentage_at_entry is not None
                    else (entry.subdealer.dac_percentage or Decimal("100"))
                )
                credited = (entry.transaction_quantity * pct / Decimal("100")).quantize(Decimal("0.01"))
                expected_balance += credited
            else:
                expected_balance -= entry.transaction_quantity

            expected_balance = expected_balance.quantize(Decimal("0.01"))

            if entry.closing_balance != expected_balance:
                math_errors += 1
                self.stdout.write(self.style.ERROR(
                    f"Math error on entry #{entry.id} ({entry.subdealer.name}): close={entry.closing_balance}, exp={expected_balance}"
                ))

        if math_errors == 0:
            self.stdout.write(self.style.SUCCESS(
                f"VALIDATION PASSED: All {all_entries.count()} entries across {total_subdealers} subdealers are 100% mathematically consistent!"
            ))
        else:
            self.stdout.write(self.style.ERROR(f"Validation found {math_errors} issues."))

        # 4. Display sample key subdealers
        key_names = ["Tarun Da", "Noni Barman", "Giribala", "Swadesh", "Mukta"]
        self.stdout.write("\nKey Subdealer Status:")
        self.stdout.write(f"{'Subdealer':<18} | {'DAC %':<6} | {'Total Entries':<13} | {'Closing Balance':<15}")
        self.stdout.write("-" * 60)
        for name in key_names:
            sd = Subdealer.objects.filter(name__icontains=name).first()
            if sd:
                latest = DACEntry.objects.filter(subdealer=sd).order_by("-entry_date", "-created_at", "-id").first()
                count = DACEntry.objects.filter(subdealer=sd).count()
                bal = latest.closing_balance if latest else Decimal("0.00")
                self.stdout.write(f"{sd.name:<18} | {sd.dac_percentage:>4.0f}% | {count:>13} | {bal:>15.2f}")
