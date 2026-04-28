import os
import sys
from pathlib import Path

from environs import env

from .django import *  # noqa

BASE_DIR = Path(__file__).resolve().parent.parent

TESTING = "test" in sys.argv or "PYTEST_VERSION" in os.environ

env.read_env()

# ---------------------------------------------------------------------------
# App settings
# ---------------------------------------------------------------------------
BOOKMARKS_PER_PAGE = 50

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
LAX_RATE_LIMIT = env.str("LAX_RATE_LIMIT", "1/s")
STRICT_RATE_LIMIT = env.str("STRICT_RATE_LIMIT", "10/h")

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
# Cache
# ---------------------------------------------------------------------------

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "bookmarks",
    },
}

# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "assets"]
STATIC_ROOT = BASE_DIR / "static"

# ---------------------------------------------------------------------------
# Development
# ---------------------------------------------------------------------------
if DEBUG and not TESTING:
    INSTALLED_APPS = [
        *INSTALLED_APPS,
        "django_extensions",
        "debug_toolbar",
    ]
    MIDDLEWARE = [
        "debug_toolbar.middleware.DebugToolbarMiddleware",
        *MIDDLEWARE,
    ]
    INTERNAL_IPS = ["127.0.0.1"]

    # We disable all panels by default here since some of them (SQL, Template,
    # Profiling) can be very CPU intensive for this site.  However disabled panels
    # can be easily toggled on in the UI.
    DEBUG_TOOLBAR_CONFIG = {
        "DISABLE_PANELS": {
            "debug_toolbar.panels.history.HistoryPanel",
            "debug_toolbar.panels.versions.VersionsPanel",
            "debug_toolbar.panels.timer.TimerPanel",
            "debug_toolbar.panels.settings.SettingsPanel",
            "debug_toolbar.panels.headers.HeadersPanel",
            "debug_toolbar.panels.request.RequestPanel",
            "debug_toolbar.panels.sql.SQLPanel",
            "debug_toolbar.panels.staticfiles.StaticFilesPanel",
            "debug_toolbar.panels.templates.TemplatesPanel",
            "debug_toolbar.panels.alerts.AlertsPanel",
            "debug_toolbar.panels.cache.CachePanel",
            "debug_toolbar.panels.signals.SignalsPanel",
            "debug_toolbar.panels.community.CommunityPanel",
            "debug_toolbar.panels.redirects.RedirectsPanel",
            "debug_toolbar.panels.profiling.ProfilingPanel",
        },
        "SHOW_COLLAPSED": True,
    }
