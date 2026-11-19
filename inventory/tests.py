from datetime import date, datetime, timedelta
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from inventory.models import ProductInventory, StockBatch
from SubDealers.models import Subdealer, DailyInvoice, DailyInvoiceLineItem


class DailyStockTrendTests(TestCase):
    def setUp(self):
        self.client = Client()
        User = get_user_model()
        self.user = User.objects.create_user(username="invtester", password="password")
        self.client.force_login(self.user)

        self.subdealer = Subdealer.objects.create(
            name="Test Subdealer",
            phone_number="9876543210",
            dac_percentage=Decimal("100.00"),
        )
        # Create product with 50 current stock
        self.product = ProductInventory.objects.create(
            product_name="14.2 KG Domestic",
            product_quantity=50,
            buy_price=Decimal("800.00"),
            product_price=Decimal("950.00"),
            in_stock=True,
        )

    def test_daily_stock_trend_page_loads(self):
        """Verify the daily_stock_trend view loads successfully."""
        response = self.client.get(reverse("daily_stock_trend"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "inventory/daily_stock_trend.html")
        self.assertIn("target_date_metrics", response.context)
        self.assertIn("daily_records", response.context)
        self.assertIn("all_products_snapshot", response.context)

    def test_exact_available_stock_on_specific_date(self):
        """
        Verify that stock available on a specific date is calculated exactly:
        Timeline:
        - 2026-08-01: Product starts with batch of 100 units
        - 2026-08-10: 20 units sold via invoice
        - 2026-08-15: 30 units added via batch top-up
        - 2026-08-20: 15 units sold via invoice
        Current stock in DB should be 100 - 20 + 30 - 15 = 95 units.
        """
        # Set current stock to 95
        self.product.product_quantity = 95
        self.product.save()

        # Batch 1 on 2026-08-01: 100 units
        b1 = StockBatch.objects.create(
            product=self.product,
            buy_price=Decimal("800.00"),
            quantity_added=100,
            quantity_remaining=100,
            notes="Initial batch",
        )
        StockBatch.objects.filter(id=b1.id).update(added_at=timezone.make_aware(datetime(2026, 8, 1, 10, 0, 0)))

        # Invoice 1 on 2026-08-10: 20 units
        inv1 = DailyInvoice.objects.create(invoice_date=date(2026, 8, 10))
        DailyInvoiceLineItem.objects.create(
            invoice=inv1,
            subdealer=self.subdealer,
            product=self.product,
            quantity=20,
            discounted_price=Decimal("950.00"),
            line_total=Decimal("19000.00"),
            buying_price=Decimal("16000.00"),
        )

        # Batch 2 on 2026-08-15: 30 units added
        b2 = StockBatch.objects.create(
            product=self.product,
            buy_price=Decimal("820.00"),
            quantity_added=30,
            quantity_remaining=30,
            notes="Second batch",
        )
        StockBatch.objects.filter(id=b2.id).update(added_at=timezone.make_aware(datetime(2026, 8, 15, 11, 0, 0)))

        # Invoice 2 on 2026-08-20: 15 units
        inv2 = DailyInvoice.objects.create(invoice_date=date(2026, 8, 20))
        DailyInvoiceLineItem.objects.create(
            invoice=inv2,
            subdealer=self.subdealer,
            product=self.product,
            quantity=15,
            discounted_price=Decimal("950.00"),
            line_total=Decimal("14250.00"),
            buying_price=Decimal("12300.00"),
        )

        # Check stock on 2026-08-10 (when 20 were sold):
        # Sales after 2026-08-10: 15 (on Aug 20)
        # Top-ups after 2026-08-10: 30 (on Aug 15)
        # Closing stock on Aug 10 = 95 + 15 - 30 = 80 units!
        # On Aug 10: Outward = 20, Inward = 0 -> Opening stock = 80 + 20 - 0 = 100 units!
        res_aug10 = self.client.get(reverse("daily_stock_trend"), {
            "product": self.product.id,
            "date": "2026-08-10",
        })
        m_aug10 = res_aug10.context["target_date_metrics"]
        self.assertEqual(m_aug10["opening_stock"], 100)
        self.assertEqual(m_aug10["outward"], 20)
        self.assertEqual(m_aug10["inward"], 0)
        self.assertEqual(m_aug10["closing_stock"], 80)

        # Check stock on 2026-08-15 (when 30 were added):
        # Sales after 2026-08-15: 15 (on Aug 20)
        # Top-ups after 2026-08-15: 0
        # Closing stock on Aug 15 = 95 + 15 - 0 = 110 units!
        # On Aug 15: Outward = 0, Inward = 30 -> Opening stock = 110 + 0 - 30 = 80 units!
        res_aug15 = self.client.get(reverse("daily_stock_trend"), {
            "product": self.product.id,
            "date": "2026-08-15",
        })
        m_aug15 = res_aug15.context["target_date_metrics"]
        self.assertEqual(m_aug15["opening_stock"], 80)
        self.assertEqual(m_aug15["inward"], 30)
        self.assertEqual(m_aug15["outward"], 0)
        self.assertEqual(m_aug15["closing_stock"], 110)

        # Check stock on 2026-08-20 (when 15 were sold):
        # Closing stock on Aug 20 = 95 + 0 - 0 = 95 units!
        # Opening stock on Aug 20 = 95 + 15 - 0 = 110 units!
        res_aug20 = self.client.get(reverse("daily_stock_trend"), {
            "product": self.product.id,
            "date": "2026-08-20",
        })
        m_aug20 = res_aug20.context["target_date_metrics"]
        self.assertEqual(m_aug20["opening_stock"], 110)
        self.assertEqual(m_aug20["outward"], 15)
        self.assertEqual(m_aug20["closing_stock"], 95)

    def test_all_products_snapshot_on_date(self):
        """Verify that all products snapshot returns each product's available stock on that date."""
        p2 = ProductInventory.objects.create(
            product_name="Commercial 19KG",
            product_quantity=40,
            buy_price=Decimal("1500.00"),
            product_price=Decimal("1800.00"),
            in_stock=True,
        )

        response = self.client.get(reverse("daily_stock_trend"), {
            "date": "2026-11-19",
        })
        self.assertEqual(response.status_code, 200)
        snapshot = response.context["all_products_snapshot"]
        product_ids_in_snapshot = [item["product"].id for item in snapshot]
        self.assertIn(self.product.id, product_ids_in_snapshot)
        self.assertIn(p2.id, product_ids_in_snapshot)
