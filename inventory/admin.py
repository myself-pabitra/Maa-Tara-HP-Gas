from django.contrib import admin
from .models import ProductInventory, StockBatch


@admin.register(ProductInventory)
class ProductInventoryAdmin(admin.ModelAdmin):
    list_display = [
        "product_name",
        "product_quantity",
        "product_price",
        "buy_price",
        "in_stock",
    ]
    search_fields = ["product_name"]
    list_filter = ["in_stock"]


@admin.register(StockBatch)
class StockBatchAdmin(admin.ModelAdmin):
    list_display = [
        "product",
        "buy_price",
        "quantity_added",
        "quantity_remaining",
        "added_at",
        "notes",
    ]
    list_filter = ["product"]
    ordering = ["-added_at"]

