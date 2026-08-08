from decimal import Decimal, InvalidOperation

from django.contrib import messages
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
            messages.error(request, f"Unable to add product. {e}")

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
    Display all products.
    """
    products = ProductInventory.objects.all().order_by("product_name")

    context = {
        "products": products,
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
        quantity = int(request.POST.get("product_quantity", 0))
        buy_price = Decimal(request.POST.get("buy_price", 0))
        sell_price = Decimal(request.POST.get("product_price", 0))

        if quantity < 0 or buy_price < 0 or sell_price < 0:
            raise ValueError("Quantity and prices cannot be negative.")

        product.product_quantity = quantity
        product.buy_price = buy_price
        product.product_price = sell_price
        product.in_stock = request.POST.get("in_stock") == "1"
        product.dac_applicable = request.POST.get("dac_applicable") == "1"
        product.submission_required = request.POST.get("submission_required") == "1"

        product.save()
        messages.success(request, f"{product.product_name} updated successfully.")

    except (ValueError, InvalidOperation) as e:
        messages.error(request, f"Invalid input: {e}")
    except Exception as e:
        messages.error(request, str(e))

    return redirect("manage_products")


def delete_product(request, product_id):
    """
    Delete a product.
    """

    product = get_object_or_404(
        ProductInventory,
        id=product_id,
    )

    if request.method == "POST":
        name = product.product_name

        product.delete()

        messages.success(
            request,
            f"{name} deleted successfully.",
        )

    return redirect("manage_products")
