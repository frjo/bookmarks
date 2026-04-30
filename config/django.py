# ---------------------------------------------------------------------------
# Django settings for bookmarks project.
# ---------------------------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "django_htmx",
    "django_nh3",
    "home",
    "accounts",
    "links",
    "subscriptions",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "subscriptions.middleware.SubscriptionWarningMiddleware",
]

ROOT_URLCONF = "config.urls"

WSGI_APPLICATION = "config.wsgi.application"

ATOMIC_REQUESTS = True

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["accounts.backends.PasskeyBackend"]

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

# ---------------------------------------------------------------------------
# Internationalisation
# ---------------------------------------------------------------------------
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
DATE_FORMAT = "j N Y"
DATETIME_FORMAT = "j N Y, H:i"
SHORT_DATE_FORMAT = "Y-m-d"
SHORT_DATETIME_FORMAT = "Y-m-d H:i e"
