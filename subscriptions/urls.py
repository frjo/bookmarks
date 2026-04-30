from django.urls import path

from . import views

app_name = "subscriptions"

urlpatterns = [
    path("pay/", views.pay, name="pay"),
    path("pay/price/", views.pay_price_partial, name="pay_price_partial"),
    path("pay/swish/", views.pay_swish, name="pay_swish"),
    path("swish/wait/<str:payment_id>/", views.swish_wait, name="swish_wait"),
    path("swish/status/<str:payment_id>/", views.swish_status, name="swish_status"),
    path("swish/callback/", views.swish_callback, name="swish_callback"),
    path("success/<str:payment_id>/", views.success, name="success"),
    path("invoice/<str:payment_id>/", views.invoice, name="invoice"),
]
