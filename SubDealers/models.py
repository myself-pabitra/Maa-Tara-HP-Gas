from decimal import Decimal
import random
import string
from django.db import models,transaction
from inventory.models import ProductInventory
from django.utils import timezone


class Subdealer(models.Model):
    name = models.CharField(max_length=100, help_text="Name of the subdealer")
    subdealerCode = models.CharField(max_length=50,unique=True,help_text="Unique Subdealer Code")
    phone_number = models.CharField(
        max_length=15, help_text="Phone number of the subdealer"
    )
    address = models.TextField(help_text="Address of the subdealer")

    class Meta:
        db_table = "SubDealers"

    def __str__(self):
        return self.name
    
    def create_subdealer_code(self):
        """
        Generate a subdealer code like:
        First 4 letters of the name + last 6 digits of the phone number + 2 random alphabets.
        """
        name_part = self.name[:4].upper()
        phone_part = self.phone_number[-6:]
        random_part = ''.join(random.choices(string.ascii_uppercase, k=2))
        return f"{name_part}{phone_part}{random_part}"
    
    def save(self, *args, **kwargs):
        """
        Automatically assign subdealerCode before saving.
        """
        if not self.subdealerCode:  # Only generate if not already set
            self.subdealerCode = self.create_subdealer_code()
        super().save(*args, **kwargs)


class SubDealerSKUDiscount(models.Model):
    subdealer = models.ForeignKey(Subdealer, on_delete=models.CASCADE)
    product = models.ForeignKey(ProductInventory, on_delete=models.CASCADE)
    product_discount = models.DecimalField(max_digits=5, decimal_places=2)

    class Meta:
        db_table = "SubDealer_SKU_Discount"
        # Ensure each subdealer-product combination is unique
        unique_together = ('subdealer', 'product')

    def __str__(self):
        return f"{self.subdealer.name} - {self.product.product_name} (Discount: {self.product_discount}%)"
    
    def get_subdealer_discounted_product_price(self, product):
        return product.price_after_discount(self.product_discount)
    


class Cylender_information(models.Model):
    Subdealer = models.ForeignKey('SubDealers.Subdealer', on_delete=models.CASCADE)
    product = models.ForeignKey('inventory.ProductInventory', on_delete=models.CASCADE)
    due_cylender_qty = models.IntegerField()

    def __str__(self):
        return f"{self.Subdealer.name} - {self.product.product_name} (Due Cylender: {self.due_cylender_qty})"
    
    class Meta:
        db_table = "Cylender_information"



class DailyInvoice(models.Model):
    invoice_number = models.CharField(max_length=30, unique=True, editable=False)
    invoice_date = models.DateField()  # set from form
    employees = models.ManyToManyField('employees.Employee', blank=True)
    # invoice-level mode is derived from line items (convenience)
    payment_mode = models.CharField(max_length=20, blank=True)
    notes = models.TextField(blank=True, null=True)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    other_expense = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    grand_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        db_table = "DailyInvoice"

    def save(self, *args, **kwargs):
        # Only assign invoice_number once
        if not self.invoice_number:
            today = timezone.now().strftime("%Y%m%d")
            with transaction.atomic():
                last_invoice = (
                    DailyInvoice.objects.filter(invoice_number__startswith=f"INV-{today}")
                    .order_by("-invoice_number")
                    .first()
                )
                if last_invoice:
                    try:
                        last_seq = int(last_invoice.invoice_number.split("-")[-1])
                    except Exception:
                        last_seq = 0
                    next_seq = last_seq + 1
                else:
                    next_seq = 1
                self.invoice_number = f"INV-{today}-{next_seq:05d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.invoice_number



class DailyInvoiceLineItem(models.Model):
    PAYMENT_MODE_CHOICES = [
        ('Cash', 'Cash'),
        ('Mixed', 'Mixed'),
        ('AC', 'AC'),
    ]
    PAYMENT_STATUS_CHOICES = [
        ('PAID', 'Paid'),
        ('PENDING', 'Pending Verification'),
    ]

    invoice = models.ForeignKey(DailyInvoice, on_delete=models.CASCADE, related_name='line_items')
    subdealer = models.ForeignKey('SubDealers.Subdealer', on_delete=models.PROTECT)
    product = models.ForeignKey('inventory.ProductInventory', on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    submitted_blank = models.PositiveIntegerField(default=0)
    discounted_price = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=14, decimal_places=2)
    due_cyl = models.PositiveIntegerField(default=0)

    # Payment fields per-line
    payment_mode = models.CharField(max_length=10, choices=PAYMENT_MODE_CHOICES, default='Cash')
    cash_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    ac_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    payment_status = models.CharField(max_length=10, choices=PAYMENT_STATUS_CHOICES, default='PENDING')

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.invoice.invoice_number} - {self.subdealer} - {self.product}"


class DailyInvoiceExpense(models.Model):
    invoice = models.ForeignKey(DailyInvoice, on_delete=models.CASCADE, related_name='expenses')
    expense_name = models.CharField(max_length=100)
    expense_amount = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.invoice.invoice_number} - {self.expense_name}: ₹{self.expense_amount}"


class PredefinedExpense(models.Model):
    name = models.CharField(max_length=100, unique=True)
    default_amount = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = "predefined_expenses"

    def __str__(self):
        return f"{self.name} - ₹{self.default_amount}"
    