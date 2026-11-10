from datetime import date

from django.db import models


class LicenseRenewal(models.Model):
    PAPER_CHOICES = [
        ("RC", "RC"),
        ("Insurance", "Insurance"),
        ("Permit", "Permit"),
        ("Fitness", "Fitness"),
        ("Pollution", "Pollution"),
        ("Other", "Other"),
    ]

    STATUS_CHOICES = [
        ("Active", "Active"),
        ("Expiring Soon", "Expiring Soon"),
        ("Expired", "Expired"),
    ]

    vehicle_no = models.CharField(max_length=50)
    vehicle_name = models.CharField(max_length=100)
    paper = models.CharField(max_length=30, choices=PAPER_CHOICES, default="RC")
    custom_paper_name = models.CharField(max_length=100, blank=True, null=True)
    expire_date = models.DateField()
    remaining_days = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="Active")

    class Meta:
        ordering = ["expire_date"]

    @property
    def paper_display(self):
        if self.paper == "Other":
            return self.custom_paper_name or "Other"
        return self.paper

    def normalize_date(self, value):
        if isinstance(value, date) and not isinstance(value, str):
            return value
        if isinstance(value, str):
            try:
                return date.fromisoformat(value)
            except ValueError:
                return None
        return value

    def calculate_remaining_days(self, expire_date=None):
        target_date = self.normalize_date(expire_date) if expire_date is not None else self.normalize_date(self.expire_date)
        if not target_date:
            return 0
        return (target_date - date.today()).days

    def update_status(self, expire_date=None):
        remaining = self.calculate_remaining_days(expire_date)
        self.remaining_days = remaining

        if remaining < 0:
            self.status = "Expired"
        elif remaining <= 30:
            self.status = "Expiring Soon"
        else:
            self.status = "Active"
        return self.status

    def save(self, *args, **kwargs):
        if self.expire_date:
            self.expire_date = self.normalize_date(self.expire_date)
            self.update_status(self.expire_date)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.vehicle_no} - {self.paper}"
