from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db.models import F, Q, Sum
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render

from .models import ProductInventory


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

    return render(
        request,
        "inventory/Add_product_to_inventory.html",
        {
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
