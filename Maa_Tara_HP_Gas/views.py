import calendar
import json
from datetime import datetime, timedelta
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

    # Determine filter mode: 'today', 'date', 'month', or 'all'
    filter_type = request.GET.get("filter_type", "").strip().lower()
    custom_date_str = request.GET.get("date", "").strip()
    custom_month_str = request.GET.get("month", "").strip()

    if custom_date_str:
        filter_type = "date"
    elif custom_month_str:
        filter_type = "month"
    elif not filter_type:
        filter_type = "today"

    selected_date = None
    selected_month = None
    period_title = f"Today ({today.strftime('%d %b %Y')})"

    all_invoices = DailyInvoice.objects.all()
    all_line_items = DailyInvoiceLineItem.objects.all()

    # 1. Filter by Specific Date
    if filter_type == "date" and custom_date_str:
        try:
            selected_date = datetime.strptime(custom_date_str, "%Y-%m-%d").date()
            invoices = all_invoices.filter(invoice_date=selected_date)
            line_items = all_line_items.filter(invoice__invoice_date=selected_date)
            period_title = f"Date: {selected_date.strftime('%d %B %Y')}"
            chart_anchor = selected_date
        except ValueError:
            filter_type = "today"
            invoices = all_invoices.filter(invoice_date=today)
            line_items = all_line_items.filter(invoice__invoice_date=today)
            chart_anchor = today

    # 2. Filter by Specific Month (YYYY-MM)
    elif filter_type == "month" and custom_month_str:
        try:
            parts = custom_month_str.split("-")
            year, month_num = int(parts[0]), int(parts[1])
            selected_month = custom_month_str
            invoices = all_invoices.filter(invoice_date__year=year, invoice_date__month=month_num)
            line_items = all_line_items.filter(invoice__invoice_date__year=year, invoice__invoice_date__month=month_num)
            m_obj = datetime(year, month_num, 1)
            period_title = f"Month: {m_obj.strftime('%B %Y')}"
            chart_anchor = None
        except Exception:
            filter_type = "today"
            invoices = all_invoices.filter(invoice_date=today)
            line_items = all_line_items.filter(invoice__invoice_date=today)
            chart_anchor = today

    # 3. All-time summary
    elif filter_type == "all":
        invoices = all_invoices
        line_items = all_line_items
        period_title = "All Time Overview"
        chart_anchor = today

    # 4. Default: Today
    else:
        filter_type = "today"
        invoices = all_invoices.filter(invoice_date=today)
        line_items = all_line_items.filter(invoice__invoice_date=today)
        period_title = f"Today ({today.strftime('%d %b %Y')})"
        chart_anchor = today

    #
    # KPIs for Selected Period
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
    # Cylinders in Selected Period
    #

    cylinder_summary = line_items.aggregate(
        cylinders=Coalesce(
            Sum("quantity", filter=Q(product__submission_required=True)),
            0,
        )
    )

    #
    # Collections in Selected Period
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
    # Gross Profit & Net Profit
    #

    profit = line_items.aggregate(
        gross_profit=Coalesce(
            Sum(
                ExpressionWrapper(
                    F("line_total") - F("buying_price"),
                    output_field=DecimalField(),
                )
            ),
            Decimal("0.00"),
            output_field=DecimalField(),
        )
    )

    net_profit = profit["gross_profit"] - invoice_summary["total_expenses"]

    #
    # Dynamic Chart Data (Day-by-Day for selected month OR 30-day window)
    #
    if filter_type == "month" and selected_month:
        year, month_num = int(selected_month.split("-")[0]), int(selected_month.split("-")[1])
        num_days = calendar.monthrange(year, month_num)[1]
        trend_dates = [datetime(year, month_num, day).date() for day in range(1, num_days + 1)]
    else:
        anchor = chart_anchor or today
        trend_start = anchor - timedelta(days=29)
        trend_dates = [trend_start + timedelta(days=offset) for offset in range(30)]

    trend_start_date = trend_dates[0]
    trend_end_date = trend_dates[-1]

    sales_by_date = {
        row["invoice_date"]: row["total"]
        for row in (
            DailyInvoice.objects.filter(
                invoice_date__gte=trend_start_date,
                invoice_date__lte=trend_end_date,
            )
            .values("invoice_date")
            .annotate(
                total=Coalesce(
                    Sum("subtotal"),
                    Decimal("0.00"),
                    output_field=DecimalField(),
                )
            )
        )
    }
    profit_by_date = {
        row["invoice__invoice_date"]: row["total"]
        for row in (
            DailyInvoiceLineItem.objects.filter(
                invoice__invoice_date__gte=trend_start_date,
                invoice__invoice_date__lte=trend_end_date,
            )
            .values("invoice__invoice_date")
            .annotate(
                total=Coalesce(
                    Sum(
                        ExpressionWrapper(
                            F("line_total") - F("buying_price"),
                            output_field=DecimalField(),
                        )
                    ),
                    Decimal("0.00"),
                    output_field=DecimalField(),
                )
            )
        )
    }
    chart_labels = [day.strftime("%d %b") for day in trend_dates]
    chart_sales = [float(sales_by_date.get(day, Decimal("0.00"))) for day in trend_dates]
    chart_profit = [float(profit_by_date.get(day, Decimal("0.00"))) for day in trend_dates]

    # Available months list for fast selection dropdown
    available_months_qs = (
        DailyInvoice.objects.dates("invoice_date", "month", order="DESC")
    )
    available_months = [
        {"value": m.strftime("%Y-%m"), "label": m.strftime("%B %Y")}
        for m in available_months_qs
    ]

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
    # Recent Invoices (Latest 5)
    #

    recent_invoices = DailyInvoice.objects.prefetch_related("employees").order_by(
        "-invoice_date", "-id"
    )[:5]

    #
    # Current Negative DAC Balances by Subdealer (Deduplicated & Top 5)
    #
    subdealer_balances = {}
    for entry in DACEntry.objects.order_by("entry_date", "created_at", "id"):
        subdealer_balances[entry.subdealer_id] = entry.closing_balance

    negative_subdealers = []
    for s in Subdealer.objects.all().order_by("name"):
        bal = subdealer_balances.get(s.id, Decimal("0.00"))
        if bal < 0:
            negative_subdealers.append({
                "subdealer": s,
                "closing_balance": bal,
            })

    negative_subdealers.sort(key=lambda x: x["closing_balance"])
    total_negative_dac_count = len(negative_subdealers)
    negative_dac_preview = negative_subdealers[:5]

    #
    # Quick Stats
    #

    active_products = ProductInventory.objects.count()

    active_subdealers = Subdealer.objects.count()

    active_employees = Employee.objects.filter(is_active=True).count()

    pending_verifications = (
        DailyInvoiceLineItem.objects.filter(payment_status="PENDING")
        .select_related("invoice", "subdealer")
        .order_by("-created_at")[:5]
    )

    #
    # Context
    #

    context = {
        "today": today,
        "filter_type": filter_type,
        "selected_date": selected_date.strftime("%Y-%m-%d") if selected_date else "",
        "selected_month": selected_month or "",
        "period_title": period_title,
        "available_months": available_months,
        "invoice_summary": invoice_summary,
        "payment_summary": payment_summary,
        "cylinder_summary": cylinder_summary,
        "gross_profit": profit["gross_profit"],
        "net_profit": net_profit,
        "stock_value": stock_value["value"],
        "low_stock": low_stock[:5],
        "out_of_stock": out_of_stock[:5],
        "negative_dac": negative_dac_preview,
        "total_negative_dac_count": total_negative_dac_count,
        "recent_invoices": recent_invoices,
        "active_products": active_products,
        "active_subdealers": active_subdealers,
        "active_employees": active_employees,
        "pending_verifications": pending_verifications,
        "chart_labels": json.dumps(chart_labels),
        "chart_sales": json.dumps(chart_sales),
        "chart_profit": json.dumps(chart_profit),
        "page_type": "dashboard",
    }


    return render(
        request,
        "dashboard.html",
        context,
    )
