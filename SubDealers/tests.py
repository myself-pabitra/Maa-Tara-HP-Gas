from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from SubDealers.models import DailyInvoice, DailyInvoiceLineItem, Subdealer
from UserDAC.models import DACEntry
from inventory.models import ProductInventory


class InvoiceUpdateDACTests(TestCase):
    def setUp(self):
        self.client = Client()
        User = get_user_model()
        self.user = User.objects.create_user(username="testadmin", password="password123")
        self.client.force_login(self.user)

        self.subdealer1 = Subdealer.objects.create(
            name="Subdealer One",
            phone_number="9876543211",
            address="Address 1",
            dac_percentage=Decimal("100.00"),
        )
        self.subdealer2 = Subdealer.objects.create(
            name="Subdealer Two",
            phone_number="9876543212",
            address="Address 2",
            dac_percentage=Decimal("100.00"),
        )

        self.product = ProductInventory.objects.create(
            product_name="14.2 KG Domestic",
            product_quantity=100,
            buy_price=Decimal("800.00"),
            product_price=Decimal("950.00"),
            in_stock=True,
            dac_applicable=True,
            submission_required=True,
        )

    def test_invoice_creation_debits_dac_correctly(self):
        """Creating an invoice creates DR entry for DAC applicable product."""
        post_data = {
            "invoice_date": "2026-11-19",
            "product_code[]": [self.product.productCode],
            "subdealer_code[]": [self.subdealer1.subdealerCode],
            "quantity[]": ["10"],
            "submitted_blank[]": ["10"],
            "discounted_price[]": ["950.00"],
            "line_total[]": ["9500.00"],
            "due_cyl[]": ["0"],
            "payment_mode[]": ["Cash"],
            "cash_amount[]": ["9500.00"],
            "ac_amount[]": ["0"],
            "remarks[]": [""],
            "buying_price[]": ["8000.00"],
        }
        response = self.client.post(reverse("create_daily_sell_invoice"), data=post_data)
        self.assertEqual(response.status_code, 302)

        invoice = DailyInvoice.objects.latest("id")
        self.assertEqual(invoice.line_items.count(), 1)

        # Check Subdealer 1 DACEntry
        entries1 = DACEntry.objects.filter(subdealer=self.subdealer1)
        self.assertEqual(entries1.count(), 1)
        entry1 = entries1.first()
        self.assertEqual(entry1.transaction_type, "DR")
        self.assertEqual(entry1.transaction_quantity, Decimal("10.00"))
        self.assertEqual(entry1.closing_balance, Decimal("-10.00"))

        # Check stock reduced to 90
        self.product.refresh_from_db()
        self.assertEqual(self.product.product_quantity, 90)

    def test_invoice_update_swaps_subdealer_and_recalculates_dac(self):
        """
        When updating an invoice where subdealer 1 was mistakenly billed instead of subdealer 2:
        - Subdealer 1's debit is completely removed, restoring balance to 0.
        - Subdealer 2 gets debited with closing balance -10.
        - Product inventory stock is preserved (no double-deduction).
        """
        # Step 1: Create initial invoice with Subdealer 1
        create_data = {
            "invoice_date": "2026-11-19",
            "product_code[]": [self.product.productCode],
            "subdealer_code[]": [self.subdealer1.subdealerCode],
            "quantity[]": ["10"],
            "submitted_blank[]": ["10"],
            "discounted_price[]": ["950.00"],
            "line_total[]": ["9500.00"],
            "due_cyl[]": ["0"],
            "payment_mode[]": ["Cash"],
            "cash_amount[]": ["9500.00"],
            "ac_amount[]": ["0"],
            "remarks[]": [""],
            "buying_price[]": ["8000.00"],
        }
        res_create = self.client.post(reverse("create_daily_sell_invoice"), data=create_data)
        self.assertEqual(res_create.status_code, 302)

        invoice = DailyInvoice.objects.latest("id")
        self.product.refresh_from_db()
        self.assertEqual(self.product.product_quantity, 90)

        # Step 2: Edit invoice, changing subdealer from Subdealer 1 to Subdealer 2
        update_data = {
            "invoice_date": "2026-11-19",
            "product_code[]": [self.product.productCode],
            "subdealer_code[]": [self.subdealer2.subdealerCode],
            "quantity[]": ["10"],
            "submitted_blank[]": ["10"],
            "discounted_price[]": ["950.00"],
            "line_total[]": ["9500.00"],
            "due_cyl[]": ["0"],
            "payment_mode[]": ["Cash"],
            "cash_amount[]": ["9500.00"],
            "ac_amount[]": ["0"],
            "remarks[]": [""],
            "buying_price[]": ["8000.00"],
        }
        res_update = self.client.post(
            reverse("edit_daily_sell_invoice", args=[invoice.id]),
            data=update_data,
        )
        self.assertEqual(res_update.status_code, 302)

        # Step 3: Verify Subdealer 1 has the original DR entry AND a CR Refund transaction
        entries_sub1 = DACEntry.objects.filter(subdealer=self.subdealer1).order_by("created_at")
        self.assertEqual(entries_sub1.count(), 2)

        dr_entry = entries_sub1.filter(transaction_type="DR").first()
        self.assertEqual(dr_entry.transaction_quantity, Decimal("10.00"))

        refund_entry = entries_sub1.filter(transaction_type="CR").first()
        self.assertEqual(refund_entry.transaction_quantity, Decimal("10.00"))
        self.assertIn("Refund:", refund_entry.description)
        self.assertIn("Subdealer Two", refund_entry.description)
        self.assertEqual(refund_entry.dac_percentage_at_entry, Decimal("100.00"))
        # Net balance for Subdealer 1 is restored to 0
        self.assertEqual(refund_entry.closing_balance, Decimal("0.00"))

        # Step 4: Verify Subdealer 2 has the DAC DR entry and balance is -10
        entries_sub2 = DACEntry.objects.filter(subdealer=self.subdealer2)
        self.assertEqual(entries_sub2.count(), 1)
        e2 = entries_sub2.first()
        self.assertEqual(e2.transaction_type, "DR")
        self.assertEqual(e2.transaction_quantity, Decimal("10.00"))
        self.assertEqual(e2.closing_balance, Decimal("-10.00"))
        self.assertIn("Reconciled from Subdealer One", e2.description)

        # Step 5: Verify product inventory is still 90 (reverted 10 then deducted 10)
        self.product.refresh_from_db()
        self.assertEqual(self.product.product_quantity, 90)
