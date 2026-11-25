from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db.models import F, Q, Sum
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse
from django.db import transaction
from django.utils import timezone

from .models import ProductInventory, StockBatch


def add_product(request):
    if request.method == "POST":
        try:
            product_name = request.POST.get("product_name", "").strip()

            if not product_name:
                messages.error(request, "Product name is required.")
                return redirect("Add_product")

            product = ProductInventory.objects.create(
                product_name=product_name,
                product_quantity=int(request.POST.get("product_quantity", 0)),
                buy_price=Decimal(request.POST.get("buy_price", "0")),
                product_price=Decimal(request.POST.get("product_price", "0")),
                in_stock="in_stock" in request.POST,
                dac_applicable="dac_applicable" in request.POST,
                submission_required="submission_required" in request.POST,
            )

            messages.success(
                request, f"Product '{product.product_name}' added successfully."
            )

            return redirect("manage_products")

        except Exception as e:
            messages.error(request, f"Unable to add product: {e}")
            return redirect("Add_product")

    recent_products = ProductInventory.objects.order_by("-id")[:5]
    total_products_count = ProductInventory.objects.count()

    return render(
        request,
        "inventory/Add_product_to_inventory.html",
        {
            "recent_products": recent_products,
            "total_products_count": total_products_count,
            "page_type": "add_product",
        },
    )


def manage_products(request):
    """
    Display and manage all inventory products with summary statistics and metrics.
    """
    products = ProductInventory.objects.all().order_by("product_name")

    total_products = products.count()
    in_stock_count = products.filter(in_stock=True).count()
    out_of_stock_count = products.filter(in_stock=False).count()
    low_stock_count = products.filter(in_stock=True, product_quantity__lt=15).count()
    dac_count = products.filter(dac_applicable=True).count()
    cylinder_req_count = products.filter(submission_required=True).count()

    total_units = sum(p.product_quantity for p in products)
    total_inventory_value = sum(p.product_quantity * p.buy_price for p in products)
    total_retail_value = sum(p.product_quantity * p.product_price for p in products)

    # Attach computed profit and margin percentage to each product for display
    enriched_products = []
    for p in products:
        margin = p.product_price - p.buy_price
        margin_pct = (
            ((margin / p.buy_price) * 100) if p.buy_price > 0 else Decimal("0.0")
        )
        is_low_stock = p.in_stock and p.product_quantity < 15
        enriched_products.append({
            "obj": p,
            "margin": margin,
            "margin_pct": round(margin_pct, 1),
            "is_low_stock": is_low_stock,
            "total_value": p.product_quantity * p.buy_price,
        })

    context = {
        "products": products,
        "enriched_products": enriched_products,
        "total_products": total_products,
        "in_stock_count": in_stock_count,
        "out_of_stock_count": out_of_stock_count,
        "low_stock_count": low_stock_count,
        "dac_count": dac_count,
        "cylinder_req_count": cylinder_req_count,
        "total_units": total_units,
        "total_inventory_value": total_inventory_value,
        "total_retail_value": total_retail_value,
        "page_type": "manage_products",
    }

    return render(
        request,
        "inventory/manage_products.html",
        context,
    )


def update_product(request, product_id):
    if request.method != "POST":
        return redirect("manage_products")

    product = get_object_or_404(ProductInventory, id=product_id)

    try:
        product_name = request.POST.get("product_name", "").strip()
        if product_name:
            product.product_name = product_name

        quantity = int(request.POST.get("product_quantity", product.product_quantity))
        buy_price = Decimal(request.POST.get("buy_price", str(product.buy_price)))
        sell_price = Decimal(request.POST.get("product_price", str(product.product_price)))

        if quantity < 0 or buy_price < 0 or sell_price < 0:
            raise ValueError("Quantity and prices cannot be negative.")

        product.product_quantity = quantity
        product.buy_price = buy_price
        product.product_price = sell_price
        product.in_stock = request.POST.get("in_stock") in ["1", "true", "on", True]
        product.dac_applicable = request.POST.get("dac_applicable") in ["1", "true", "on", True]
        product.submission_required = request.POST.get("submission_required") in ["1", "true", "on", True]

        product.save()
        messages.success(request, f"Product '{product.product_name}' updated successfully.")

    except (ValueError, InvalidOperation) as e:
        messages.error(request, f"Invalid input: {e}")
    except Exception as e:
        messages.error(request, f"Unable to update product: {e}")

    return redirect("manage_products")


def delete_product(request, product_id):
    """
    Delete a product with protection for linked records.
    """
    product = get_object_or_404(ProductInventory, id=product_id)

    if request.method == "POST":
        name = product.product_name
        try:
            product.delete()
            messages.success(request, f"Product '{name}' deleted successfully.")
        except ProtectedError:
            messages.error(
                request,
                f"Cannot delete '{name}' because it is linked to existing invoices or sales records.",
            )
        except Exception as e:
            messages.error(request, f"Could not delete product: {e}")

    return redirect("manage_products")


def topup_stock(request):
    """
    Dedicated page to top-up product stock.
    GET: Show product selector with current stock and buy price, plus recent batch history.
    POST: Create a StockBatch and increment product.product_quantity.
    """
    products = ProductInventory.objects.all().order_by("product_name")

    if request.method == "POST":
        try:
            product_id = request.POST.get("product_id")
            quantity = int(request.POST.get("quantity", 0))
            buy_price = Decimal(request.POST.get("buy_price", "0"))
            notes = request.POST.get("notes", "").strip()

            if not product_id:
                raise ValueError("Please select a product.")
            if quantity <= 0:
                raise ValueError("Quantity must be greater than zero.")
            if buy_price < 0:
                raise ValueError("Buy price cannot be negative.")

            product = get_object_or_404(ProductInventory, id=product_id)

            with transaction.atomic():
                # Create the batch
                StockBatch.objects.create(
                    product=product,
                    buy_price=buy_price,
                    quantity_added=quantity,
                    quantity_remaining=quantity,
                    notes=notes,
                )

                # Update product stock and buy price
                product.product_quantity += quantity
                product.buy_price = buy_price  # update to latest buy price
                product.in_stock = True
                product.save(update_fields=["product_quantity", "buy_price", "in_stock"])

            messages.success(
                request,
                f"Added {quantity} units of '{product.product_name}' at ₹{buy_price}/unit. "
                f"New stock: {product.product_quantity}",
            )
            return redirect("topup_stock")

        except (ValueError, InvalidOperation) as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Error: {e}")

    # Recent top-up history (last 25 batches)
    recent_batches = (
        StockBatch.objects.select_related("product")
        .order_by("-added_at")[:25]
    )

    total_batches_count = StockBatch.objects.count()
    total_units_stocked = StockBatch.objects.aggregate(total=Sum("quantity_added"))["total"] or 0

    # Build product data for JS (current stock, buy price)
    product_data = {
        str(p.id): {
            "name": p.product_name,
            "code": p.productCode,
            "current_stock": p.product_quantity,
            "buy_price": str(p.buy_price),
            "sell_price": str(p.product_price),
        }
        for p in products
    }

    import json

    context = {
        "products": products,
        "product_data_json": json.dumps(product_data),
        "recent_batches": recent_batches,
        "total_batches_count": total_batches_count,
        "total_units_stocked": total_units_stocked,
        "page_type": "topup_stock",
    }
    return render(request, "inventory/topup_stock.html", context)


def daily_stock_trend(request):
    """
    Day-wise product inventory trend and available stock lookup.
    Enables user to:
    1. Know exact available stock of any product on a specific target date.
    2. View day-by-day inventory progression (Opening, Inward/Top-up, Outward/Dispatched, Closing/Available).
    3. Inspect invoices and stock batches on that date.
    4. View visual stock level trend charts over time.
    """
    import calendar
    import json
    from datetime import datetime, date, timedelta
    from SubDealers.models import DailyInvoiceLineItem

    today = timezone.localdate()
    products = ProductInventory.objects.all().order_by("product_name")

    # 1. Product Filter
    product_param = request.GET.get("product", "").strip()
    selected_product = None
    if product_param and product_param.isdigit():
        selected_product = products.filter(id=int(product_param)).first()
    if not selected_product:
        # Default to first product if available
        selected_product = products.first()

    # 2. Target Date (for specific date lookup)
    date_param = request.GET.get("date", "").strip()
    target_date = today
    if date_param:
        try:
            target_date = datetime.strptime(date_param, "%Y-%m-%d").date()
        except ValueError:
            target_date = today

    # 3. Date Range / Preset Filter
    preset = request.GET.get("preset", "this_month").strip()
    from_date_param = request.GET.get("from_date", "").strip()
    to_date_param = request.GET.get("to_date", "").strip()

    if preset == "today":
        from_date = today
        to_date = today
    elif preset == "yesterday":
        yesterday = today - timedelta(days=1)
        from_date = yesterday
        to_date = yesterday
    elif preset == "last_7_days":
        from_date = today - timedelta(days=6)
        to_date = today
    elif preset == "last_30_days":
        from_date = today - timedelta(days=29)
        to_date = today
    elif preset == "this_month":
        from_date = date(today.year, today.month, 1)
        to_date = today  # Month-to-date up to today to prevent phantom future days
    elif preset == "last_month":
        first_this_month = date(today.year, today.month, 1)
        last_prev_month = first_this_month - timedelta(days=1)
        from_date = date(last_prev_month.year, last_prev_month.month, 1)
        to_date = last_prev_month
    elif preset == "custom" or from_date_param or to_date_param:
        preset = "custom"
        try:
            from_date = datetime.strptime(from_date_param, "%Y-%m-%d").date() if from_date_param else date(target_date.year, target_date.month, 1)
        except ValueError:
            from_date = date(target_date.year, target_date.month, 1)
        try:
            to_date = datetime.strptime(to_date_param, "%Y-%m-%d").date() if to_date_param else target_date
        except ValueError:
            to_date = target_date
    else:
        # Default to month-to-date up to today
        from_date = date(target_date.year, target_date.month, 1)
        to_date = min(target_date, today)

    # Do not project historical stock into future days
    if to_date > today:
        to_date = today

    if from_date > to_date:
        from_date, to_date = to_date, from_date

    # Max range safeguard: 366 days
    if (to_date - from_date).days > 366:
        from_date = to_date - timedelta(days=366)

    # 4. Activity filter
    active_only = request.GET.get("active_only", "0").strip() in ["1", "true", "on", "yes"]

    # =========================================================================
    # A. Specific Date Spotlight (target_date) for selected_product
    # =========================================================================
    target_date_metrics = {}
    target_date_invoices = []
    target_date_batches = []

    if selected_product:
        # Stock after target_date
        sales_after_target = DailyInvoiceLineItem.objects.filter(
            product=selected_product,
            invoice__invoice_date__gt=target_date
        ).aggregate(s=Sum("quantity"))["s"] or 0

        topups_after_target = StockBatch.objects.filter(
            product=selected_product,
            added_at__date__gt=target_date
        ).aggregate(s=Sum("quantity_added"))["s"] or 0

        closing_on_target = selected_product.product_quantity + sales_after_target - topups_after_target

        inward_on_target = StockBatch.objects.filter(
            product=selected_product,
            added_at__date=target_date
        ).aggregate(s=Sum("quantity_added"))["s"] or 0

        outward_on_target = DailyInvoiceLineItem.objects.filter(
            product=selected_product,
            invoice__invoice_date=target_date
        ).aggregate(s=Sum("quantity"))["s"] or 0

        opening_on_target = closing_on_target + outward_on_target - inward_on_target

        target_date_metrics = {
            "opening_stock": opening_on_target,
            "inward": inward_on_target,
            "outward": outward_on_target,
            "closing_stock": closing_on_target,
            "net_change": inward_on_target - outward_on_target,
            "stock_value": closing_on_target * selected_product.buy_price,
            "retail_value": closing_on_target * selected_product.product_price,
            "is_out_of_stock": closing_on_target <= 0,
            "is_low_stock": (0 < closing_on_target < 15),
        }

        # Invoices on target_date
        target_date_invoices = (
            DailyInvoiceLineItem.objects.filter(
                product=selected_product,
                invoice__invoice_date=target_date
            )
            .select_related("invoice", "subdealer")
            .order_by("-id")
        )

        # Batches on target_date
        target_date_batches = (
            StockBatch.objects.filter(
                product=selected_product,
                added_at__date=target_date
            )
            .order_by("-added_at")
        )

    # =========================================================================
    # B. All Products Snapshot on target_date
    # =========================================================================
    all_products_snapshot = []
    total_snapshot_units = 0
    total_snapshot_value = Decimal("0.00")

    for p in products:
        p_sales_after = DailyInvoiceLineItem.objects.filter(
            product=p,
            invoice__invoice_date__gt=target_date
        ).aggregate(s=Sum("quantity"))["s"] or 0

        p_topups_after = StockBatch.objects.filter(
            product=p,
            added_at__date__gt=target_date
        ).aggregate(s=Sum("quantity_added"))["s"] or 0

        p_close = p.product_quantity + p_sales_after - p_topups_after

        p_inward = StockBatch.objects.filter(
            product=p,
            added_at__date=target_date
        ).aggregate(s=Sum("quantity_added"))["s"] or 0

        p_outward = DailyInvoiceLineItem.objects.filter(
            product=p,
            invoice__invoice_date=target_date
        ).aggregate(s=Sum("quantity"))["s"] or 0

        p_open = p_close + p_outward - p_inward
        p_val = p_close * p.buy_price

        total_snapshot_units += p_close
        total_snapshot_value += p_val

        all_products_snapshot.append({
            "product": p,
            "opening_stock": p_open,
            "inward": p_inward,
            "outward": p_outward,
            "closing_stock": p_close,
            "net_change": p_inward - p_outward,
            "value": p_val,
            "is_selected": (selected_product and p.id == selected_product.id),
        })

    # =========================================================================
    # C. Day-Wise Range Progression & Chart Data for selected_product
    # =========================================================================
    daily_records = []
    chart_labels = []
    chart_closing_stock = []
    chart_inward = []
    chart_outward = []

    range_total_inward = 0
    range_total_outward = 0
    range_highest_stock = 0
    range_highest_date = None
    range_lowest_stock = None
    range_lowest_date = None

    if selected_product:
        # Closing stock at end of to_date
        sales_after_to = DailyInvoiceLineItem.objects.filter(
            product=selected_product,
            invoice__invoice_date__gt=to_date
        ).aggregate(s=Sum("quantity"))["s"] or 0

        topups_after_to = StockBatch.objects.filter(
            product=selected_product,
            added_at__date__gt=to_date
        ).aggregate(s=Sum("quantity_added"))["s"] or 0

        stock_at_to_date = selected_product.product_quantity + sales_after_to - topups_after_to

        # Aggregate daily sales and topups in [from_date, to_date]
        items_in_range_qs = (
            DailyInvoiceLineItem.objects.filter(
                product=selected_product,
                invoice__invoice_date__gte=from_date,
                invoice__invoice_date__lte=to_date,
            )
            .select_related("invoice", "subdealer")
            .order_by("-id")
        )
        items_by_date = {}
        sales_in_range = {}
        for item in items_in_range_qs:
            d = item.invoice.invoice_date
            if d not in items_by_date:
                items_by_date[d] = []
            items_by_date[d].append(item)
            sales_in_range[d] = sales_in_range.get(d, 0) + item.quantity

        batches_in_range_qs = (
            StockBatch.objects.filter(
                product=selected_product,
                added_at__date__gte=from_date,
                added_at__date__lte=to_date,
            )
            .order_by("-added_at")
        )
        batches_by_date = {}
        topups_in_range = {}
        for b in batches_in_range_qs:
            d = b.added_at.date()
            if d not in batches_by_date:
                batches_by_date[d] = []
            batches_by_date[d].append(b)
            topups_in_range[d] = topups_in_range.get(d, 0) + b.quantity_added

        # Step backwards from to_date to from_date
        curr_closing = stock_at_to_date
        curr = to_date
        raw_days = []

        while curr >= from_date:
            inw = topups_in_range.get(curr, 0)
            outw = sales_in_range.get(curr, 0)
            opn = curr_closing + outw - inw
            day_invoices = items_by_date.get(curr, [])
            day_batches = batches_by_date.get(curr, [])
            has_act = (inw > 0 or outw > 0)

            range_total_inward += inw
            range_total_outward += outw

            if curr_closing > range_highest_stock:
                range_highest_stock = curr_closing
                range_highest_date = curr

            if range_lowest_stock is None or curr_closing < range_lowest_stock:
                range_lowest_stock = curr_closing
                range_lowest_date = curr

            raw_days.append({
                "date": curr,
                "date_formatted": curr.strftime("%d %b %Y"),
                "weekday": curr.strftime("%a"),
                "opening_stock": opn,
                "inward": inw,
                "outward": outw,
                "closing_stock": curr_closing,
                "net_change": inw - outw,
                "has_activity": has_act,
                "is_target_date": (curr == target_date),
                "invoices": day_invoices,
                "batches": day_batches,
            })

            curr_closing = opn
            curr -= timedelta(days=1)

        raw_days.reverse()  # chronological order for display and chart

        # Chart data preparation
        for day in raw_days:
            chart_labels.append(day["date"].strftime("%d %b"))
            chart_closing_stock.append(day["closing_stock"])
            chart_inward.append(day["inward"])
            chart_outward.append(day["outward"])

        # Display table filtering (show all days vs active only)
        if active_only:
            daily_records = [d for d in raw_days if d["has_activity"] or d["is_target_date"]]
        else:
            daily_records = raw_days

    range_summary = {
        "from_date": from_date,
        "to_date": to_date,
        "total_inward": range_total_inward,
        "total_outward": range_total_outward,
        "start_stock": daily_records[0]["opening_stock"] if daily_records else 0,
        "end_stock": daily_records[-1]["closing_stock"] if daily_records else 0,
        "net_change": range_total_inward - range_total_outward,
        "highest_stock": range_highest_stock,
        "highest_date": range_highest_date,
        "lowest_stock": range_lowest_stock if range_lowest_stock is not None else 0,
        "lowest_date": range_lowest_date,
        "active_days_count": sum(1 for d in daily_records if d["has_activity"]),
        "total_days_count": len(daily_records),
    }

    context = {
        "products": products,
        "selected_product": selected_product,
        "target_date": target_date,
        "target_date_str": target_date.strftime("%Y-%m-%d"),
        "target_date_metrics": target_date_metrics,
        "target_date_invoices": target_date_invoices,
        "target_date_batches": target_date_batches,
        "all_products_snapshot": all_products_snapshot,
        "total_snapshot_units": total_snapshot_units,
        "total_snapshot_value": total_snapshot_value,
        "daily_records": daily_records,
        "range_summary": range_summary,
        "preset": preset,
        "from_date": from_date,
        "to_date": to_date,
        "from_date_str": from_date.strftime("%Y-%m-%d"),
        "to_date_str": to_date.strftime("%Y-%m-%d"),
        "active_only": active_only,
        "today": today,
        "chart_labels_json": json.dumps(chart_labels),
        "chart_closing_stock_json": json.dumps(chart_closing_stock),
        "chart_inward_json": json.dumps(chart_inward),
        "chart_outward_json": json.dumps(chart_outward),
        "page_type": "daily_stock_trend",
    }

    return render(request, "inventory/daily_stock_trend.html", context)

