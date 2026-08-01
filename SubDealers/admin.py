from django.contrib import admin
from .models import DACEntry, PredefinedExpense, Subdealer, SubDealerSKUDiscount, Cylender_information, DailyInvoice, DailyInvoiceExpense, DailyInvoiceLineItem


@admin.register(Subdealer)
class SubdealerAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone_number', 'address']
    search_fields = ['name']

@admin.register(SubDealerSKUDiscount)
class SubDealerSKUDiscountAdmin(admin.ModelAdmin):
    list_display = ['subdealer', 'product', 'product_discount']

@admin.register(DACEntry)
class DACEntryAdmin(admin.ModelAdmin):
    list_display = ['subdealer', 'entry_date', 'amount', 'description']
    list_filter = ['entry_date', 'subdealer']
    search_fields = ['subdealer__name', 'description']


admin.site.register(Cylender_information)
admin.site.register(PredefinedExpense)
admin.site.register(DailyInvoice)
admin.site.register(DailyInvoiceExpense)
admin.site.register(DailyInvoiceLineItem)



