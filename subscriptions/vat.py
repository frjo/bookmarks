"""EU VIES VAT number validation via SOAP."""

import logging

import httpx

logger = logging.getLogger(__name__)

_VIES_URL = "https://ec.europa.eu/taxation_customs/vies/services/checkVatService"

_SOAP_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/"
                   xmlns:tns="urn:ec.europa.eu:taxud:vies:services:checkVat:types">
  <SOAP-ENV:Body>
    <tns:checkVat>
      <tns:countryCode>{country_code}</tns:countryCode>
      <tns:vatNumber>{vat_number}</tns:vatNumber>
    </tns:checkVat>
  </SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""


def validate_vat_number(vat_number: str) -> dict:
    """
    Validate a VAT number against EU VIES.
    Returns {'valid': bool, 'name': str, 'vat_number': str} or {'valid': False, 'error': str}.
    """
    vat_number = vat_number.strip().upper().replace(" ", "").replace(".", "")

    if len(vat_number) < 4 or not vat_number[:2].isalpha():
        return {
            "valid": False,
            "error": "Invalid VAT number format (expected e.g. SE556000000001)",
        }

    country_code = vat_number[:2]
    number = vat_number[2:]

    body = _SOAP_TEMPLATE.format(country_code=country_code, vat_number=number).encode(
        "utf-8"
    )

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(
                _VIES_URL,
                content=body,
                headers={"Content-Type": "text/xml; charset=utf-8"},
            )

        if resp.status_code != 200:
            return {
                "valid": False,
                "error": f"VIES service unavailable ({resp.status_code})",
            }

        text = resp.text

        if "<valid>true</valid>" in text:
            name = _extract_xml(text, "name") or ""
            return {"valid": True, "name": name, "vat_number": vat_number}

        if "<valid>false</valid>" in text:
            return {"valid": False, "error": "VAT number not registered in VIES"}

        return {"valid": False, "error": "Unexpected response from VIES"}

    except httpx.TimeoutException:
        logger.warning("VIES timeout for %s", vat_number)
        return {"valid": False, "error": "VIES service timed out — please try again"}
    except Exception as exc:
        logger.error("VIES error for %s: %s", vat_number, exc)
        return {"valid": False, "error": "Could not reach VIES service"}


def _extract_xml(text: str, tag: str) -> str:
    start = text.find(f"<{tag}>")
    if start == -1:
        return ""
    start += len(tag) + 2
    end = text.find(f"</{tag}>", start)
    return text[start:end].strip() if end != -1 else ""
