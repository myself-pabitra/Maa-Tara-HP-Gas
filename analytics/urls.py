from . import views
from django.urls import path

urlpatterns = [
    path("analytics/monthly-summary/", views.monthly_summary, name="monthly_summary"),
]
