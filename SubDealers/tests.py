from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from SubDealers.models import DailyInvoice, DailyInvoiceLineItem, Subdealer
from UserDAC.models import DACEntry
from UserDAC.helpers import recalculate_balances
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


class SubdealerAuditLogTests(TestCase):
    def setUp(self):
        self.client = Client()
        User = get_user_model()
        self.user = User.objects.create_user(username="audituser", password="password")
        self.client.force_login(self.user)

    def test_subdealer_creation_logs_audit_entry(self):
        response = self.client.post(
            reverse("CreateNewSubDealers"),
            {
                "name": "New Partner",
                "phone_number": "9876500000",
                "address": "Market Complex",
                "dac_percentage": "95.00",
            },
        )
        self.assertEqual(response.status_code, 302)

        from SubDealers.models import SubdealerAuditLog
        sub = Subdealer.objects.filter(name="New Partner").first()
        self.assertIsNotNone(sub)

        log = SubdealerAuditLog.objects.filter(subdealer=sub, change_type="CREATED").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.new_dac_percentage, Decimal("95.00"))
        self.assertEqual(log.changed_by, self.user)

    def test_dac_percentage_change_logs_audit_entry_and_preserves_old_entries(self):
        sub = Subdealer.objects.create(
            name="Testing Partner",
            phone_number="9876511111",
            address="Village 1",
            dac_percentage=Decimal("90.00"),
        )

        # 1. First DAC entry at 90%
        entry1 = DACEntry.objects.create(
            subdealer=sub,
            entry_date=date(2026, 11, 1),
            transaction_type="CR",
            transaction_quantity=Decimal("10.00"),
            dac_percentage_at_entry=Decimal("90.00"),
        )
        recalculate_balances(sub)
        entry1.refresh_from_db()
        self.assertEqual(entry1.effective_quantity, Decimal("9.00"))
        self.assertEqual(entry1.closing_balance, Decimal("9.00"))

        # 2. Update DAC % from 90% to 95% via edit_subdealer view
        res = self.client.post(
            reverse("edit_subdealer", args=[sub.id]),
            {
                "name": "Testing Partner",
                "phone_number": "9876511111",
                "address": "Village 1 Updated",
                "dac_percentage": "95.00",
            },
        )
        self.assertEqual(res.status_code, 302)

        sub.refresh_from_db()
        self.assertEqual(sub.dac_percentage, Decimal("95.00"))

        from SubDealers.models import SubdealerAuditLog
        audit = SubdealerAuditLog.objects.filter(subdealer=sub, change_type="DAC_PERCENTAGE").first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.old_dac_percentage, Decimal("90.00"))
        self.assertEqual(audit.new_dac_percentage, Decimal("95.00"))
        self.assertEqual(audit.changed_by, self.user)

        # 3. Second DAC entry created after the change -> uses 95%
        entry2 = DACEntry.objects.create(
            subdealer=sub,
            entry_date=date(2026, 11, 20),
            transaction_type="CR",
            transaction_quantity=Decimal("10.00"),
            dac_percentage_at_entry=sub.dac_percentage,
        )
        recalculate_balances(sub)

        # 4. Verify historical entry remained at 9.00 and new entry is 9.50
        entry1.refresh_from_db()
        entry2.refresh_from_db()
        self.assertEqual(entry1.effective_quantity, Decimal("9.00"))
        self.assertEqual(entry2.effective_quantity, Decimal("9.50"))
        self.assertEqual(entry2.closing_balance, Decimal("18.50"))

    def test_audit_logs_view_filtering(self):
        sub = Subdealer.objects.create(
            name="Filter Partner",
            phone_number="9876522222",
            dac_percentage=Decimal("100.00"),
        )
        from SubDealers.models import SubdealerAuditLog
        SubdealerAuditLog.objects.create(
            subdealer=sub,
            subdealer_name=sub.name,
            subdealer_code=sub.subdealerCode,
            changed_by=self.user,
            change_type="DAC_PERCENTAGE",
            old_dac_percentage=Decimal("100.00"),
            new_dac_percentage=Decimal("95.00"),
            details="Annual revision",
        )

        res = self.client.get(reverse("subdealer_audit_logs"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Filter Partner")
        self.assertContains(res, "95")

        # Filter by subdealer
        res_filtered = self.client.get(reverse("subdealer_audit_logs"), {"subdealer": sub.id})
        self.assertEqual(res_filtered.status_code, 200)
        self.assertContains(res_filtered, "Filter Partner")


class InvoiceEditAndDACReconcileTests(TestCase):
    def setUp(self):
        self.client = Client()
        User = get_user_model()
        self.user = User.objects.create_user(username="invuser", password="password")
        self.client.force_login(self.user)

        self.subdealer1 = Subdealer.objects.create(
            name="Subdealer One",
            phone_number="9876543210",
            dac_percentage=Decimal("95.00"),
        )
        self.subdealer2 = Subdealer.objects.create(
            name="Subdealer Two",
            phone_number="9876543211",
            dac_percentage=Decimal("100.00"),
        )
        self.product = ProductInventory.objects.create(
            product_name="14.2kg Cylinder",
            productCode="14CY",
            product_quantity=50,
            product_price=Decimal("950.00"),
            buy_price=Decimal("800.00"),
            dac_applicable=True,
            in_stock=True,
        )

    def test_edit_invoice_multiple_lines_same_product_reverts_stock_correctly(self):
        # Create an invoice with 2 lines for the same product: 15 cyl and 20 cyl (total 35)
        # Initial stock was 50, so remaining stock should be 15
        create_data = {
            "invoice_date": "2026-11-11",
            "product_code[]": [self.product.productCode, self.product.productCode],
            "subdealer_code[]": [self.subdealer1.subdealerCode, self.subdealer2.subdealerCode],
            "quantity[]": ["15", "20"],
            "submitted_blank[]": ["15", "20"],
            "discounted_price[]": ["950.00", "950.00"],
            "line_total[]": ["14250.00", "19000.00"],
            "due_cyl[]": ["0", "0"],
            "payment_mode[]": ["Cash", "Cash"],
            "cash_amount[]": ["14250.00", "19000.00"],
            "ac_amount[]": ["0", "0"],
            "remarks[]": ["", ""],
            "buying_price[]": ["12000.00", "16000.00"],
        }
        res_create = self.client.post(reverse("create_daily_sell_invoice"), data=create_data)
        self.assertEqual(res_create.status_code, 302)

        self.product.refresh_from_db()
        self.assertEqual(self.product.product_quantity, 15)

        invoice = DailyInvoice.objects.latest("id")

        # Edit invoice without changing quantities - stock must revert 15+20=35 (back to 50),
        # then re-deduct 35, remaining at 15 without throwing InsufficientStock error.
        edit_data = {
            "invoice_date": "2026-11-11",
            "product_code[]": [self.product.productCode, self.product.productCode],
            "subdealer_code[]": [self.subdealer1.subdealerCode, self.subdealer2.subdealerCode],
            "quantity[]": ["15", "20"],
            "submitted_blank[]": ["15", "20"],
            "discounted_price[]": ["950.00", "950.00"],
            "line_total[]": ["14250.00", "19000.00"],
            "due_cyl[]": ["0", "0"],
            "payment_mode[]": ["Cash", "Cash"],
            "cash_amount[]": ["14250.00", "19000.00"],
            "ac_amount[]": ["0", "0"],
            "remarks[]": ["", ""],
            "buying_price[]": ["12000.00", "16000.00"],
        }
        res_edit = self.client.post(
            reverse("edit_daily_sell_invoice", args=[invoice.id]),
            data=edit_data,
        )
        self.assertEqual(res_edit.status_code, 302)
        self.product.refresh_from_db()
        self.assertEqual(self.product.product_quantity, 15)

    def test_edit_invoice_form_error_re_render_does_not_raise_strftime_attribute_error(self):
        # Create a simple invoice
        invoice = DailyInvoice.objects.create(
            invoice_date="2026-11-11",
            payment_mode="Cash",
        )

        # Submit invalid POST data that triggers ValueError inside the atomic block
        bad_data = {
            "invoice_date": "2026-11-11",
            "product_code[]": [self.product.productCode],
            # missing subdealer_code[] to trigger array length inconsistency ValueError
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
        # This should re-render the page (status 200) with error message and NOT crash with AttributeError on strftime
        res = self.client.post(
            reverse("edit_daily_sell_invoice", args=[invoice.id]),
            data=bad_data,
        )
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Could not update invoice:")

    def test_edit_invoice_creates_missing_dac_for_undebited_subdealer(self):
        # Simulate an invoice where a line item was saved historically without creating a DACEntry
        invoice = DailyInvoice.objects.create(
            invoice_date=date(2026, 11, 11),
            payment_mode="Mixed",
        )
        DailyInvoiceLineItem.objects.create(
            invoice=invoice,
            subdealer=self.subdealer2,
            product=self.product,
            quantity=9,
            submitted_blank=9,
            discounted_price=Decimal("950.00"),
            line_total=Decimal("8550.00"),
            buying_price=Decimal("7200.00"),
            payment_mode="Mixed",
            payment_status="PENDING",
            cash_amount=Decimal("6000.00"),
            ac_amount=Decimal("2550.00"),
        )

        # Verify subdealer2 initially has NO DACEntry
        self.assertEqual(DACEntry.objects.filter(subdealer=self.subdealer2).count(), 0)

        # Now editing and saving the invoice
        edit_data = {
            "invoice_date": "2026-11-11",
            "product_code[]": [self.product.productCode],
            "subdealer_code[]": [self.subdealer2.subdealerCode],
            "quantity[]": ["9"],
            "submitted_blank[]": ["9"],
            "discounted_price[]": ["950.00"],
            "line_total[]": ["8550.00"],
            "due_cyl[]": ["0"],
            "payment_mode[]": ["Mixed"],
            "cash_amount[]": ["6000.00"],
            "ac_amount[]": ["2550.00"],
            "remarks[]": [""],
            "buying_price[]": ["7200.00"],
        }
        res = self.client.post(
            reverse("edit_daily_sell_invoice", args=[invoice.id]),
            data=edit_data,
        )
        self.assertEqual(res.status_code, 302)

        # Verify DACEntry DR is now created for subdealer2
        entries = DACEntry.objects.filter(subdealer=self.subdealer2)
        self.assertEqual(entries.count(), 1)
        dr = entries.first()
        self.assertEqual(dr.transaction_type, "DR")
        self.assertEqual(dr.transaction_quantity, Decimal("9.00"))
        self.assertEqual(dr.closing_balance, Decimal("-9.00"))

    def test_recalculate_all_dac_sync_invoices_command(self):
        from django.core.management import call_command
        # Create invoice line item without DACEntry
        invoice = DailyInvoice.objects.create(
            invoice_date=date(2026, 11, 11),
            payment_mode="Cash",
        )
        DailyInvoiceLineItem.objects.create(
            invoice=invoice,
            subdealer=self.subdealer2,
            product=self.product,
            quantity=9,
            submitted_blank=9,
            discounted_price=Decimal("950.00"),
            line_total=Decimal("8550.00"),
            buying_price=Decimal("7200.00"),
            payment_mode="Cash",
            payment_status="PAID",
            cash_amount=Decimal("8550.00"),
            ac_amount=Decimal("0.00"),
        )

        self.assertEqual(DACEntry.objects.filter(subdealer=self.subdealer2).count(), 0)

        # Run command with --sync-invoices
        call_command("recalculate_all_dac", "--sync-invoices")

        # Verify entry was created and balance recalculated
        entries = DACEntry.objects.filter(subdealer=self.subdealer2)
        self.assertEqual(entries.count(), 1)
        dr = entries.first()
        self.assertEqual(dr.transaction_type, "DR")
        self.assertEqual(dr.transaction_quantity, Decimal("9.00"))
        self.assertEqual(dr.closing_balance, Decimal("-9.00"))


