from django.db import models


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
