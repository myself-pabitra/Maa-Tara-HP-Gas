from . import views
from django.urls import path

urlpatterns = [
    path("monthly-summary/", views.monthly_summary, name="monthly_summary"),
]
