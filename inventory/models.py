import re

from django.db import models, transaction


class ProductInventory(models.Model):
    productCode = models.CharField(max_length=20, unique=True, editable=False, null=True, blank=True, help_text="Unique code for the product, auto-generated from the product name.")

    product_name = models.CharField(max_length=100)

    product_quantity = models.IntegerField(default=0)

    product_price = models.DecimalField(
        max_digits=10, decimal_places=2, help_text="MRP of the Product"
    )

    buy_price = models.DecimalField(
        max_digits=10, decimal_places=2, help_text="Buying Price of the Product"
    )

    in_stock = models.BooleanField(default=False)

    dac_applicable = models.BooleanField(
        default=False, help_text="Deduct DAC while selling this product."
    )

    class Meta:
        db_table = "product_inventory"
        ordering = ["product_name"]

    def __str__(self):
        return f"{self.productCode} - {self.product_name}"

    def price_after_discount(self, discount_amount):
        return self.product_price - discount_amount

    def generate_product_code(self):

        # Keep only letters and digits
        cleaned = re.sub(r"[^A-Za-z0-9 ]", "", self.product_name.upper())

        words = cleaned.split()

        code = ""

        for word in words:
            if word.isdigit():
                code += word
            else:
                code += word[:2]

        code = code[:10]

        if not ProductInventory.objects.filter(productCode=code).exists():
            return code

        counter = 1

        while True:
            new_code = f"{code}{counter:03d}"

            if not ProductInventory.objects.filter(productCode=new_code).exists():
                return new_code

            counter += 1

    def save(self, *args, **kwargs):

        if not self.productCode:
            with transaction.atomic():
                self.productCode = self.generate_product_code()

        super().save(*args, **kwargs)
