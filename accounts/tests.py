from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from license_renewal.models import LicenseRenewal


class DashboardViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="adminuser", password="password123")
        self.client = Client()
        self.client.force_login(self.user)

    def test_dashboard_renders_with_no_licenses(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard.html")
        self.assertIn("active_licenses", response.context)
        self.assertEqual(response.context["active_licenses"], 0)
        self.assertEqual(response.context["total_expiring_licenses_count"], 0)

    def test_dashboard_renders_with_expiring_licenses(self):
        LicenseRenewal.objects.create(
            vehicle_no="WB58A9999",
            vehicle_name="Delivery Truck 9",
            paper="Insurance",
            expire_date=date.today() + timedelta(days=2),
        )
        LicenseRenewal.objects.create(
            vehicle_no="WB58A8888",
            vehicle_name="Delivery Truck 8",
            paper="Fitness",
            expire_date=date.today() + timedelta(days=45),
        )
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["active_licenses"], 1)
        self.assertEqual(response.context["total_expiring_licenses_count"], 1)
        self.assertContains(response, "WB58A9999")
