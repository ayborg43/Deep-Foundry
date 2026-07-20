"""
Django settings for the Deep-Foundry modular monolith (Core modules).

Per ARCHITECTURE.md ADR-006: this is the same settings module used whether the
process is running as the ASGI app (config.asgi:application) or as the Celery
worker entrypoint (config.celery:app) — one codebase, two entrypoints.
"""

import os
import re
from datetime import timedelta
from pathlib import Path

from cryptography.fernet import Fernet
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
ENVIRONMENT = os.environ.get("APP_ENV", "development").lower()

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "insecure-dev-key-do-not-use-in-production")
DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() == "true"
_raw_hosts = os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",")
ALLOWED_HOSTS = [h.strip() for h in _raw_hosts if h.strip()]
# The Next.js container proxies same-origin browser API calls to the Compose
# service name. This hostname is reachable only on the private Docker network.
if "app" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append("app")

# The web client (apps/web) runs on a different origin (e.g. localhost:3000
# in dev) than the API (localhost:8000) — without this, every browser
# fetch() from the web app is blocked by the browser itself before it even
# reaches Django. Defaults to the local Next.js dev server; real deployments
# must set CORS_ALLOWED_ORIGINS to their actual web app origin(s).
_raw_cors_origins = os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:3000").split(",")
CORS_ALLOWED_ORIGINS = [o.strip() for o in _raw_cors_origins if o.strip()]
_raw_csrf_origins = os.environ.get("CSRF_TRUSTED_ORIGINS", "http://localhost:3000").split(",")
CSRF_TRUSTED_ORIGINS = [o.strip() for o in _raw_csrf_origins if o.strip()]
# No CORS_ALLOW_CREDENTIALS — auth is a Bearer token in the Authorization
# header, not a cookie, so credentialed CORS isn't needed.

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",  # per-device revocation, SECURITY.md §2
    "corsheaders",
    "core",
    "ai",
    "research",
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
        "core.api_token_auth.ApiTokenAuthentication",
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    # Application-level gateway limit from API.md §10. UserRateThrottle also
    # keys unauthenticated auth/bootstrap requests by source IP.
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.UserRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {
        "user": "1000/min",
        "password_reset": "20/hour",
        "telegram_link": "10/hour",
        "telegram_test": "10/hour",
    },
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

MFA_ISSUER_NAME = "Deep-Foundry"

GOOGLE_OAUTH_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")
GOOGLE_OAUTH_CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "")

# Backing store for the `read_file`/`write_file` built-in tools (ai/tool_executor.py).
# Milestone 4 MVP scope only: a per-workspace directory on local disk, jailed
# against path traversal, with no volume mount — contents don't survive a
# container recreation. Durable, MinIO-backed file storage is Memory/Knowledge
# scope (ARCHITECTURE.md §4.3, Milestone 5+), not this milestone's concern.
WORKSPACE_FILES_ROOT = Path(
    os.environ.get("WORKSPACE_FILES_ROOT", str(BASE_DIR / "var" / "workspace_files"))
)

# Built-in web search. The default provider is keyless and bounded; operators
# can replace it with a compatible internal endpoint.
WEB_SEARCH_ENDPOINT = os.environ.get(
    "WEB_SEARCH_ENDPOINT", "https://html.duckduckgo.com/html/"
)
WEB_SEARCH_TIMEOUT_SECONDS = float(os.environ.get("WEB_SEARCH_TIMEOUT_SECONDS", "10"))
WEB_SEARCH_MAX_RESULTS = int(os.environ.get("WEB_SEARCH_MAX_RESULTS", "5"))
WEB_SEARCH_MAX_RESPONSE_BYTES = int(
    os.environ.get("WEB_SEARCH_MAX_RESPONSE_BYTES", str(2 * 1024 * 1024))
)

# Keyless recent-news discovery. GDELT's public DOC API is blended into the
# normal web-search results; DuckDuckGo remains available when it is busy or
# unavailable. The shared cache slot respects GDELT's public request pacing.
NEWS_SEARCH_ENABLED = os.environ.get("NEWS_SEARCH_ENABLED", "true").lower() == "true"
NEWS_SEARCH_ENDPOINT = os.environ.get(
    "NEWS_SEARCH_ENDPOINT", "https://api.gdeltproject.org/api/v2/doc/doc"
)
NEWS_SEARCH_TIMEOUT_SECONDS = float(
    os.environ.get("NEWS_SEARCH_TIMEOUT_SECONDS", "15")
)
NEWS_SEARCH_MAX_RESULTS = int(os.environ.get("NEWS_SEARCH_MAX_RESULTS", "5"))
NEWS_SEARCH_MAX_RESPONSE_BYTES = int(
    os.environ.get("NEWS_SEARCH_MAX_RESPONSE_BYTES", str(2 * 1024 * 1024))
)
NEWS_SEARCH_TIMESPAN = os.environ.get("NEWS_SEARCH_TIMESPAN", "7d")
NEWS_SEARCH_MIN_INTERVAL_SECONDS = float(
    os.environ.get("NEWS_SEARCH_MIN_INTERVAL_SECONDS", "5")
)
NEWS_SEARCH_CACHE_SECONDS = int(os.environ.get("NEWS_SEARCH_CACHE_SECONDS", "900"))

# Built-in public webpage reader. User-provided URLs are resolved and pinned to
# public IPs in ai/web_reader.py; these bounds keep a single model tool call
# from turning into an unbounded download or prompt payload.
WEB_READER_TIMEOUT_SECONDS = float(os.environ.get("WEB_READER_TIMEOUT_SECONDS", "10"))
WEB_READER_MAX_RESPONSE_BYTES = int(
    os.environ.get("WEB_READER_MAX_RESPONSE_BYTES", str(2 * 1024 * 1024))
)
WEB_READER_MAX_TEXT_CHARS = int(os.environ.get("WEB_READER_MAX_TEXT_CHARS", "30000"))
WEB_READER_MAX_REDIRECTS = int(os.environ.get("WEB_READER_MAX_REDIRECTS", "3"))
WEB_READER_MAX_LINKS = int(os.environ.get("WEB_READER_MAX_LINKS", "50"))
WEB_READER_MAX_HEADINGS = int(os.environ.get("WEB_READER_MAX_HEADINGS", "30"))
WEB_READER_USER_AGENT = os.environ.get(
    "WEB_READER_USER_AGENT",
    "Deep-Foundry/1.0 (public webpage reader)",
)
WEB_FETCH_TOTAL_TIMEOUT_SECONDS = float(
    os.environ.get("WEB_FETCH_TOTAL_TIMEOUT_SECONDS", "30")
)
WEB_DOCUMENT_MAX_RESPONSE_BYTES = int(
    os.environ.get("WEB_DOCUMENT_MAX_RESPONSE_BYTES", str(25 * 1024 * 1024))
)

# Responsible research crawling. Crawls execute in Celery and share Redis
# pacing/cache state across worker replicas.
CRAWLER_MAX_PAGES = int(os.environ.get("CRAWLER_MAX_PAGES", "50"))
CRAWLER_MAX_DEPTH = int(os.environ.get("CRAWLER_MAX_DEPTH", "3"))
CRAWLER_MAX_DURATION_SECONDS = float(
    os.environ.get("CRAWLER_MAX_DURATION_SECONDS", "60")
)
CRAWLER_MAX_RATE_LIMIT_SECONDS = float(
    os.environ.get("CRAWLER_MAX_RATE_LIMIT_SECONDS", "10")
)
CRAWLER_MAX_ROBOTS_BYTES = int(
    os.environ.get("CRAWLER_MAX_ROBOTS_BYTES", str(512 * 1024))
)
CRAWLER_MAX_SITEMAP_BYTES = int(
    os.environ.get("CRAWLER_MAX_SITEMAP_BYTES", str(2 * 1024 * 1024))
)
CRAWLER_MAX_SITEMAPS = int(os.environ.get("CRAWLER_MAX_SITEMAPS", "5"))
CRAWLER_MAX_SITEMAP_URLS = int(os.environ.get("CRAWLER_MAX_SITEMAP_URLS", "500"))
CRAWLER_ROBOTS_CACHE_SECONDS = int(
    os.environ.get("CRAWLER_ROBOTS_CACHE_SECONDS", "86400")
)
CRAWLER_PAGE_CACHE_SECONDS = int(
    os.environ.get("CRAWLER_PAGE_CACHE_SECONDS", "3600")
)

# Public document extraction bounds.
DOCUMENT_MAX_TEXT_CHARS = int(os.environ.get("DOCUMENT_MAX_TEXT_CHARS", "200000"))
DOCUMENT_MAX_PAGES = int(os.environ.get("DOCUMENT_MAX_PAGES", "300"))
DOCUMENT_MAX_CSV_ROWS = int(os.environ.get("DOCUMENT_MAX_CSV_ROWS", "5000"))
DOCUMENT_MAX_CELL_CHARS = int(os.environ.get("DOCUMENT_MAX_CELL_CHARS", "10000"))
DOCUMENT_MAX_ZIP_MEMBERS = int(os.environ.get("DOCUMENT_MAX_ZIP_MEMBERS", "1000"))
DOCUMENT_MAX_UNCOMPRESSED_BYTES = int(
    os.environ.get("DOCUMENT_MAX_UNCOMPRESSED_BYTES", str(100 * 1024 * 1024))
)

# Bounded structured extraction.
EXTRACTION_MAX_FIELDS = int(os.environ.get("EXTRACTION_MAX_FIELDS", "50"))
EXTRACTION_MAX_ARRAY_ITEMS = int(os.environ.get("EXTRACTION_MAX_ARRAY_ITEMS", "100"))
EXTRACTION_MAX_VALUE_CHARS = int(os.environ.get("EXTRACTION_MAX_VALUE_CHARS", "10000"))
EXTRACTION_MAX_INPUT_CHARS = int(os.environ.get("EXTRACTION_MAX_INPUT_CHARS", "60000"))

# Isolated JavaScript browser client. Chromium has no direct egress in Compose;
# it reaches the internet only through the public-address-validating proxy.
BROWSER_SERVICE_URL = os.environ.get("BROWSER_SERVICE_URL", "")
BROWSER_SERVICE_TOKEN = os.environ.get(
    "BROWSER_SERVICE_TOKEN", os.environ.get("INTERNAL_API_TOKEN", "")
)
BROWSER_SERVICE_TIMEOUT_SECONDS = float(
    os.environ.get("BROWSER_SERVICE_TIMEOUT_SECONDS", "25")
)
BROWSER_SERVICE_MAX_RESPONSE_BYTES = int(
    os.environ.get("BROWSER_SERVICE_MAX_RESPONSE_BYTES", str(2 * 1024 * 1024))
)

# Website monitoring comparison and retention.
MONITOR_MEANINGFUL_CHANGE_RATIO = float(
    os.environ.get("MONITOR_MEANINGFUL_CHANGE_RATIO", "0.01")
)
MONITOR_MAX_DIFF_LINES = int(os.environ.get("MONITOR_MAX_DIFF_LINES", "500"))
MONITOR_MAX_SNAPSHOT_CHARS = int(
    os.environ.get("MONITOR_MAX_SNAPSHOT_CHARS", "500000")
)
MONITOR_SNAPSHOT_RETENTION = int(
    os.environ.get("MONITOR_SNAPSHOT_RETENTION", "50")
)

# Instance-wide DeepSeek Cloud key. When set, it's the default for every
# workspace that hasn't configured its own ProviderCredential — so a
# self-hosted operator can supply one key for the whole deployment instead of
# each workspace adding one. A workspace-specific credential still wins.
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

# Dedicated Docker-in-Docker sandbox. The host socket is never mounted; this
# URL resolves only on Compose's private sandbox-control network.
SANDBOX_DOCKER_URL = os.environ.get("SANDBOX_DOCKER_URL", "")
SANDBOX_IMAGE = os.environ.get("SANDBOX_IMAGE", "python:3.14-alpine")
SANDBOX_TIMEOUT_SECONDS = float(os.environ.get("SANDBOX_TIMEOUT_SECONDS", "10"))
SANDBOX_IMAGE_PULL_TIMEOUT_SECONDS = float(
    os.environ.get("SANDBOX_IMAGE_PULL_TIMEOUT_SECONDS", "180")
)
SANDBOX_MAX_CODE_BYTES = int(os.environ.get("SANDBOX_MAX_CODE_BYTES", str(64 * 1024)))
SANDBOX_MAX_OUTPUT_BYTES = int(
    os.environ.get("SANDBOX_MAX_OUTPUT_BYTES", str(64 * 1024))
)
SANDBOX_MEMORY_BYTES = int(
    os.environ.get("SANDBOX_MEMORY_BYTES", str(128 * 1024 * 1024))
)
SANDBOX_NANO_CPUS = int(os.environ.get("SANDBOX_NANO_CPUS", "500000000"))
SANDBOX_PIDS_LIMIT = int(os.environ.get("SANDBOX_PIDS_LIMIT", "64"))

# Celery — broker/result backend both point at Redis per ARCHITECTURE.md §4.2.
CELERY_BROKER_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    "evaluate-scheduled-workflows": {
        "task": "worker.evaluate_scheduled_workflows",
        "schedule": 60.0,
    },
    "detect-audit-anomalies": {
        "task": "worker.detect_audit_anomalies",
        "schedule": 300.0,
    },
    "evaluate-due-website-monitors": {
        "task": "worker.evaluate_due_website_monitors",
        "schedule": 60.0,
    },
}

PAYMENTS_CHECKOUT_BASE_URL = os.environ.get("PAYMENTS_CHECKOUT_BASE_URL", "")
PAYMENTS_WEBHOOK_SECRET = os.environ.get("PAYMENTS_WEBHOOK_SECRET", "")

# Shared cache keeps API throttle counters consistent between ASGI workers and
# replicas instead of silently reverting to process-local counters.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": os.environ.get("REDIS_CACHE_URL", "redis://localhost:6379/1"),
    }
}

# Milestone 5 knowledge source storage. The bucket is created lazily by the
# ingestion service, which keeps first-run setup to environment variables.
MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "http://localhost:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "agentarium")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "agentarium123")
MINIO_BUCKET = os.environ.get("MINIO_BUCKET", "agentarium-knowledge")
MINIO_SECURE = os.environ.get("MINIO_SECURE", "false").lower() == "true"
KNOWLEDGE_FILES_ROOT = Path(
    os.environ.get("KNOWLEDGE_FILES_ROOT", str(BASE_DIR / "var" / "knowledge"))
)

# Notifications default to console delivery for self-hosted development;
# production operators can switch to SMTP entirely through environment variables.
EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = os.environ.get("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "25"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "false").lower() == "true"
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "Deep-Foundry <noreply@localhost>")
WEB_APP_URL = os.environ.get("WEB_APP_URL", "http://localhost:3000")
INTERNAL_API_TOKEN = os.environ.get(
    "INTERNAL_API_TOKEN", "insecure-dev-internal-token-change-in-production"
)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_BOT_USERNAME = os.environ.get("TELEGRAM_BOT_USERNAME", "").strip().lstrip("@")
TELEGRAM_WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "").strip()
TELEGRAM_LINK_TTL_SECONDS = int(os.environ.get("TELEGRAM_LINK_TTL_SECONDS", "600"))
TELEGRAM_API_TIMEOUT_SECONDS = int(os.environ.get("TELEGRAM_API_TIMEOUT_SECONDS", "10"))
TELEGRAM_WEBHOOK_MAX_BYTES = int(os.environ.get("TELEGRAM_WEBHOOK_MAX_BYTES", "65536"))
_telegram_values = (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_BOT_USERNAME,
    TELEGRAM_WEBHOOK_SECRET,
)
if any(_telegram_values) and not all(_telegram_values):
    raise ImproperlyConfigured(
        "TELEGRAM_BOT_TOKEN, TELEGRAM_BOT_USERNAME, and TELEGRAM_WEBHOOK_SECRET "
        "must be configured together."
    )
TELEGRAM_ENABLED = all(_telegram_values)
if TELEGRAM_ENABLED:
    if not re.fullmatch(r"[A-Za-z0-9_]{5,32}", TELEGRAM_BOT_USERNAME):
        raise ImproperlyConfigured("TELEGRAM_BOT_USERNAME is invalid.")
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", TELEGRAM_WEBHOOK_SECRET):
        raise ImproperlyConfigured(
            "TELEGRAM_WEBHOOK_SECRET must be 32-256 URL-safe characters."
        )
if not 60 <= TELEGRAM_LINK_TTL_SECONDS <= 3600:
    raise ImproperlyConfigured("TELEGRAM_LINK_TTL_SECONDS must be between 60 and 3600.")
if not 1 <= TELEGRAM_API_TIMEOUT_SECONDS <= 30:
    raise ImproperlyConfigured("TELEGRAM_API_TIMEOUT_SECONDS must be between 1 and 30.")
if not 1024 <= TELEGRAM_WEBHOOK_MAX_BYTES <= 1048576:
    raise ImproperlyConfigured(
        "TELEGRAM_WEBHOOK_MAX_BYTES must be between 1024 and 1048576."
    )

if ENVIRONMENT == "production":
    insecure_values = {"", "change-me", "insecure-dev-key-do-not-use-in-production"}
    if DEBUG:
        raise ImproperlyConfigured("DJANGO_DEBUG must be false when APP_ENV=production.")
    if (
        SECRET_KEY in insecure_values
        or SECRET_KEY.startswith(("dev-only-", "change-me", "insecure-"))
        or len(SECRET_KEY) < 50
    ):
        raise ImproperlyConfigured("DJANGO_SECRET_KEY must be a generated secret of 50+ characters.")
    if INTERNAL_API_TOKEN in insecure_values or INTERNAL_API_TOKEN.startswith(("insecure-", "change-me")):
        raise ImproperlyConfigured("INTERNAL_API_TOKEN must be generated for production.")
    if DATABASES["default"]["PASSWORD"] in insecure_values or DATABASES["default"]["PASSWORD"].startswith("change-me"):
        raise ImproperlyConfigured("DB_PASSWORD must be changed for production.")
    if MINIO_SECRET_KEY in insecure_values or MINIO_SECRET_KEY.startswith("change-me") or MINIO_SECRET_KEY == "agentarium123":
        raise ImproperlyConfigured("MINIO_ROOT_PASSWORD must be changed for production.")
    if "*" in ALLOWED_HOSTS or not [host for host in ALLOWED_HOSTS if host != "app"]:
        raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must list explicit production hosts.")
    try:
        Fernet(FIELD_ENCRYPTION_KEY.encode("ascii"))
    except (ValueError, TypeError) as exc:
        raise ImproperlyConfigured("FIELD_ENCRYPTION_KEY must be a valid Fernet key.") from exc
    if FIELD_ENCRYPTION_KEY == "cejGCUCoSNmRYVMLQQQX9KGwbOqCiauvwWsHIWy-RPY=":
        raise ImproperlyConfigured("FIELD_ENCRYPTION_KEY must not use the public development key.")
    if not SANDBOX_DOCKER_URL:
        raise ImproperlyConfigured(
            "SANDBOX_DOCKER_URL is required in production so execute_code fails closed."
        )
    if TELEGRAM_ENABLED:
        if not WEB_APP_URL.startswith("https://"):
            raise ImproperlyConfigured(
                "WEB_APP_URL must use HTTPS when Telegram notifications are enabled."
            )

    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = True
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
