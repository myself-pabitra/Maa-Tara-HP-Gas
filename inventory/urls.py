from django.urls import path

from . import views

urlpatterns = [
    path("add-products/", views.add_product, name="Add_product"),
    path(
        "manage-products/",
        views.manage_products,
        name="manage_products",
    ),
    path(
        "manage-products/update/<int:product_id>/",
        views.update_product,
        name="update_product",
    ),
    path(
        "manage-products/delete/<int:product_id>/",
        views.delete_product,
        name="delete_product",
    ),
]
