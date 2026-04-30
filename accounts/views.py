import base64
import json
import logging
import secrets

import nh3
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST
from django_ratelimit.decorators import ratelimit
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes
from webauthn.helpers.structs import (
    AuthenticationCredential,
    AuthenticatorAssertionResponse,
    AuthenticatorAttestationResponse,
    AuthenticatorSelectionCriteria,
    AuthenticatorTransport,
    PublicKeyCredentialDescriptor,
    RegistrationCredential,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from .models import APIToken, User, WebAuthnCredential

logger = logging.getLogger(__name__)

_MAX_PASSKEYS = 10


def _registration_options(user_handle, username, exclude_credentials=None):
    return generate_registration_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        rp_name=settings.WEBAUTHN_RP_NAME,
        user_id=user_handle,
        user_name=username,
        user_display_name=username,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=exclude_credentials or [],
    )


def _verify_registration(data, challenge):
    resp = data["response"]
    transports = [
        AuthenticatorTransport(t)
        for t in resp.get("transports", [])
        if t in AuthenticatorTransport._value2member_map_
    ]
    credential = RegistrationCredential(
        id=data["id"],
        raw_id=base64url_to_bytes(data["rawId"]),
        response=AuthenticatorAttestationResponse(
            client_data_json=base64url_to_bytes(resp["clientDataJSON"]),
            attestation_object=base64url_to_bytes(resp["attestationObject"]),
            transports=transports or None,
        ),
    )
    verification = verify_registration_response(
        credential=credential,
        expected_challenge=challenge,
        expected_rp_id=settings.WEBAUTHN_RP_ID,
        expected_origin=settings.WEBAUTHN_ORIGIN,
    )
    return verification, [t.value for t in transports]


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


@require_GET
def register(request):
    if request.user.is_authenticated:
        return redirect("/")
    return render(request, "accounts/register.html")


@require_POST
@ratelimit(key="ip", rate=settings.DEFAULT_RATE_LIMIT)
def register_username(request):
    """Validate and store a chosen username in the session (optional)."""
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": _("Invalid request body.")}, status=400)

    username = nh3.clean(body.get("username", "").strip(), tags=set())
    if username:
        if not (3 <= len(username) <= 50):
            return JsonResponse(
                {"error": _("Username must be 3–50 characters.")},
                status=400,
            )
        if User.objects.filter(username=username).exists():
            return JsonResponse(
                {"error": _("That username is already taken.")}, status=400
            )

    request.session["reg_username"] = username
    return JsonResponse({"status": "ok"})


@require_POST
@ratelimit(key="ip", rate=settings.DEFAULT_RATE_LIMIT)
def register_begin(request):
    """Begin passkey registration for a new user (username may be absent)."""
    if "reg_username" not in request.session:
        return JsonResponse(
            {"error": "No registration session found. Please start over."}, status=400
        )

    username = request.session["reg_username"]
    if username:
        user_handle = base64.urlsafe_b64encode(username.encode()).rstrip(b"=")
        display_name = username
    else:
        user_handle = base64.urlsafe_b64encode(secrets.token_bytes(16))
        display_name = "user"

    options = _registration_options(user_handle, display_name)
    request.session["reg_challenge"] = base64.b64encode(options.challenge).decode()
    return JsonResponse(json.loads(options_to_json(options)))


@require_POST
@ratelimit(key="ip", rate=settings.DEFAULT_RATE_LIMIT)
def register_complete(request):
    challenge_b64 = request.session.get("reg_challenge", "")
    username = request.session.get("reg_username", "") or None

    if not challenge_b64 or "reg_username" not in request.session:
        return JsonResponse(
            {"error": _("Registration session expired. Please try again.")}, status=400
        )

    if username and User.objects.filter(username=username).exists():
        return JsonResponse({"error": _("That username is already taken.")}, status=400)

    try:
        challenge = base64.b64decode(challenge_b64)
        data = json.loads(request.body)
        verification, transports = _verify_registration(data, challenge)
    except Exception:
        logger.exception("WebAuthn registration verification failed")
        return JsonResponse(
            {"error": _("Verification failed. Please try again.")}, status=400
        )

    user = User.objects.create_user(username=username)
    WebAuthnCredential.objects.create(
        user=user,
        credential_id=bytes(verification.credential_id),
        public_key=bytes(verification.credential_public_key),
        sign_count=verification.sign_count,
        transports=transports,
        name=nh3.clean(data.get("name", "").strip(), tags=set()),
    )

    request.session.pop("reg_challenge", None)
    request.session.pop("reg_username", None)

    login(request, user, backend="accounts.backends.PasskeyBackend")
    logger.info(
        "audit: registration complete user=%s ip=%s",
        user.pk,
        request.META.get("REMOTE_ADDR"),
    )
    return JsonResponse({"status": "ok"})


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


@require_GET
def login_view(request):
    if request.user.is_authenticated:
        return redirect("/")
    return render(request, "accounts/login.html")


@require_POST
@ratelimit(key="ip", rate=settings.DEFAULT_RATE_LIMIT)
def login_begin(request):
    options = generate_authentication_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    request.session["auth_challenge"] = base64.b64encode(options.challenge).decode()
    return JsonResponse(json.loads(options_to_json(options)))


@require_POST
@ratelimit(key="ip", rate=settings.DEFAULT_RATE_LIMIT)
def login_complete(request):
    challenge_b64 = request.session.get("auth_challenge", "")
    if not challenge_b64:
        return JsonResponse(
            {"error": _("Authentication session expired. Please try again.")},
            status=400,
        )

    try:
        challenge = base64.b64decode(challenge_b64)
        data = json.loads(request.body)
        resp = data["response"]
        raw_id = base64url_to_bytes(data["rawId"])
        credential = AuthenticationCredential(
            id=data["id"],
            raw_id=raw_id,
            response=AuthenticatorAssertionResponse(
                client_data_json=base64url_to_bytes(resp["clientDataJSON"]),
                authenticator_data=base64url_to_bytes(resp["authenticatorData"]),
                signature=base64url_to_bytes(resp["signature"]),
                user_handle=base64url_to_bytes(resp["userHandle"])
                if resp.get("userHandle")
                else None,
            ),
        )

        with transaction.atomic():
            stored = (
                WebAuthnCredential.objects.select_related("user")
                .select_for_update()
                .get(credential_id=bytes(raw_id))
            )

            verification = verify_authentication_response(
                credential=credential,
                expected_challenge=challenge,
                expected_rp_id=settings.WEBAUTHN_RP_ID,
                expected_origin=settings.WEBAUTHN_ORIGIN,
                credential_public_key=bytes(stored.public_key),
                credential_current_sign_count=stored.sign_count,
            )

            if (
                verification.new_sign_count != 0 or stored.sign_count != 0
            ) and verification.new_sign_count <= stored.sign_count:
                logger.warning(
                    "Possible cloned authenticator for credential %s (user %s): stored=%d new=%d",
                    stored.pk,
                    stored.user_id,
                    stored.sign_count,
                    verification.new_sign_count,
                )
                return JsonResponse(
                    {"error": _("Authentication failed. Please try again.")}, status=401
                )

            stored.sign_count = verification.new_sign_count
            stored.last_used_at = timezone.now()
            stored.save(update_fields=["sign_count", "last_used_at"])

    except WebAuthnCredential.DoesNotExist:
        logger.warning(
            "audit: login failed (unknown credential) ip=%s",
            request.META.get("REMOTE_ADDR"),
        )
        return JsonResponse({"error": _("Passkey not recognised.")}, status=401)
    except Exception:
        logger.exception("WebAuthn authentication verification failed")
        logger.warning(
            "audit: login failed (verification error) ip=%s",
            request.META.get("REMOTE_ADDR"),
        )
        return JsonResponse(
            {"error": _("Authentication failed. Please try again.")}, status=401
        )

    request.session.pop("auth_challenge", None)

    login(request, stored.user, backend="accounts.backends.PasskeyBackend")
    logger.info(
        "audit: login success user=%s ip=%s",
        stored.user.pk,
        request.META.get("REMOTE_ADDR"),
    )

    next_url = data.get("next", "").strip()
    if not url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}
    ):
        next_url = "/"

    return JsonResponse({"status": "ok", "redirect_url": next_url or "/"})


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


@require_POST
def logout_view(request):
    logout(request)
    return redirect(settings.LOGOUT_REDIRECT_URL)


# ---------------------------------------------------------------------------
# Passkey management (authenticated users)
# ---------------------------------------------------------------------------


@login_required
@require_POST
@ratelimit(key="user", rate=settings.DEFAULT_RATE_LIMIT)
def passkey_add_begin(request):
    """Begin adding a new passkey for an already-authenticated user."""
    user = request.user
    if user.credentials.count() >= _MAX_PASSKEYS:
        return JsonResponse(
            {
                "error": _("You have reached the maximum number of passkeys (%(max)s).")
                % {"max": _MAX_PASSKEYS}
            },
            status=400,
        )
    user_handle = base64.urlsafe_b64encode(user.username.encode()).rstrip(b"=")
    existing = [
        PublicKeyCredentialDescriptor(id=bytes(c.credential_id))
        for c in user.credentials.all()
    ]
    options = _registration_options(
        user_handle, user.username, exclude_credentials=existing
    )
    request.session["add_passkey_challenge"] = base64.b64encode(
        options.challenge
    ).decode()
    return JsonResponse(json.loads(options_to_json(options)))


@login_required
@require_POST
@ratelimit(key="user", rate=settings.DEFAULT_RATE_LIMIT)
def passkey_add_complete(request):
    """Complete adding a new passkey for an already-authenticated user."""
    challenge_b64 = request.session.get("add_passkey_challenge", "")
    if not challenge_b64:
        return JsonResponse(
            {"error": _("Session expired. Please try again.")}, status=400
        )

    try:
        challenge = base64.b64decode(challenge_b64)
        data = json.loads(request.body)
        verification, transports = _verify_registration(data, challenge)
    except Exception:
        logger.exception("WebAuthn passkey-add verification failed")
        return JsonResponse(
            {"error": _("Verification failed. Please try again.")}, status=400
        )

    credential = WebAuthnCredential.objects.create(
        user=request.user,
        credential_id=bytes(verification.credential_id),
        public_key=bytes(verification.credential_public_key),
        sign_count=verification.sign_count,
        transports=transports,
        name=nh3.clean(data.get("name", "").strip(), tags=set()),
    )
    logger.info(
        "audit: passkey added user=%s credential=%s ip=%s",
        request.user.pk,
        credential.pk,
        request.META.get("REMOTE_ADDR"),
    )

    request.session.pop("add_passkey_challenge", None)
    return JsonResponse({"status": "ok"})


@login_required
@require_POST
@ratelimit(key="user", rate=settings.DEFAULT_RATE_LIMIT)
def passkey_delete(request, pk: str):
    """Delete one of the authenticated user's passkeys."""
    user = request.user
    if user.credentials.count() <= 1:
        messages.error(request, _("You must keep at least one passkey."))
        return redirect("account", slug=user.slug)
    try:
        credential = user.credentials.get(pk=pk)
    except user.credentials.model.DoesNotExist:
        messages.error(request, _("Passkey not found."))
        return redirect("account", slug=user.slug)
    credential.delete()
    logger.info(
        "audit: passkey deleted user=%s credential=%s ip=%s",
        user.pk,
        pk,
        request.META.get("REMOTE_ADDR"),
    )
    messages.success(request, _("Passkey deleted."))
    return redirect("account", slug=user.slug)


# ---------------------------------------------------------------------------
# Account
# ---------------------------------------------------------------------------


@login_required
@ratelimit(key="user", rate=settings.DEFAULT_RATE_LIMIT)
def account_view(request, slug: str = ""):
    user = request.user
    api_token = APIToken.objects.filter(user=user).first()
    credentials = user.credentials.order_by("created_at")

    if request.method == "POST":
        action = request.POST.get("action")

        if action not in {"update_username", "regenerate_token"}:
            return HttpResponseBadRequest()

        if action == "update_username":
            new_username = nh3.clean(
                request.POST.get("username", "").strip(), tags=set()
            )
            if not (3 <= len(new_username) <= 50):
                messages.error(
                    request,
                    _("Username must be 3–50 characters."),
                )
            elif (
                new_username != user.username
                and User.objects.filter(username=new_username).exists()
            ):
                messages.error(request, _("That username is already taken."))
            else:
                old_username = user.username
                user.username = new_username
                user.save(update_fields=["username"])
                logger.info(
                    "audit: username changed user=%s old=%s new=%s ip=%s",
                    user.pk,
                    old_username,
                    new_username,
                    request.META.get("REMOTE_ADDR"),
                )
                messages.success(request, _("Username updated."))

        elif action == "regenerate_token":
            new_token = APIToken.generate_token()
            api_token, _created = APIToken.objects.update_or_create(
                user=user,
                defaults={"token": new_token},
            )
            logger.info(
                "audit: api token regenerated user=%s ip=%s",
                user.pk,
                request.META.get("REMOTE_ADDR"),
            )
            messages.success(request, _("API token regenerated."))

        return redirect("account", slug=user.slug)

    return render(
        request,
        "accounts/account.html",
        {
            "api_token": api_token,
            "credentials": credentials,
            "subscription_free_limit": settings.SUBSCRIPTION_FREE_LIMIT,
        },
    )
