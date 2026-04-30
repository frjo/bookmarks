import logging

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import swish as swish_api
from . import vat as vat_api
from .models import Payment
from .utils import (
    calculate_price,
    extend_subscription,
    generate_invoice_number,
    get_max_payable_years,
)

logger = logging.getLogger(__name__)

_SESSION_KEY = "subscription_payment_intent"


# ---------------------------------------------------------------------------
# Payment form
# ---------------------------------------------------------------------------


@login_required
def pay(request):
    max_years = get_max_payable_years(request.user)
    years_range = range(1, max_years + 1)

    if request.method == "POST":
        try:
            years = int(request.POST.get("years", 1))
        except (ValueError, TypeError):
            years = 1
        years = max(1, min(years, max_years))

        vat_number = request.POST.get("vat_number", "").strip().upper().replace(" ", "")
        include_vat = True

        if vat_number:
            result = vat_api.validate_vat_number(vat_number)
            if not result["valid"]:
                price = calculate_price(years, "SEK", include_vat=True)
                return render(
                    request,
                    "subscriptions/pay.html",
                    {
                        "years_range": years_range,
                        "max_years": max_years,
                        "price": price,
                        "vat_number": vat_number,
                        "vat_error": result.get("error", _("Invalid VAT number")),
                    },
                )
            include_vat = False

        price = calculate_price(years, "SEK", include_vat=include_vat)

        request.session[_SESSION_KEY] = {
            "years": years,
            "vat_number": vat_number,
            "include_vat": include_vat,
            "price": {k: str(v) for k, v in price.items()},
        }
        return redirect("subscriptions:pay_swish")

    price = calculate_price(1, "SEK", include_vat=True)
    return render(
        request,
        "subscriptions/pay.html",
        {
            "years_range": years_range,
            "max_years": max_years,
            "price": price,
            "vat_number": "",
        },
    )


@login_required
def pay_price_partial(request):
    """HTMX endpoint: return updated price breakdown when years/VAT changes."""
    max_years = get_max_payable_years(request.user)
    try:
        years = int(request.GET.get("years", 1))
    except (ValueError, TypeError):
        years = 1
    years = max(1, min(years, max_years))

    vat_number = request.GET.get("vat_number", "").strip()
    include_vat = True
    vat_valid = False
    vat_name = ""

    if vat_number:
        result = vat_api.validate_vat_number(vat_number)
        if result["valid"]:
            include_vat = False
            vat_valid = True
            vat_name = result.get("name", "")

    price = calculate_price(years, "SEK", include_vat=include_vat)
    return render(
        request,
        "subscriptions/_price_breakdown.html",
        {
            "price": price,
            "vat_valid": vat_valid,
            "vat_name": vat_name,
            "vat_number": vat_number,
        },
    )


# ---------------------------------------------------------------------------
# Swish payment
# ---------------------------------------------------------------------------


@login_required
def pay_swish(request):
    intent = request.session.get(_SESSION_KEY)
    if not intent:
        return redirect("subscriptions:pay")

    if request.method == "POST":
        phone = request.POST.get("phone", "").strip()
        if not phone:
            return render(
                request,
                "subscriptions/pay_swish.html",
                {
                    "intent": intent,
                    "phone_error": _("Please enter your Swish phone number."),
                },
            )

        with transaction.atomic():
            invoice_number = generate_invoice_number()
            payment = Payment.objects.create(
                user=request.user,
                invoice_number=invoice_number,
                years=intent["years"],
                discount_pct=intent["price"]["discount_pct"],
                amount_excl_vat=intent["price"]["amount_excl_vat"],
                vat_rate=intent["price"]["vat_rate"],
                vat_amount=intent["price"]["vat_amount"],
                amount_incl_vat=intent["price"]["amount_incl_vat"],
                currency=intent["price"]["currency"],
                vat_number=intent.get("vat_number", ""),
                payment_method=Payment.METHOD_SWISH,
                status=Payment.STATUS_PENDING,
            )

        callback_url = request.build_absolute_uri("/subscriptions/swish/callback/")
        message = f"Bookmarks {intent['years']} yr"

        try:
            result = swish_api.create_payment(
                payment_ref=payment.id,
                payer_alias=phone,
                amount=intent["price"]["amount_incl_vat"],
                message=message,
                callback_url=callback_url,
            )
            payment.swish_payment_id = result["swish_id"]
            payment.save(update_fields=["swish_payment_id", "updated_at"])
        except swish_api.SwishError as exc:
            payment.status = Payment.STATUS_FAILED
            payment.save(update_fields=["status", "updated_at"])
            logger.error("Swish initiation failed for payment %s: %s", payment.id, exc)
            return render(
                request,
                "subscriptions/pay_swish.html",
                {
                    "intent": intent,
                    "swish_error": str(exc)
                    or _("Could not initiate Swish payment. Please try again."),
                },
            )

        del request.session[_SESSION_KEY]
        return redirect("subscriptions:swish_wait", payment_id=payment.id)

    return render(request, "subscriptions/pay_swish.html", {"intent": intent})


@login_required
def swish_wait(request, payment_id: str):
    payment = get_object_or_404(Payment, pk=payment_id, user=request.user)
    return render(request, "subscriptions/swish_wait.html", {"payment": payment})


@login_required
def swish_status(request, payment_id: str):
    """HTMX polling endpoint — returns a partial with current payment status."""
    payment = get_object_or_404(Payment, pk=payment_id, user=request.user)

    if payment.status == Payment.STATUS_PAID:
        response = HttpResponse("")
        response["HX-Redirect"] = f"/subscriptions/success/{payment.id}/"
        return response

    if payment.status in (Payment.STATUS_FAILED, Payment.STATUS_CANCELLED):
        return render(
            request,
            "subscriptions/_swish_status.html",
            {
                "payment": payment,
                "terminal": True,
            },
        )

    # Query Swish for live status
    if payment.swish_payment_id:
        try:
            data = swish_api.get_payment_status(payment.swish_payment_id)
            swish_status = data.get("status", "")

            if swish_status == "PAID":
                payment.status = Payment.STATUS_PAID
                payment.swish_payment_reference = data.get("paymentReference", "")
                payment.paid_at = timezone.now()
                payment.save(
                    update_fields=[
                        "status",
                        "swish_payment_reference",
                        "paid_at",
                        "updated_at",
                    ]
                )
                extend_subscription(request.user, payment.years)
                response = HttpResponse("")
                response["HX-Redirect"] = f"/subscriptions/success/{payment.id}/"
                return response

            if swish_status in ("DECLINED", "ERROR", "CANCELLED"):
                payment.status = (
                    Payment.STATUS_CANCELLED
                    if swish_status == "CANCELLED"
                    else Payment.STATUS_FAILED
                )
                payment.save(update_fields=["status", "updated_at"])
                return render(
                    request,
                    "subscriptions/_swish_status.html",
                    {
                        "payment": payment,
                        "terminal": True,
                    },
                )

        except swish_api.SwishError as exc:
            logger.warning("Swish status poll error for %s: %s", payment.id, exc)

    return render(
        request,
        "subscriptions/_swish_status.html",
        {
            "payment": payment,
            "terminal": False,
        },
    )


@csrf_exempt
@require_POST
def swish_callback(request):
    """Swish payment callback — handles real-time notifications in production."""
    import json

    try:
        data = json.loads(request.body)
    except Exception:
        return HttpResponse(status=400)

    payment_ref = data.get("payeePaymentReference", "")
    swish_status = data.get("status", "")

    try:
        payment = Payment.objects.get(id=payment_ref)
    except Payment.DoesNotExist:
        logger.warning("Swish callback for unknown payment ref %s", payment_ref)
        return HttpResponse(status=200)

    if payment.status == Payment.STATUS_PAID:
        return HttpResponse(status=200)

    if swish_status == "PAID":
        payment.status = Payment.STATUS_PAID
        payment.swish_payment_reference = data.get("paymentReference", "")
        payment.paid_at = timezone.now()
        payment.save(
            update_fields=["status", "swish_payment_reference", "paid_at", "updated_at"]
        )
        extend_subscription(payment.user, payment.years)
    elif swish_status in ("DECLINED", "ERROR"):
        payment.status = Payment.STATUS_FAILED
        payment.save(update_fields=["status", "updated_at"])
    elif swish_status == "CANCELLED":
        payment.status = Payment.STATUS_CANCELLED
        payment.save(update_fields=["status", "updated_at"])

    return HttpResponse(status=200)


# ---------------------------------------------------------------------------
# Success & invoice
# ---------------------------------------------------------------------------


@login_required
def success(request, payment_id: str):
    payment = get_object_or_404(Payment, pk=payment_id, user=request.user)
    return render(request, "subscriptions/success.html", {"payment": payment})


@login_required
def invoice(request, payment_id: str):
    payment = get_object_or_404(Payment, pk=payment_id, user=request.user)
    return render(request, "subscriptions/invoice.html", {"payment": payment})
