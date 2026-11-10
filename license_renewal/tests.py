from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from .models import LicenseRenewal
from .views import add_expiry_reminders


class LicenseRenewalModelTests(TestCase):
    def test_license_renewal_requires_expected_fields(self):
        self.assertTrue(hasattr(LicenseRenewal, "vehicle_no"))
        self.assertTrue(hasattr(LicenseRenewal, "vehicle_name"))
        self.assertTrue(hasattr(LicenseRenewal, "paper"))
        self.assertTrue(hasattr(LicenseRenewal, "expire_date"))
        self.assertTrue(hasattr(LicenseRenewal, "remaining_days"))
        self.assertTrue(hasattr(LicenseRenewal, "status"))

    def test_remaining_days_are_calculated_from_expire_date(self):
        record = LicenseRenewal(
            vehicle_no="MH12AB1234",
            vehicle_name="Truck",
            paper="RC",
            expire_date=date.today() + timedelta(days=12),
        )

        self.assertEqual(record.calculate_remaining_days(), 12)
        record.update_status()
        self.assertEqual(record.remaining_days, 12)
        self.assertEqual(record.status, "Expiring Soon")

    def test_string_expire_date_is_supported(self):
        record = LicenseRenewal(
            vehicle_no="MH12AB1234",
            vehicle_name="Truck",
            paper="RC",
            expire_date=(date.today() + timedelta(days=5)).isoformat(),
        )

        self.assertEqual(record.calculate_remaining_days(), 5)
        record.update_status()
        self.assertEqual(record.remaining_days, 5)

    def test_paper_display_for_standard_and_custom(self):
        rc_record = LicenseRenewal(
            vehicle_no="WB58A1111",
            vehicle_name="Van 1",
            paper="RC",
            expire_date=date.today() + timedelta(days=60),
        )
        self.assertEqual(rc_record.paper_display, "RC")

        other_record = LicenseRenewal(
            vehicle_no="WB58A2222",
            vehicle_name="Van 2",
            paper="Other",
            custom_paper_name="Road Tax Permit",
            expire_date=date.today() + timedelta(days=60),
        )
        self.assertEqual(other_record.paper_display, "Road Tax Permit")

    def test_update_status_expired_and_active(self):
        expired_record = LicenseRenewal(
            vehicle_no="WB58A3333",
            vehicle_name="Truck 3",
            paper="Fitness",
            expire_date=date.today() - timedelta(days=5),
        )
        expired_record.update_status()
        self.assertEqual(expired_record.status, "Expired")

        active_record = LicenseRenewal(
            vehicle_no="WB58A4444",
            vehicle_name="Truck 4",
            paper="Insurance",
            expire_date=date.today() + timedelta(days=90),
        )
        active_record.update_status()
        self.assertEqual(active_record.status, "Active")


class LicenseRenewalViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testadmin", password="password123")
        self.client = Client()
        self.client.force_login(self.user)

        self.record1 = LicenseRenewal.objects.create(
            vehicle_no="WB58AB1001",
            vehicle_name="Tata 407 Delivery",
            paper="RC",
            expire_date=date.today() + timedelta(days=60),
        )
        self.record2 = LicenseRenewal.objects.create(
            vehicle_no="WB58AB1002",
            vehicle_name="E-Rickshaw 01",
            paper="Insurance",
            expire_date=date.today() + timedelta(days=10),
        )
        self.record3 = LicenseRenewal.objects.create(
            vehicle_no="WB58AB1003",
            vehicle_name="Mahindra Bolero",
            paper="Fitness",
            expire_date=date.today() - timedelta(days=3),
        )

    def test_license_renewal_view_renders_successfully(self):
        response = self.client.get(reverse("license_renewal_view"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "license_renewal/view_license_renewal.html")
        self.assertIn("records", response.context)
        self.assertEqual(response.context["total_count"], 3)
        self.assertEqual(response.context["active_count"], 1)
        self.assertEqual(response.context["expiring_count"], 1)
        self.assertEqual(response.context["expired_count"], 1)

    def test_license_renewal_view_filtering_by_status(self):
        response = self.client.get(reverse("license_renewal_view") + "?status=Expiring+Soon")
        self.assertEqual(response.status_code, 200)
        records_list = list(response.context["records"])
        self.assertEqual(len(records_list), 1)
        self.assertEqual(records_list[0].vehicle_no, "WB58AB1002")

    def test_license_renewal_view_filtering_by_search(self):
        response = self.client.get(reverse("license_renewal_view") + "?q=Tata")
        self.assertEqual(response.status_code, 200)
        records_list = list(response.context["records"])
        self.assertEqual(len(records_list), 1)
        self.assertEqual(records_list[0].vehicle_no, "WB58AB1001")

    def test_license_renewal_update_get_new(self):
        response = self.client.get(reverse("license_renewal_update"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "license_renewal/update_license_renewal.html")
        self.assertIsNone(response.context["record"])

    def test_license_renewal_update_get_edit(self):
        response = self.client.get(
            reverse("license_renewal_update_record", args=[self.record1.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "license_renewal/update_license_renewal.html")
        self.assertEqual(response.context["record"], self.record1)

    def test_license_renewal_create_post_success(self):
        post_data = {
            "vehicle_no": "wb58cd9999",
            "vehicle_name": "New Delivery Van",
            "paper": "Permit",
            "expire_date": (date.today() + timedelta(days=120)).strftime("%Y-%m-%d"),
        }
        response = self.client.post(reverse("license_renewal_update"), data=post_data)
        self.assertRedirects(response, reverse("license_renewal_view"))

        created = LicenseRenewal.objects.get(vehicle_no="WB58CD9999")
        self.assertEqual(created.vehicle_name, "New Delivery Van")
        self.assertEqual(created.paper, "Permit")
        self.assertEqual(created.status, "Active")

    def test_license_renewal_create_post_custom_paper_validation(self):
        post_data = {
            "vehicle_no": "WB58CD8888",
            "vehicle_name": "Truck",
            "paper": "Other",
            "custom_paper_name": "",  # Blank should fail
            "expire_date": (date.today() + timedelta(days=40)).strftime("%Y-%m-%d"),
        }
        response = self.client.post(reverse("license_renewal_update"), data=post_data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(LicenseRenewal.objects.filter(vehicle_no="WB58CD8888").exists())

    def test_license_renewal_edit_post_success(self):
        new_expire = (date.today() + timedelta(days=200)).strftime("%Y-%m-%d")
        post_data = {
            "vehicle_no": "WB58AB1001",
            "vehicle_name": "Tata 407 Delivery (Updated)",
            "paper": "RC",
            "expire_date": new_expire,
        }
        response = self.client.post(
            reverse("license_renewal_update_record", args=[self.record1.id]),
            data=post_data,
        )
        self.assertRedirects(response, reverse("license_renewal_view"))
        self.record1.refresh_from_db()
        self.assertEqual(self.record1.vehicle_name, "Tata 407 Delivery (Updated)")
        self.assertEqual(self.record1.status, "Active")

    def test_license_renewal_delete_post(self):
        response = self.client.post(
            reverse("license_renewal_delete", args=[self.record3.id])
        )
        self.assertRedirects(response, reverse("license_renewal_view"))
        self.assertFalse(LicenseRenewal.objects.filter(id=self.record3.id).exists())

    def test_add_expiry_reminders_triggers_warning_for_soon_expiring(self):
        # Create record expiring in 3 days
        LicenseRenewal.objects.create(
            vehicle_no="WB58URGENT",
            vehicle_name="Urgent Van",
            paper="Pollution",
            expire_date=date.today() + timedelta(days=3),
        )
        response = self.client.get(reverse("license_renewal_view"))
        messages_list = list(response.context["messages"])
        warning_messages = [str(m) for m in messages_list if "Reminder" in str(m)]
        self.assertTrue(len(warning_messages) >= 1)
        self.assertTrue(any("WB58URGENT" in msg for msg in warning_messages))
