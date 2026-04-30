import io
import xml.etree.ElementTree as ET
from functools import lru_cache
from urllib.parse import quote

import segno
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .utils import calculate_price

_MAX_YEARS = 6
_QR_SIZE = 200

_SVG_NS = "http://www.w3.org/2000/svg"

ET.register_namespace("", _SVG_NS)


@lru_cache(maxsize=256)
def _swish_qr_svg(merchant: str, amount: int, message: str) -> str:
    """Generate a Swish QR code as inline SVG with the Swish logo centered.

    Format: C<payee>;<amount with comma decimal>;<url-encoded message>;<lock_mask>
    lock_mask=0 locks all fields (amount and message not editable in the Swish app).
    """
    data = f"C{merchant};{amount},00;{quote(message)};0"
    qr = segno.make(data, error="M")
    buf = io.BytesIO()
    qr.save(buf, kind="svg", scale=4, border=2, xmldecl=False, nl=False)

    root = ET.fromstring(buf.getvalue())
    w = root.get("width", "0")
    root.set("viewBox", f"0 0 {w} {w}")
    root.set("width", str(_QR_SIZE))
    root.set("height", str(_QR_SIZE))

    style = ET.Element(f"{{{_SVG_NS}}}style")
    style.text = (
        "@media(prefers-color-scheme:dark){"
        ".segno{background:#1a1a1a}"
        ".qrline{stroke:#fff}"
        "}"
    )
    root.insert(0, style)

    w = float(w)
    logo_size = round(w * 0.20)
    offset = round((w - logo_size) / 2)

    img = ET.SubElement(root, f"{{{_SVG_NS}}}image")
    img.set("x", str(offset))
    img.set("y", str(offset))
    img.set("width", str(logo_size))
    img.set("height", str(logo_size))
    img.set("href", "/static/images/swish-qr-logo.svg")

    return ET.tostring(root, encoding="unicode")


@login_required
def pay(request):
    merchant = getattr(settings, "SWISH_MERCHANT_NUMBER", "")
    options = []
    for years in range(1, _MAX_YEARS + 1):
        price = calculate_price(years, "SEK", include_vat=True)
        amount = int(price["amount_incl_vat"])
        year_label = "year" if years == 1 else "years"
        message = f"Bookmarks {years} {year_label}: {request.user.id}"
        svg = _swish_qr_svg(merchant, amount, message) if merchant else ""
        options.append(
            {
                "years": years,
                "price": price,
                "message": message,
                "svg": svg,
            }
        )

    return render(
        request,
        "subscriptions/pay.html",
        {
            "options": options,
            "subscription_free_limit": settings.SUBSCRIPTION_FREE_LIMIT,
        },
    )
