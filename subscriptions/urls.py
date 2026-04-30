from django.urls import path

from . import views

app_name = "subscriptions"

urlpatterns = [
    path("pay/", views.pay, name="pay"),
]
