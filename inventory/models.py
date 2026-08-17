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

    submission_required = models.BooleanField(
        default=False, help_text="Requires empty cylinders to be submitted."
    )

    class Meta:
        db_table = "product_inventory"
        ordering = ["product_name"]

    def __str__(self):
        return f"{self.productCode} - {self.product_name}"

    def price_after_discount(self, discount_amount):
        return self.product_price - discount_amount

    def generate_product_code(self):
        """
        Generate a readable product code.

        Examples:
        -------------------------------------
        Lighter120         -> LIGHT120
        HP Gas 14.2 KG     -> HPGA142KG
        Commercial Cylinder-> COMCY
        Stove              -> STOVE
        Regulator          -> REGUL
        """

        # Keep only letters, numbers and spaces
        cleaned = re.sub(r"[^A-Za-z0-9 ]", "", self.product_name.upper()).strip()

        words = cleaned.split()

        code = ""

        if len(words) == 1:
            word = words[0]

            letters = "".join(ch for ch in word if ch.isalpha())
            digits = "".join(ch for ch in word if ch.isdigit())

            if digits:
                # LIGHTER120 -> LIGHT120
                code = letters[:5] + digits
            else:
                # STOVE -> STOVE
                code = letters[:5]

        else:
            # Multi-word product names
            for word in words:
                if word.isdigit():
                    code += word
                else:
                    code += word[:2]

            code = code[:10]

        # Ensure uniqueness
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


class StockBatch(models.Model):
    """
    Tracks individual stock purchases (batches) for FIFO profit calculation.
    Each time stock is topped up, a new batch is created with the buy price
    at that time. When selling, oldest batches are consumed first.
    """
    product = models.ForeignKey(
        ProductInventory, on_delete=models.CASCADE, related_name="batches"
    )
    buy_price = models.DecimalField(
        max_digits=10, decimal_places=2,
        help_text="Buy price per unit for this batch",
    )
    quantity_added = models.PositiveIntegerField(
        help_text="Original batch size when stock was added",
    )
    quantity_remaining = models.PositiveIntegerField(
        help_text="Units still unsold from this batch",
    )
    added_at = models.DateTimeField(auto_now_add=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "stock_batch"
        ordering = ["added_at"]  # oldest first for FIFO

    def __str__(self):
        return (
            f"{self.product.product_name} — "
            f"₹{self.buy_price} × {self.quantity_remaining}/{self.quantity_added} "
            f"({self.added_at:%d %b %Y})"
        )
