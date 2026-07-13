"""
Django settings for the Agentarium modular monolith (Core modules).

Per ARCHITECTURE.md ADR-006: this is the same settings module used whether the
process is running as the ASGI app (config.asgi:application) or as the Celery
worker entrypoint (config.celery:app) — one codebase, two entrypoints.
"""

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "insecure-dev-key-do-not-use-in-production")
DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() == "true"
_raw_hosts = os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",")
ALLOWED_HOSTS = [h.strip() for h in _raw_hosts if h.strip()]

# The web client (apps/web) runs on a different origin (e.g. localhost:3000
# in dev) than the API (localhost:8000) — without this, every browser
# fetch() from the web app is blocked by the browser itself before it even
# reaches Django. Defaults to the local Next.js dev server; real deployments
# must set CORS_ALLOWED_ORIGINS to their actual web app origin(s).
_raw_cors_origins = os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:3000").split(",")
CORS_ALLOWED_ORIGINS = [o.strip() for o in _raw_cors_origins if o.strip()]
# No CORS_ALLOW_CREDENTIALS — auth is a Bearer token in the Authorization
# header, not a cookie, so credentialed CORS isn't needed.

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",  # per-device revocation, SECURITY.md §2
    "corsheaders",
    "core",
    "ai",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",  # must sit above CommonMiddleware
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
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

WSGI_APPLICATION = None  # ASGI-only per ARCHITECTURE.md ADR-006 — no WSGI entrypoint is served.

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "agentarium"),
        "USER": os.environ.get("DB_USER", "agentarium"),
        "PASSWORD": os.environ.get("DB_PASSWORD", "agentarium"),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
    }
}

AUTH_USER_MODEL = "core.User"

# Argon2id first per SECURITY.md §2 ("a modern, salted, memory-hard algorithm").
# The rest are kept only so Django can still verify pre-existing hashes of
# those types; every new/rehashed password uses Argon2PasswordHasher.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
# Fallback only — every Core model defines an explicit UUIDv7 `id` per DATABASE.md §1.
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    # Default-deny per SECURITY.md's authorization posture — individual views
    # (register/login/refresh/oauth callback/mfa login-verify) opt into
    # AllowAny explicitly rather than every other endpoint opting into auth.
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=14),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# Envelope encryption key for provider_credentials.encrypted_key and
# users.mfa_secret, per SECURITY.md §6. MVP: a single Fernet key from env;
# a dedicated secrets manager is the documented V2+ upgrade path. The default
# below is an insecure, publicly-known dev key (same pattern as SECRET_KEY's
# dev fallback) — every real deployment must set FIELD_ENCRYPTION_KEY itself.
FIELD_ENCRYPTION_KEY = os.environ.get(
    "FIELD_ENCRYPTION_KEY", "cejGCUCoSNmRYVMLQQQX9KGwbOqCiauvwWsHIWy-RPY="
)

MFA_ISSUER_NAME = "Agentarium"

GOOGLE_OAUTH_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")
GOOGLE_OAUTH_CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "")

# Celery — broker/result backend both point at Redis per ARCHITECTURE.md §4.2.
CELERY_BROKER_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
