from datetime import date
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from SubDealers.models import Subdealer, DailyInvoice, DailyInvoiceLineItem
from inventory.models import ProductInventory
from UserDAC.models import DACEntry
from UserDAC.helpers import recalculate_balances


class DACTransactionAndIsolationTests(TestCase):
    def setUp(self):
        self.client = Client()
        User = get_user_model()
        self.user = User.objects.create_user(username="testuser", password="password")
        self.client.force_login(self.user)

        self.subdealer = Subdealer.objects.create(
            name="Test Subdealer",
            phone_number="9876543210",
            dac_percentage=Decimal("95.00"),
        )
        self.product = ProductInventory.objects.create(
            product_name="14.2 KG Domestic",
            product_price=Decimal("800.00"),
            buy_price=Decimal("750.00"),
            dac_applicable=True,
        )

    def test_dac_entry_snapshots_percentage_and_isolates_from_future_changes(self):
        """
        1. When a DAC CR entry is created, snapshot dac_percentage_at_entry is recorded.
        2. Updating subdealer.dac_percentage does NOT alter previous entry's snapshot.
        3. A new entry uses the new percentage.
        """
        # Create first entry via POST
        response = self.client.post(
            reverse("dac_entry"),
            {
                "subdealer_code": self.subdealer.subdealerCode,
                "dac_date": "2026-11-01",
                "transaction_type": "CR",
                "transaction_quantity": "15",
                "description": "Initial delivery",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.status_code, 302)

        entry1 = DACEntry.objects.filter(subdealer=self.subdealer, entry_date="2026-11-01").first()
        self.assertIsNotNone(entry1)
        self.assertEqual(entry1.dac_percentage_at_entry, Decimal("95.00"))

        # Update subdealer percentage to 100% in directory
        self.subdealer.dac_percentage = Decimal("100.00")
        self.subdealer.save()

        # Existing entry snapshot remains 95%
        entry1.refresh_from_db()
        self.assertEqual(entry1.dac_percentage_at_entry, Decimal("95.00"))

        # Create second entry with the new 100%
        response2 = self.client.post(
            reverse("dac_entry"),
            {
                "subdealer_code": self.subdealer.subdealerCode,
                "dac_date": "2026-11-10",
                "transaction_type": "CR",
                "transaction_quantity": "10",
                "description": "Second delivery at 100%",
            },
        )
        self.assertEqual(response2.status_code, 302)

        entry2 = DACEntry.objects.filter(subdealer=self.subdealer, entry_date="2026-11-10").first()
        self.assertEqual(entry2.dac_percentage_at_entry, Decimal("100.00"))

    def test_pending_dac_orders_calculation(self):
        """
        Test the user's specific scenario:
        1. Subdealer has a DAC entry of 15 cylinders @ 95% => credited = 14.25
        2. Previous month rolled over balance = 5.00  (10 CR - 5 DR in DACEntry)
        3. Available = 14.25 + 5.00 = 19.25
        4. Invoiced/dispatched this month = 12
        5. Final remaining = 19.25 - 12 = 7.25

        Source-of-truth: DACEntry records only (same as DAC Ledger / recalculate_balances).
        Invoice records are NOT used for balance calculation.
        """
        # Previous month: entry of 10 cylinders @ 100% on 2026-10-01
        DACEntry.objects.create(
            subdealer=self.subdealer,
            entry_date=date(2026, 10, 1),
            transaction_type="CR",
            transaction_quantity=Decimal("10.00"),
            dac_percentage_at_entry=Decimal("100.00"),
        )
        # Previous month DR (dispatch): 5 cylinders on 2026-10-15 — DACEntry is the source of truth
        DACEntry.objects.create(
            subdealer=self.subdealer,
            entry_date=date(2026, 10, 15),
            transaction_type="DR",
            transaction_quantity=Decimal("5.00"),
            description="Oct dispatch",
        )
        # Recalculate to set correct closing balances on Oct entries
        recalculate_balances(self.subdealer)
        # That leaves 10 - 5 = 5.00 rolled-over into November!

        # This month (November):
        # 15 cylinders @ 95% = 14.25 credited
        DACEntry.objects.create(
            subdealer=self.subdealer,
            entry_date=date(2026, 11, 2),
            transaction_type="CR",
            transaction_quantity=Decimal("15.00"),
            dac_percentage_at_entry=Decimal("95.00"),
        )

        # This month DR: 12 cylinders dispatched on 2026-11-05 — DACEntry source of truth
        DACEntry.objects.create(
            subdealer=self.subdealer,
            entry_date=date(2026, 11, 5),
            transaction_type="DR",
            transaction_quantity=Decimal("12.00"),
            description="Nov dispatch",
        )
        recalculate_balances(self.subdealer)

        # Call pending_dac_orders view for 2026-11
        response = self.client.get(reverse("pending_dac_orders"), {"month": "2026-11"})
        self.assertEqual(response.status_code, 200)

        rows = response.context["rows"]
        self.assertEqual(len(rows), 1)
        row = rows[0]

        # 1. Credited balance = 15 * 95% = 14.25
        self.assertEqual(row["this_month_raw_credit"], Decimal("15.00"))
        self.assertEqual(row["this_month_dac_credited"], Decimal("14.25"))

        # 2. Previous month rolled over balance = 10 CR - 5 DR = 5.00
        self.assertEqual(row["prev_month_balance"], Decimal("5.00"))

        # 3. Available = 14.25 + 5.00 = 19.25
        self.assertEqual(row["available_dac_balance"], Decimal("19.25"))

        # 4. Refills dispatched = 12 (from DACEntry DR)
        self.assertEqual(row["refills_this_month"], Decimal("12"))

        # 5. Final remaining = 19.25 - 12 = 7.25
        self.assertEqual(row["final_remaining"], Decimal("7.25"))

    def test_inactive_all_zero_subdealer_is_hidden_by_default(self):
        """
        Subdealers with all 0s and fulfilled should not clutter the Pending DAC Orders page.
        They should only show if explicitly searched/filtered.
        """
        # Create an inactive subdealer with 0 transactions
        inactive_subdealer = Subdealer.objects.create(
            name="Inactive Subdealer",
            phone_number="9111111111",
            dac_percentage=Decimal("95.00"),
        )

        response = self.client.get(reverse("pending_dac_orders"), {"month": "2026-11"})
        self.assertEqual(response.status_code, 200)

        # Inactive subdealer with all 0s is excluded from default view
        subdealer_ids_in_page = [r["subdealer"].id for r in response.context["rows"]]
        self.assertNotIn(inactive_subdealer.id, subdealer_ids_in_page)

        # When explicitly searched by subdealer filter, they are shown
        response_filtered = self.client.get(reverse("pending_dac_orders"), {"month": "2026-11", "subdealer": inactive_subdealer.id})
        self.assertEqual(response_filtered.status_code, 200)
        subdealer_ids_filtered = [r["subdealer"].id for r in response_filtered.context["rows"]]
        self.assertIn(inactive_subdealer.id, subdealer_ids_filtered)

    def test_dac_ledger_matches_pending_dac_orders(self):
        """
        Verify that DAC Ledger balances and Pending DAC Orders balances match.
        """
        # Create CR entry of 15 with 95% DAC
        res = self.client.post(
            reverse("dac_entry"),
            {
                "subdealer_code": self.subdealer.subdealerCode,
                "dac_date": "2026-11-02",
                "transaction_type": "CR",
                "transaction_quantity": "15",
                "description": "Test entry",
            },
        )
        self.assertEqual(res.status_code, 302)

        entry = DACEntry.objects.filter(subdealer=self.subdealer, entry_date="2026-11-02").first()
        self.assertEqual(entry.effective_quantity, Decimal("14.25"))
        self.assertEqual(entry.closing_balance, Decimal("14.25"))

        # In DAC Ledger view for 2026-11
        ledger_res = self.client.get(reverse("view_dac"), {"month": "2026-11", "subdealer": self.subdealer.id})
        self.assertEqual(ledger_res.status_code, 200)
        self.assertEqual(ledger_res.context["total_actual_cr"], Decimal("14.25"))

        # In Pending DAC Orders view for 2026-11
        pending_res = self.client.get(reverse("pending_dac_orders"), {"month": "2026-11", "subdealer": self.subdealer.id})
        self.assertEqual(pending_res.status_code, 200)
        row = pending_res.context["rows"][0]
        self.assertEqual(row["this_month_dac_credited"], Decimal("14.25"))
        self.assertEqual(row["this_month_raw_credit"], Decimal("15.00"))

    def test_negative_rollover_balance_matches_ledger_and_dac_entry(self):
        """
        Verify that negative balances from prior months carry forward properly
        into Previous Month Bal and Final Remaining Balance, matching New DAC Entry and DAC Ledger.
        Example (Giribala case):
        - Prior months: 54 cylinders delivered (DR), 0 credited -> -54.00 balance
        - Current month: 5 cylinders credited (at 100%), 7 delivered (DR)
        - Previous Month Bal = -54.00
        - Available = -54.00 + 5.00 = -49.00
        - Delivered = 7.00
        - Final Remaining = -49.00 - 7.00 = -56.00
        """
        sub = Subdealer.objects.create(
            name="Giribala Test Subdealer",
            phone_number="9222222222",
            dac_percentage=Decimal("100.00"),
        )
        # Prior month delivery: 54 cylinders on 2026-08-28
        e1 = DACEntry.objects.create(
            subdealer=sub,
            entry_date=date(2026, 8, 28),
            transaction_type="DR",
            transaction_quantity=Decimal("54.00"),
            description="Prior delivery",
        )
        recalculate_balances(sub)
        e1.refresh_from_db()
        self.assertEqual(e1.closing_balance, Decimal("-54.00"))

        # Current month: 5 CR and 7 DR on 2026-11-19
        e2 = DACEntry.objects.create(
            subdealer=sub,
            entry_date=date(2026, 11, 19),
            transaction_type="CR",
            transaction_quantity=Decimal("5.00"),
            dac_percentage_at_entry=Decimal("100.00"),
            description="Nov credit",
        )
        e3 = DACEntry.objects.create(
            subdealer=sub,
            entry_date=date(2026, 11, 19),
            transaction_type="DR",
            transaction_quantity=Decimal("7.00"),
            description="Nov delivery",
        )
        recalculate_balances(sub)
        e3.refresh_from_db()
        self.assertEqual(e3.closing_balance, Decimal("-56.00"))

        # Check Pending DAC Orders for 2026-11
        res = self.client.get(reverse("pending_dac_orders"), {"month": "2026-11", "subdealer": sub.id})
        self.assertEqual(res.status_code, 200)
        row = res.context["rows"][0]

        self.assertEqual(row["prev_month_balance"], Decimal("-54.00"))
        self.assertEqual(row["this_month_dac_credited"], Decimal("5.00"))
        self.assertEqual(row["available_dac_balance"], Decimal("-49.00"))
        self.assertEqual(row["refills_this_month"], Decimal("7.00"))
        self.assertEqual(row["final_remaining"], Decimal("-56.00"))

    def test_separate_year_and_month_filters(self):
        """
        Test that year and month work as separate filters:
        - When month is empty ('') and year is selected: returns all months for that year.
        - When both year and month are selected: filters to that specific month.
        - When neither is passed (first load): defaults to current year and current month.
        """
        sub = Subdealer.objects.create(
            name="Filter Test Subdealer",
            phone_number="9333333333",
            dac_percentage=Decimal("100.00"),
        )
        # Entry in August 2026
        DACEntry.objects.create(
            subdealer=sub,
            entry_date=date(2026, 8, 15),
            transaction_type="CR",
            transaction_quantity=Decimal("10.00"),
            dac_percentage_at_entry=Decimal("100.00"),
        )
        # Entry in November 2026
        DACEntry.objects.create(
            subdealer=sub,
            entry_date=date(2026, 11, 10),
            transaction_type="CR",
            transaction_quantity=Decimal("20.00"),
            dac_percentage_at_entry=Decimal("100.00"),
        )
        recalculate_balances(sub)

        # 1. view_dac with year=2026 and month='' (All Months)
        res_all = self.client.get(reverse("view_dac"), {"year": "2026", "month": "", "subdealer": sub.id})
        self.assertEqual(res_all.status_code, 200)
        self.assertEqual(res_all.context["total_entries_count"], 2)
        self.assertEqual(res_all.context["total_punched_cr"], Decimal("30.00"))

        # 2. view_dac with year=2026 and month='8' (August only)
        res_aug = self.client.get(reverse("view_dac"), {"year": "2026", "month": "8", "subdealer": sub.id})
        self.assertEqual(res_aug.status_code, 200)
        self.assertEqual(res_aug.context["total_entries_count"], 1)
        self.assertEqual(res_aug.context["total_punched_cr"], Decimal("10.00"))

        # 3. Pending_DAC_Orders with year=2026 and month='' (All Months)
        res_pending_all = self.client.get(reverse("pending_dac_orders"), {"year": "2026", "month": "", "subdealer": sub.id})
        self.assertEqual(res_pending_all.status_code, 200)
        row_all = res_pending_all.context["rows"][0]
        self.assertEqual(row_all["this_month_raw_credit"], Decimal("30.00"))

        # 4. Pending_DAC_Orders with year=2026 and month='11' (November only)
        res_pending_nov = self.client.get(reverse("pending_dac_orders"), {"year": "2026", "month": "11", "subdealer": sub.id})
        self.assertEqual(res_pending_nov.status_code, 200)
        row_nov = res_pending_nov.context["rows"][0]
        self.assertEqual(row_nov["this_month_raw_credit"], Decimal("20.00"))
        # Rolled over from August
        self.assertEqual(row_nov["prev_month_balance"], Decimal("10.00"))





