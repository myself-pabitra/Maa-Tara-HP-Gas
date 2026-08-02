from django.contrib import admin
from django.urls import path, include
from . import views

urlpatterns = [
    path("admin/", admin.site.urls),
    # dasboard url
    path("", views.dashboard, name="dashboard"),
    # Inventory appllication URLs
    path("inventory/", include("inventory.urls")),
    # Subdealers appllication URLs
    path("subdealers/", include("SubDealers.urls")),
    # Employee Application URLs
    path("employees/",include("employees.urls")),
    #UserDAC Application URLs
    path("userdac/",include("UserDAC.urls")),
    #Payments Application URLs
    path("payments/",include("Payments.urls")),
    # Accounts Application URLs
    path("accounts/", include("accounts.urls")),
    # analytics Application URLs
    path("analytics/", include("analytics.urls")),
]
