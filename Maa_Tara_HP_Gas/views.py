from datetime import timedelta
from decimal import Decimal

from django.db.models import Q, Count
from django.db.models import DecimalField
from django.db.models import ExpressionWrapper
from django.db.models import F
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.shortcuts import render
from django.utils import timezone

from SubDealers.models import (
    Cylender_information,
    DailyInvoice,
    DailyInvoiceLineItem,
)
from UserDAC.models import DACEntry
from employees.models import Employee
from inventory.models import ProductInventory
from SubDealers.models import Subdealer


def dashboard(request):

    today = timezone.localdate()

    current_month = today.month
    current_year = today.year

    invoices = DailyInvoice.objects.filter(invoice_date=today)

    line_items = DailyInvoiceLineItem.objects.filter(invoice__invoice_date=today)

    #
    # Today's KPIs
    #

    invoice_summary = invoices.aggregate(
        total_sales=Coalesce(
            Sum("subtotal"),
            Decimal("0.00"),
            output_field=DecimalField(),
        ),
        total_expenses=Coalesce(
            Sum("other_expense"),
            Decimal("0.00"),
            output_field=DecimalField(),
        ),
        total_revenue=Coalesce(
            Sum("grand_total"),
            Decimal("0.00"),
            output_field=DecimalField(),
        ),
        total_invoices=Count("id"),
    )

    #
    # Today's Cylinders
    #

    cylinder_summary = line_items.aggregate(
        cylinders=Coalesce(
            Sum("quantity"),
            0,
        )
    )

    #
    # Today's Collections
    #

    payment_summary = line_items.aggregate(
        cash=Coalesce(
            Sum("cash_amount"),
            Decimal("0.00"),
            output_field=DecimalField(),
        ),
        ac=Coalesce(
            Sum("ac_amount"),
            Decimal("0.00"),
            output_field=DecimalField(),
        ),
        due=Coalesce(
            Sum("due_amount"),
            Decimal("0.00"),
            output_field=DecimalField(),
        ),
        pending=Count(
            "id",
            filter=Q(payment_status="PENDING"),
        ),
    )

    #
    # Gross Profit
    #

    profit = line_items.aggregate(
        gross_profit=Coalesce(
            Sum(
                ExpressionWrapper(
                    (F("discounted_price") - F("product__buy_price")) * F("quantity"),
                    output_field=DecimalField(),
                )
            ),
            Decimal("0.00"),
            output_field=DecimalField(),
        )
    )

    net_profit = profit["gross_profit"] - invoice_summary["total_expenses"]

    #
    # Stock Value
    #

    stock_value = ProductInventory.objects.aggregate(
        value=Coalesce(
            Sum(
                ExpressionWrapper(
                    F("buy_price") * F("product_quantity"),
                    output_field=DecimalField(),
                )
            ),
            Decimal("0.00"),
            output_field=DecimalField(),
        )
    )

    #
    # Low Stock
    #

    low_stock = ProductInventory.objects.filter(
        product_quantity__lte=10,
        product_quantity__gt=0,
    ).order_by("product_quantity")

    #
    # Out of Stock
    #

    out_of_stock = ProductInventory.objects.filter(product_quantity=0)

    #
    # Recent Invoices
    #

    recent_invoices = DailyInvoice.objects.prefetch_related("employees").order_by(
        "-invoice_date", "-id"
    )[:5]

    #
    # Negative DAC
    #

    negative_dac = DACEntry.objects.filter(closing_balance__lt=0).select_related(
        "subdealer"
    )

    #
    # Quick Stats
    #

    active_products = ProductInventory.objects.count()

    active_subdealers = Subdealer.objects.count()

    active_employees = Employee.objects.filter(is_active=True).count()

    pending_verifications = (
        DailyInvoiceLineItem.objects.filter(payment_status="PENDING")
        .select_related("invoice", "subdealer")
        .order_by("-created_at")[:10]
    )

    #
    # Context
    #

    context = {
        "today": today,
        "invoice_summary": invoice_summary,
        "payment_summary": payment_summary,
        "cylinder_summary": cylinder_summary,
        "gross_profit": profit["gross_profit"],
        "net_profit": net_profit,
        "stock_value": stock_value["value"],
        "low_stock": low_stock,
        "out_of_stock": out_of_stock,
        "negative_dac": negative_dac,
        "recent_invoices": recent_invoices,
        "active_products": active_products,
        "active_subdealers": active_subdealers,
        "active_employees": active_employees,
        "pending_verifications": pending_verifications,
        "page_type": "dashboard",
    }


    return render(
        request,
        "dashboard.html",
        context,
    )