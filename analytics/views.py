from datetime import datetime
from decimal import Decimal

from django.db.models import (
    Count,
    DecimalField,
    ExpressionWrapper,
    F,
    Q,
    Sum,
)
from django.db.models.functions import (
    Coalesce,
    ExtractMonth,
    ExtractYear,
)
from django.shortcuts import render

from SubDealers.models import (
    DailyInvoice,
    DailyInvoiceLineItem,
)
from UserDAC.models import DACEntry


def monthly_summary(request):

    context = {}

    # ==========================================================
    # Filters
    # ==========================================================

    year_filter = request.GET.get("year", "").strip()
    month_filter = request.GET.get("month", "").strip()

    # Query-string values are user input.  Ignore invalid values instead of
    # passing them to Django's date transforms and returning a server error.
    if not year_filter.isdigit() or int(year_filter) < 1:
        year_filter = ""
    if not month_filter.isdigit() or not 1 <= int(month_filter) <= 12:
        month_filter = ""

    invoices = DailyInvoice.objects.all()

    line_items = DailyInvoiceLineItem.objects.select_related(
        "invoice",
        "subdealer",
        "product",
    )

    dac_entries = DACEntry.objects.select_related(
        "subdealer",
    )

    # ==========================================================
    # Apply Filters
    # ==========================================================

    if year_filter:
        invoices = invoices.filter(
            invoice_date__year=year_filter,
        )

        line_items = line_items.filter(
            invoice__invoice_date__year=year_filter,
        )

        dac_entries = dac_entries.filter(
            entry_date__year=year_filter,
        )

    if month_filter:
        invoices = invoices.filter(
            invoice_date__month=month_filter,
        )

        line_items = line_items.filter(
            invoice__invoice_date__month=month_filter,
        )

        dac_entries = dac_entries.filter(
            entry_date__month=month_filter,
        )

    # ==========================================================
    # KPI Cards
    # ==========================================================

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

    # ==========================================================
    # Cylinder Statistics
    # ==========================================================

    cylinder_summary = line_items.aggregate(
        cylinders_sold=Coalesce(
            Sum("quantity"),
            0,
        ),
        billed_amount=Coalesce(
            Sum("line_total"),
            Decimal("0.00"),
            output_field=DecimalField(),
        ),
        cash_received=Coalesce(
            Sum("cash_amount"),
            Decimal("0.00"),
            output_field=DecimalField(),
        ),
        ac_billed=Coalesce(
            Sum("ac_amount"),
            Decimal("0.00"),
            output_field=DecimalField(),
        ),
        verified_amount=Coalesce(
            Sum("verified_ac_amount"),
            Decimal("0.00"),
            output_field=DecimalField(),
        ),
        outstanding_due=Coalesce(
            Sum("due_amount"),
            Decimal("0.00"),
            output_field=DecimalField(),
        ),
    )

    # ==========================================================
    # Payment Statistics
    # ==========================================================

    payment_summary = line_items.aggregate(
        cash_count=Count(
            "id",
            filter=Q(payment_mode="Cash"),
        ),
        mixed_count=Count(
            "id",
            filter=Q(payment_mode="Mixed"),
        ),
        ac_count=Count(
            "id",
            filter=Q(payment_mode="AC"),
        ),
        paid_count=Count(
            "id",
            filter=Q(payment_status="PAID"),
        ),
        partial_count=Count(
            "id",
            filter=Q(payment_status="PARTIAL"),
        ),
        pending_count=Count(
            "id",
            filter=Q(payment_status="PENDING"),
        ),
    )

    # ==========================================================
    # Due Payments
    # ==========================================================

    due_summary = line_items.aggregate(
        total_due=Coalesce(
            Sum("due_amount"),
            Decimal("0.00"),
            output_field=DecimalField(),
        ),
        pending_verification=Count(
            "id",
            filter=Q(payment_status="PENDING"),
        ),
    )

    # ==========================================================
    # Cylinder Mismatch
    # ==========================================================

    mismatch_summary = line_items.aggregate(
        mismatch_records=Count(
            "id",
            filter=~Q(quantity=F("submitted_blank")),
        ),
        shortage=Coalesce(
            Sum(
                F("quantity") - F("submitted_blank"),
                filter=Q(quantity__gt=F("submitted_blank")),
                output_field=DecimalField(),
            ),
            Decimal("0.00"),
            output_field=DecimalField(),
        ),
        excess=Coalesce(
            Sum(
                F("submitted_blank") - F("quantity"),
                filter=Q(submitted_blank__gt=F("quantity")),
                output_field=DecimalField(),
            ),
            Decimal("0.00"),
            output_field=DecimalField(),
        ),
    )

    # ==========================================================
    # DAC Statistics
    # ==========================================================

    dac_summary = dac_entries.aggregate(
        total_credit=Coalesce(
            Sum(
                "transaction_quantity",
                filter=Q(transaction_type="CR"),
            ),
            Decimal("0.00"),
            output_field=DecimalField(),
        ),
        total_debit=Coalesce(
            Sum(
                "transaction_quantity",
                filter=Q(transaction_type="DR"),
            ),
            Decimal("0.00"),
            output_field=DecimalField(),
        ),
        total_transactions=Count("id"),
    )

    dac_summary["net_balance"] = (
        dac_summary["total_credit"] - dac_summary["total_debit"]
    )

    # ==========================================================
    # Monthly Invoice Summary
    # ==========================================================

    monthly_invoice_summary = (
        invoices.annotate(
            year=ExtractYear("invoice_date"),
            month=ExtractMonth("invoice_date"),
        )
        .values("year", "month")
        .annotate(
            invoice_count=Count("id"),
            subtotal=Coalesce(
                Sum("subtotal"),
                Decimal("0.00"),
                output_field=DecimalField(),
            ),
            expenses=Coalesce(
                Sum("other_expense"),
                Decimal("0.00"),
                output_field=DecimalField(),
            ),
            revenue=Coalesce(
                Sum("grand_total"),
                Decimal("0.00"),
                output_field=DecimalField(),
            ),
        )
        .order_by("year", "month")
    )
    invoice_lookup = {
        (row["year"], row["month"]): row for row in monthly_invoice_summary
    }

    # ==========================================================
    # Monthly Cylinder Summary
    # ==========================================================

    monthly_cylinder_summary = (
        line_items.annotate(
            year=ExtractYear("invoice__invoice_date"),
            month=ExtractMonth("invoice__invoice_date"),
        )
        .values("year", "month")
        .annotate(
            cylinders=Coalesce(
                Sum("quantity"),
                0,
            )
        )
    )

    cylinder_lookup = {
        (row["year"], row["month"]): row["cylinders"]
        for row in monthly_cylinder_summary
    }

    # ==========================================================
    # Monthly Due Summary
    # ==========================================================

    monthly_due_summary = (
        line_items.annotate(
            year=ExtractYear("invoice__invoice_date"),
            month=ExtractMonth("invoice__invoice_date"),
        )
        .values("year", "month")
        .annotate(
            due_amount=Coalesce(
                Sum("due_amount"),
                Decimal("0.00"),
                output_field=DecimalField(),
            ),
            pending_count=Count(
                "id",
                filter=Q(payment_status="PENDING"),
            ),
        )
    )

    due_lookup = {(row["year"], row["month"]): row for row in monthly_due_summary}

    # ==========================================================
    # Monthly DAC Summary
    # ==========================================================

    monthly_dac_summary = (
        dac_entries.annotate(
            year=ExtractYear("entry_date"),
            month=ExtractMonth("entry_date"),
        )
        .values("year", "month")
        .annotate(
            credit=Coalesce(
                Sum(
                    "transaction_quantity",
                    filter=Q(transaction_type="CR"),
                ),
                Decimal("0.00"),
                output_field=DecimalField(),
            ),
            debit=Coalesce(
                Sum(
                    "transaction_quantity",
                    filter=Q(transaction_type="DR"),
                ),
                Decimal("0.00"),
                output_field=DecimalField(),
            ),
        )
    )

    dac_lookup = {(row["year"], row["month"]): row for row in monthly_dac_summary}

    # ==========================================================
    # Monthly Mismatch Summary
    # ==========================================================

    monthly_mismatch = (
        line_items.annotate(
            year=ExtractYear("invoice__invoice_date"),
            month=ExtractMonth("invoice__invoice_date"),
        )
        .values(
            "year",
            "month",
        )
        .annotate(
            mismatch_count=Count(
                "id",
                filter=~Q(quantity=F("submitted_blank")),
            )
        )
    )

    mismatch_lookup = {
        (row["year"], row["month"]): row["mismatch_count"] for row in monthly_mismatch
    }

    # ==========================================================
    # Build Monthly Table
    # ==========================================================

    monthly_rows = []

    chart_labels = []

    chart_sales = []

    chart_expenses = []

    chart_revenue = []

    chart_cylinders = []

    chart_credit = []

    chart_debit = []

    # An analytics month can contain DAC, cylinder, or due data even when an
    # invoice was not recorded.  Use the union of all summaries so those
    # months do not silently disappear from the table or charts.
    month_keys = set(invoice_lookup)
    month_keys.update(cylinder_lookup)
    month_keys.update(due_lookup)
    month_keys.update(dac_lookup)
    month_keys.update(mismatch_lookup)

    for key in sorted(month_keys):
        year, month = key
        row = invoice_lookup.get(
            key,
            {
                "year": year,
                "month": month,
                "invoice_count": 0,
                "subtotal": Decimal("0.00"),
                "expenses": Decimal("0.00"),
                "revenue": Decimal("0.00"),
            },
        )

        due = due_lookup.get(
            key,
            {},
        )

        dac = dac_lookup.get(
            key,
            {},
        )

        cylinders = cylinder_lookup.get(
            key,
            0,
        )

        mismatch = mismatch_lookup.get(
            key,
            0,
        )

        month_name = datetime(
            year,
            month,
            1,
        ).strftime("%b %Y")

        monthly_rows.append(
            {
                "label": month_name,
                "year": year,
                "month": month,
                "invoice_count": row["invoice_count"],
                "cylinders": cylinders,
                "subtotal": row["subtotal"],
                "expenses": row["expenses"],
                "revenue": row["revenue"],
                "due_amount": due.get(
                    "due_amount",
                    Decimal("0.00"),
                ),
                "pending": due.get(
                    "pending_count",
                    0,
                ),
                "dac_credit": dac.get(
                    "credit",
                    Decimal("0.00"),
                ),
                "dac_debit": dac.get(
                    "debit",
                    Decimal("0.00"),
                ),
                "mismatch": mismatch,
            }
        )

        chart_labels.append(month_name)

        chart_sales.append(float(row["subtotal"]))

        chart_expenses.append(float(row["expenses"]))

        chart_revenue.append(float(row["revenue"]))

        chart_cylinders.append(cylinders)

        chart_credit.append(
            float(
                dac.get(
                    "credit",
                    Decimal("0.00"),
                )
            )
        )

        chart_debit.append(
            float(
                dac.get(
                    "debit",
                    Decimal("0.00"),
                )
            )
        )

    monthly_rows = sorted(
        monthly_rows,
        key=lambda x: (
            x["year"],
            x["month"],
        ),
        reverse=True,
    )

    # ==========================================================
    # Year Filter Dropdown
    # ==========================================================

    year_choices = sorted(
        DailyInvoice.objects.annotate(year=ExtractYear("invoice_date"))
        .values_list(
            "year",
            flat=True,
        )
        .distinct(),
        reverse=True,
    )

    # ==========================================================
    # Top Subdealers
    # ==========================================================

    top_subdealers = (
        line_items.values(
            "subdealer__id",
            "subdealer__name",
            "subdealer__subdealerCode",
        )
        .annotate(
            invoice_count=Count("invoice", distinct=True),
            cylinders=Coalesce(
                Sum("quantity"),
                0,
            ),
            sales=Coalesce(
                Sum("line_total"),
                Decimal("0.00"),
                output_field=DecimalField(),
            ),
            due_amount=Coalesce(
                Sum("due_amount"),
                Decimal("0.00"),
                output_field=DecimalField(),
            ),
        )
        .order_by("-sales")[:10]
    )

    # ==========================================================
    # Product Performance
    # ==========================================================

    top_products = (
        line_items.values(
            "product__id",
            "product__product_name",
            "product__productCode",
        )
        .annotate(
            quantity_sold=Coalesce(
                Sum("quantity"),
                0,
            ),
            sales=Coalesce(
                Sum("line_total"),
                Decimal("0.00"),
                output_field=DecimalField(),
            ),
        )
        .order_by("-quantity_sold")[:10]
    )

    # ==========================================================
    # Employee Performance
    # ==========================================================

    employee_summary = (
        invoices.values(
            "employees__id",
            "employees__employeeCode",
            "employees__name",
        )
        .annotate(
            invoice_count=Count(
                "id",
                distinct=True,
            ),
            sales=Coalesce(
                Sum("grand_total"),
                Decimal("0.00"),
                output_field=DecimalField(),
            ),
            subtotal=Coalesce(
                Sum("subtotal"),
                Decimal("0.00"),
                output_field=DecimalField(),
            ),
        )
        .exclude(employees__id=None)
        .order_by("-sales")
    )

    # ==========================================================
    # Payment Mode Analytics
    # ==========================================================

    payment_mode_summary = line_items.aggregate(
        cash_sales=Coalesce(
            Sum(
                "cash_amount",
                filter=Q(payment_mode="Cash"),
            ),
            Decimal("0.00"),
            output_field=DecimalField(),
        ),
        mixed_cash=Coalesce(
            Sum(
                "cash_amount",
                filter=Q(payment_mode="Mixed"),
            ),
            Decimal("0.00"),
            output_field=DecimalField(),
        ),
        mixed_ac=Coalesce(
            Sum(
                "ac_amount",
                filter=Q(payment_mode="Mixed"),
            ),
            Decimal("0.00"),
            output_field=DecimalField(),
        ),
        ac_sales=Coalesce(
            Sum(
                "ac_amount",
                filter=Q(payment_mode="AC"),
            ),
            Decimal("0.00"),
            output_field=DecimalField(),
        ),
        verified_ac=Coalesce(
            Sum("verified_ac_amount"),
            Decimal("0.00"),
            output_field=DecimalField(),
        ),
        total_due=Coalesce(
            Sum("due_amount"),
            Decimal("0.00"),
            output_field=DecimalField(),
        ),
    )

    # ==========================================================
    # Business Insights
    # ==========================================================

    average_invoice_value = Decimal("0.00")

    if invoice_summary["total_invoices"] > 0:
        average_invoice_value = (
            invoice_summary["total_revenue"] / invoice_summary["total_invoices"]
        )

    average_cylinder_invoice = Decimal("0.00")

    if invoice_summary["total_invoices"] > 0:
        average_cylinder_invoice = (
            cylinder_summary["cylinders_sold"] / invoice_summary["total_invoices"]
        )

    # =========================================================

    profit_summary = line_items.aggregate(
        total_profit=Sum(
            ExpressionWrapper(
                F("line_total") - F("buying_price"),
                output_field=DecimalField(
                    max_digits=18,
                    decimal_places=2,
                ),
            )
        )
    )

    # ===========================================================

    gross_profit = profit_summary["total_profit"] or Decimal("0.00")
    net_profit = gross_profit - invoice_summary["total_expenses"]

    verification_pending = payment_summary["pending_count"]

    partial_payment = payment_summary["partial_count"]

    completed_payment = payment_summary["paid_count"]

    # ==========================================================
    # Dashboard Highlights
    # ==========================================================

    dashboard_highlights = {
        "average_invoice_value": average_invoice_value,
        "average_cylinder_invoice": average_cylinder_invoice,
        "net_profit": net_profit,
        "verification_pending": verification_pending,
        "partial_payment": partial_payment,
        "completed_payment": completed_payment,
    }

    # ==========================================================
    # Context
    # ==========================================================

    context = {
        "invoice_summary": invoice_summary,
        "cylinder_summary": cylinder_summary,
        "payment_summary": payment_summary,
        "due_summary": due_summary,
        "mismatch_summary": mismatch_summary,
        "dac_summary": dac_summary,
        "selected_year": year_filter,
        "selected_month": month_filter,
        "page_type": "monthly_summary",
        "monthly_rows": monthly_rows,
        "year_choices": year_choices,
        "chart_labels": chart_labels,
        "chart_sales": chart_sales,
        "chart_expenses": chart_expenses,
        "chart_revenue": chart_revenue,
        "chart_cylinders": chart_cylinders,
        "chart_credit": chart_credit,
        "chart_debit": chart_debit,
        "top_subdealers": top_subdealers,
        "top_products": top_products,
        "employee_summary": employee_summary,
        "payment_mode_summary": payment_mode_summary,
        "dashboard_highlights": dashboard_highlights,
    }

    payment_mode_summary["mixed_total"] = (
        payment_mode_summary["mixed_cash"] + payment_mode_summary["mixed_ac"]
    )

    return render(
        request,
        "analytics/monthly_summary.html",
        context,
    )
