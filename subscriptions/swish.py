"""
Swish e-commerce API client.

Environments:
  simulator  → https://mss.cpc.getswish.net/swish-cpcapi/api/v2
  production → https://cpc.getswish.net/swish-cpcapi/api/v2

Simulator certificates are available at https://developer.swish.nu/documentation/environments
  - Download the test merchant certificate package (.p12, password: swish)
  - Convert to PEM:
      openssl pkcs12 -in cert.p12 -clcerts -nokeys -out swish_cert.pem -passing pass:swish
      openssl pkcs12 -in cert.p12 -nocerts -nodes -out swish_key.pem  -passing pass:swish
  - Set SWISH_CERT_PATH and SWISH_KEY_PATH in .env
  - Optionally set SWISH_CA_CERT_PATH to the Swish root CA bundle.
    If omitted in simulator mode, TLS verification is skipped.
"""

import logging
import uuid

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

_SIMULATOR_BASE = "https://mss.cpc.getswish.net/swish-cpcapi/api/v2"
_PRODUCTION_BASE = "https://cpc.getswish.net/swish-cpcapi/api/v2"


class SwishError(Exception):
    pass


def _base_url() -> str:
    return (
        _SIMULATOR_BASE
        if settings.SWISH_ENVIRONMENT == "simulator"
        else _PRODUCTION_BASE
    )


def _client() -> httpx.Client:
    kwargs: dict = {"timeout": 30.0}

    cert_path = getattr(settings, "SWISH_CERT_PATH", "")
    key_path = getattr(settings, "SWISH_KEY_PATH", "")
    ca_cert_path = getattr(settings, "SWISH_CA_CERT_PATH", "")

    if cert_path and key_path:
        kwargs["cert"] = (cert_path, key_path)

    if ca_cert_path:
        kwargs["verify"] = ca_cert_path
    elif settings.SWISH_ENVIRONMENT == "simulator":
        kwargs["verify"] = False

    return httpx.Client(**kwargs)


def create_payment(
    payment_ref: str,
    payer_alias: str,
    amount: str,
    message: str,
    callback_url: str,
) -> dict:
    """
    Create a Swish payment request.
    Returns {'swish_id': str, 'location': str} on success.
    Raises SwishError on failure.
    """
    swish_uuid = uuid.uuid4().hex.upper()
    url = f"{_base_url()}/paymentrequests/{swish_uuid}"

    payload = {
        "payeePaymentReference": payment_ref,
        "callbackUrl": callback_url,
        "payeeAlias": settings.SWISH_MERCHANT_NUMBER,
        "currency": "SEK",
        "payerAlias": _normalise_phone(payer_alias),
        "amount": str(amount),
        "message": message[:50],
    }

    with _client() as client:
        resp = client.put(url, json=payload)

    if resp.status_code == 201:
        location = resp.headers.get("Location", "")
        swish_id = location.rstrip("/").split("/")[-1] or swish_uuid
        return {"swish_id": swish_id, "location": location}

    logger.error("Swish create_payment %s: %s", resp.status_code, resp.text)
    _raise_for_swish_error(resp)


def get_payment_status(swish_id: str) -> dict:
    """
    Fetch the current status of a payment.
    Returns the Swish response dict (keys: id, status, amount, datePaid, …).
    Raises SwishError on failure.
    """
    url = f"{_base_url()}/paymentrequests/{swish_id}"
    with _client() as client:
        resp = client.get(url)

    if resp.status_code == 200:
        return resp.json()

    logger.error("Swish get_payment_status %s: %s", resp.status_code, resp.text)
    _raise_for_swish_error(resp)


def _normalise_phone(phone: str) -> str:
    """Convert a Swedish phone number to Swish format (46XXXXXXXXX)."""
    phone = phone.strip().replace(" ", "").replace("-", "")
    if phone.startswith("+46"):
        return "46" + phone[3:]
    if phone.startswith("0046"):
        return "46" + phone[4:]
    if phone.startswith("0"):
        return "46" + phone[1:]
    if not phone.startswith("46"):
        return "46" + phone
    return phone


def _raise_for_swish_error(resp: httpx.Response):
    try:
        errors = resp.json()
        msg = (
            "; ".join(e.get("errorMessage", "") for e in errors)
            if isinstance(errors, list)
            else str(errors)
        )
    except Exception:
        msg = resp.text or str(resp.status_code)
    raise SwishError(msg)
