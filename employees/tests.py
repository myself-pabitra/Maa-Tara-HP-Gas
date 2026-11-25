from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from employees.models import OperationalExpense
from SubDealers.models import PredefinedExpense


class OperationalExpenseTests(TestCase):
    def setUp(self):
        self.client = Client()
        User = get_user_model()
        self.user = User.objects.create_user(username="testuser", password="password")
        self.client.force_login(self.user)

        # Create sample predefined expense
        PredefinedExpense.objects.create(name="Office Tea", default_amount=Decimal("50.00"))

    def test_add_operational_expense_get(self):
        res = self.client.get(reverse("add_operational_expense"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Add Operational Expense")
        self.assertContains(res, "Vehicle Fuel / Diesel")
        self.assertContains(res, "Office Tea")

    def test_add_operational_expense_post_success(self):
        data = {
            "expense_date": "2026-11-20",
            "category_select": "Vehicle Fuel / Diesel",
            "custom_category": "",
            "amount": "2500.50",
            "payment_mode": "Cash",
            "reference_no": "WB-29-1234",
            "description": "50L Diesel for delivery truck",
        }
        res = self.client.post(reverse("add_operational_expense"), data=data)
        self.assertEqual(res.status_code, 302)

        expense = OperationalExpense.objects.first()
        self.assertIsNotNone(expense)
        self.assertEqual(expense.expense_date, date(2026, 11, 20))
        self.assertEqual(expense.category, "Vehicle Fuel / Diesel")
        self.assertEqual(expense.amount, Decimal("2500.50"))
        self.assertEqual(expense.payment_mode, "Cash")
        self.assertEqual(expense.reference_no, "WB-29-1234")
        self.assertEqual(expense.description, "50L Diesel for delivery truck")
        self.assertEqual(expense.created_by, self.user)

    def test_add_operational_expense_post_custom_category(self):
        data = {
            "expense_date": "2026-11-21",
            "category_select": "__other__",
            "custom_category": "Truck Tyre Replacement",
            "amount": "6000.00",
            "payment_mode": "Online/UPI",
            "reference_no": "MRF-INV-889",
            "description": "2 Rear Tyres replaced",
        }
        res = self.client.post(reverse("add_operational_expense"), data=data)
        self.assertEqual(res.status_code, 302)

        expense = OperationalExpense.objects.filter(category="Truck Tyre Replacement").first()
        self.assertIsNotNone(expense)
        self.assertEqual(expense.amount, Decimal("6000.00"))
        self.assertEqual(expense.payment_mode, "Online/UPI")

    def test_add_operational_expense_invalid_amount(self):
        data = {
            "expense_date": "2026-11-21",
            "category_select": "Vehicle Fuel / Diesel",
            "amount": "-500",
        }
        res = self.client.post(reverse("add_operational_expense"), data=data)
        self.assertEqual(res.status_code, 302)
        self.assertEqual(OperationalExpense.objects.count(), 0)

    def test_operational_expenses_history_and_category_breakdown(self):
        # Create multiple expenses across categories
        OperationalExpense.objects.create(
            expense_date=date(2026, 11, 5),
            category="Vehicle Fuel / Diesel",
            amount=Decimal("5000.00"),
            payment_mode="Cash",
            created_by=self.user,
        )
        OperationalExpense.objects.create(
            expense_date=date(2026, 11, 10),
            category="Vehicle Fuel / Diesel",
            amount=Decimal("3000.00"),
            payment_mode="Cash",
            created_by=self.user,
        )
        OperationalExpense.objects.create(
            expense_date=date(2026, 11, 15),
            category="Vehicle Tyres",
            amount=Decimal("4000.00"),
            payment_mode="Online/UPI",
            created_by=self.user,
        )

        res = self.client.get(reverse("operational_expenses_history"), {"month": "2026-11"})
        self.assertEqual(res.status_code, 200)

        # Total amount = 5000 + 3000 + 4000 = 12000
        self.assertEqual(res.context["total_amount"], Decimal("12000.00"))
        self.assertEqual(res.context["total_count"], 3)

        # Category breakdown: Fuel (8000, 66.7%), Tyres (4000, 33.3%)
        summary = res.context["category_summary"]
        self.assertEqual(len(summary), 2)
        self.assertEqual(summary[0]["category"], "Vehicle Fuel / Diesel")
        self.assertEqual(summary[0]["total"], Decimal("8000.00"))
        self.assertEqual(summary[0]["count"], 2)
        self.assertEqual(summary[0]["percentage"], 66.7)

        self.assertEqual(summary[1]["category"], "Vehicle Tyres")
        self.assertEqual(summary[1]["total"], Decimal("4000.00"))
        self.assertEqual(summary[1]["percentage"], 33.3)

    def test_operational_expenses_history_filters(self):
        OperationalExpense.objects.create(
            expense_date=date(2026, 10, 15),
            category="Vehicle Maintenance",
            amount=Decimal("1500.00"),
            description="Oil change",
        )
        OperationalExpense.objects.create(
            expense_date=date(2026, 11, 15),
            category="Vehicle Fuel / Diesel",
            amount=Decimal("2000.00"),
            description="Petrol pump diesel",
        )

        # Filter by category
        res = self.client.get(reverse("operational_expenses_history"), {"category": "Vehicle Maintenance", "month": "all"})
        self.assertEqual(res.context["total_count"], 1)
        self.assertEqual(res.context["total_amount"], Decimal("1500.00"))

        # Search query
        res_search = self.client.get(reverse("operational_expenses_history"), {"q": "diesel", "month": "all"})
        self.assertEqual(res_search.context["total_count"], 1)
        self.assertEqual(res_search.context["total_amount"], Decimal("2000.00"))

    def test_edit_operational_expense(self):
        expense = OperationalExpense.objects.create(
            expense_date=date(2026, 11, 1),
            category="Vehicle Fuel / Diesel",
            amount=Decimal("1000.00"),
            payment_mode="Cash",
        )

        edit_data = {
            "expense_date": "2026-11-02",
            "category_select": "Vehicle Maintenance",
            "amount": "1800.00",
            "payment_mode": "Online/UPI",
            "reference_no": "BILL-99",
            "description": "Brake servicing",
        }
        res = self.client.post(reverse("edit_operational_expense", args=[expense.id]), data=edit_data)
        self.assertEqual(res.status_code, 302)

        expense.refresh_from_db()
        self.assertEqual(expense.expense_date, date(2026, 11, 2))
        self.assertEqual(expense.category, "Vehicle Maintenance")
        self.assertEqual(expense.amount, Decimal("1800.00"))
        self.assertEqual(expense.payment_mode, "Online/UPI")
        self.assertEqual(expense.reference_no, "BILL-99")

    def test_delete_operational_expense(self):
        expense = OperationalExpense.objects.create(
            expense_date=date(2026, 11, 1),
            category="Chanda",
            amount=Decimal("200.00"),
        )
        res = self.client.post(reverse("delete_operational_expense", args=[expense.id]))
        self.assertEqual(res.status_code, 302)
        self.assertEqual(OperationalExpense.objects.filter(id=expense.id).count(), 0)
