from django.contrib import admin

from .models import (
    Cylender_information,
    DailyInvoice,
    DailyInvoiceExpense,
    DailyInvoiceLineItem,
    PredefinedExpense,
    Subdealer,
    SubDealerSKUDiscount,
)


@admin.register(Subdealer)
class SubdealerAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone_number', 'address']
    search_fields = ['name']

@admin.register(SubDealerSKUDiscount)
class SubDealerSKUDiscountAdmin(admin.ModelAdmin):
    list_display = ['subdealer', 'product', 'product_discount']

admin.site.register(Cylender_information)
admin.site.register(PredefinedExpense)
admin.site.register(DailyInvoice)
admin.site.register(DailyInvoiceExpense)


@admin.register(DailyInvoiceLineItem)
class DailyInvoiceLineItemAdmin(admin.ModelAdmin):
    list_display = ['invoice', 'subdealer','product','payment_mode','payment_status']
    



