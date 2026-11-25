from django.conf import settings
from django.db import models
from django.utils import timezone


class Employee(models.Model):
    employeeCode = models.CharField(
        max_length=10,
        unique=True,
        blank=True,
        editable=False,
    )

    name = models.CharField(
        max_length=100,
        unique=True,
    )

    phone = models.CharField(
        max_length=15,
        unique=True,
    )

    address = models.TextField()

    is_active = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        db_table = "employees"
        ordering = ["name"]  # noqa: RUF012
        verbose_name = "Employee"
        verbose_name_plural = "Employees"

    def save(self, *args, **kwargs):

        if not self.employeeCode:
            last = Employee.objects.order_by("-id").only("id").first()

            next_number = 1 if not last else last.id + 1

            self.employeeCode = f"EMP{next_number:04d}"

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.employeeCode} - {self.name}"


class OperationalExpense(models.Model):
    PAYMENT_MODES = [
        ("Cash", "Cash"),
        ("Online/UPI", "Online / UPI"),
        ("Bank Transfer", "Bank Transfer"),
        ("Cheque", "Cheque"),
    ]

    expense_date = models.DateField(default=timezone.localdate)
    category = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_mode = models.CharField(max_length=30, choices=PAYMENT_MODES, default="Cash")
    reference_no = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Bill / Slip / Invoice / Vehicle Number",
    )
    description = models.TextField(
        blank=True,
        null=True,
        help_text="Particulars or remarks about the expense",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="operational_expenses",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "operational_expenses"
        ordering = ["-expense_date", "-id"]
        verbose_name = "Operational Expense"
        verbose_name_plural = "Operational Expenses"

    def __str__(self):
        return f"{self.expense_date} | {self.category}: ₹{self.amount}"
