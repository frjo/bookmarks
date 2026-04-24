from pathlib import Path

from environs import env

from .django import *  # noqa

BASE_DIR = Path(__file__).resolve().parent.parent

env.read_env()


# ---------------------------------------------------------------------------
# App settings
# ---------------------------------------------------------------------------
BOOKMARKS_PER_PAGE = 30

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
SECRET_KEY = env.str("DJANGO_SECRET_KEY")
DEBUG = env.bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", ["localhost", "127.0.0.1"])
LANGUAGE_CODE = env.str("LANGUAGE_CODE", "en")

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env.str("DB_NAME", "bookmarks"),
        "USER": env.str("DB_USER", "postgres"),
        "PASSWORD": env.str("DB_PASSWORD", ""),
        "HOST": env.str("DB_HOST", "localhost"),
        "PORT": env.int("DB_PORT", 5432),
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ---------------------------------------------------------------------------
# WebAuthn / Passkeys
# ---------------------------------------------------------------------------
WEBAUTHN_RP_ID = env.str("WEBAUTHN_RP_ID", "localhost")
WEBAUTHN_RP_NAME = env.str("WEBAUTHN_RP_NAME", "Bookmarks")
WEBAUTHN_ORIGIN = env.str("WEBAUTHN_ORIGIN", "http://localhost:8000")

# ---------------------------------------------------------------------------
# Rate-Limit configuration
# ---------------------------------------------------------------------------
DEFAULT_RATE_LIMIT = env.str("DEFAULT_RATE_LIMIT", "5/m")

# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------
SESSION_COOKIE_AGE = env.int("SESSION_COOKIE_AGE", 60 * 60 * 24 * 7 * 2)  # 2 weeks
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "assets"]
STATIC_ROOT = BASE_DIR / "static"
