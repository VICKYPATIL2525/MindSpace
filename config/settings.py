"""
Production-ready Django settings for MindSpace.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured
from django.contrib.messages import constants as messages


# ============================================================
# BASE
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return str(value).strip().lower() in ["1", "true", "yes", "on"]


def env_list(name, default=""):
    value = os.environ.get(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


def env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def required_env(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise ImproperlyConfigured(f"{name} is required.")
    return value


# ============================================================
# SECURITY
# ============================================================

DEBUG = env_bool("DEBUG", False)

SECRET_KEY = os.environ.get("SECRET_KEY", "").strip()

if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "dev-only-change-this-secret-key"
    else:
        raise ImproperlyConfigured("SECRET_KEY must be set when DEBUG=False.")

ALLOWED_HOSTS = env_list(
    "ALLOWED_HOSTS",
    "127.0.0.1,localhost"
)

CSRF_TRUSTED_ORIGINS = env_list(
    "CSRF_TRUSTED_ORIGINS",
    "http://127.0.0.1:8000,http://localhost:8000"
)

SITE_BASE_URL = os.environ.get(
    "SITE_BASE_URL",
    "http://127.0.0.1:8000" if DEBUG else ""
).rstrip("/")

if not SITE_BASE_URL and not DEBUG:
    raise ImproperlyConfigured("SITE_BASE_URL must be set in production.")


# ============================================================
# APPLICATIONS
# ============================================================

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "django.contrib.sites",
    "django.contrib.postgres",

    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",

    "django_q",
    "mindspace",
]

# If you use SITE_ID=2, you must create site id 2 after fresh DB.
# Simpler production-safe default is 1.
SITE_ID = env_int("SITE_ID", 1)

# ============================================================
# Django Q
# ============================================================

Q_CLUSTER = {
    "name": "mindspace",
    "workers": 4,
    "timeout": 1800,
    "retry": 2100,
    "queue_limit": 100,
    "bulk": 10,
    "redis": {
        "host": os.environ.get("REDIS_HOST", "127.0.0.1"),
        "port": int(os.environ.get("REDIS_PORT", "6379")),
        "db": int(os.environ.get("REDIS_DB", "0")),
    },
}

# ============================================================
# MIDDLEWARE
# ============================================================

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",

    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",

    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",

    "django.contrib.messages.middleware.MessageMiddleware",

    # Force consent + profile completion before protected app access.
    # Your middleware must exclude login, signup, verify-email, admin, static, media, and OAuth callback URLs.
    "mindspace.middleware.OnboardingRequiredMiddleware",

    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


# ============================================================
# URL / WSGI
# ============================================================

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"


# ============================================================
# TEMPLATES
# ============================================================

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            BASE_DIR / "templates",
        ],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]


# ============================================================
# DATABASE
# ============================================================

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "mds"),
        "USER": os.environ.get("DB_USER", "mds_user"),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
        "CONN_MAX_AGE": env_int("DB_CONN_MAX_AGE", 60),
    }
}


# ============================================================
# PASSWORD VALIDATION
# ============================================================

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {
            "min_length": 8,
        },
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# ============================================================
# AUTH / ALLAUTH
# ============================================================

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "google_login_redirect"
LOGOUT_REDIRECT_URL = "login"

ACCOUNT_LOGIN_REDIRECT_URL = "google_login_redirect"
ACCOUNT_SIGNUP_REDIRECT_URL = "google_login_redirect"

# You are using your own PendingSignup email verification flow.
ACCOUNT_EMAIL_VERIFICATION = "none"

ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]

SOCIALACCOUNT_LOGIN_ON_GET = True
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_EMAIL_VERIFICATION = "none"
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True

SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "SCOPE": [
            "profile",
            "email",
        ],
        "AUTH_PARAMS": {
            "access_type": "online",
        },
        "OAUTH_PKCE_ENABLED": True,
    }
}


# ============================================================
# LANGUAGE / TIMEZONE
# ============================================================

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True


# ============================================================
# STATIC / MEDIA
# ============================================================

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STATICFILES_DIRS = []
if (BASE_DIR / "static").exists():
    STATICFILES_DIRS.append(BASE_DIR / "static")

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"


# ============================================================
# EMAIL SETTINGS
# ============================================================

EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND",
    "django.core.mail.backends.smtp.EmailBackend"
)

EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = env_int("EMAIL_PORT", 587)
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", False)
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")

DEFAULT_FROM_EMAIL = os.environ.get(
    "DEFAULT_FROM_EMAIL",
    EMAIL_HOST_USER or "noreply@mindspace.local"
)


# ============================================================
# SESSION / CSRF / PRODUCTION SECURITY
# ============================================================

SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False

SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG

SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", not DEBUG)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 0 if DEBUG else 31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", not DEBUG)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", not DEBUG)

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

REFERRER_POLICY = "strict-origin-when-cross-origin"


# ============================================================
# MESSAGES
# ============================================================

MESSAGE_TAGS = {
    messages.DEBUG: "debug",
    messages.INFO: "info",
    messages.SUCCESS: "success",
    messages.WARNING: "warning",
    messages.ERROR: "error",
}


# ============================================================
# DEFAULT PRIMARY KEY
# ============================================================

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ============================================================
# GCP STORAGE
# ============================================================

USE_GCP_STORAGE = env_bool("USE_GCP_STORAGE", False)
GS_BUCKET_NAME = os.environ.get("GS_BUCKET_NAME", "")
GCP_BUCKET_NAME = os.environ.get("GCP_BUCKET_NAME", "")
GOOGLE_APPLICATION_CREDENTIALS = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")


# ============================================================
# MINDSPACE EXTERNAL API CONFIG
# Names match assessments/views.py
# ============================================================

# Face pipeline
FACE_EXTRACT_URL = os.environ.get(
    "FACE_EXTRACT_URL",
    "http://88.222.12.15:5100/extract/video"
)

FACE_EXTRACT_SESSION_VECTOR_URL_TEMPLATE = os.environ.get(
    "FACE_EXTRACT_SESSION_VECTOR_URL_TEMPLATE",
    ""
)

FACE_VECTOR_URL_TEMPLATE = os.environ.get(
    "FACE_VECTOR_URL_TEMPLATE",
    ""
)

FACE_SCORE_URL = os.environ.get(
    "FACE_SCORE_URL",
    "http://127.0.0.1:8011/predict"
)

FACE_VIDEO_FEATURE_EXTRACTION_API_KEY = os.environ.get(
    "FACE_VIDEO_FEATURE_EXTRACTION_API_KEY",
    ""
)

FACE_VIDEO_FEATURE_TO_MH_API_KEY = os.environ.get(
    "FACE_VIDEO_FEATURE_TO_MH_API_KEY",
    ""
)

EXTRACTION_API_KEY = os.environ.get("EXTRACTION_API_KEY", "")
SCORING_API_KEY = os.environ.get("SCORING_API_KEY", "")


# Voice phonation pipeline
VOICE_EXTRACT_URL = os.environ.get(
    "VOICE_EXTRACT_URL",
    "http://88.222.12.15:5800/extract"
)

VOICE_PCA_URL = os.environ.get(
    "VOICE_PCA_URL",
    "http://88.222.12.15:5900/process"
)

VOICE_SCORE_URL = os.environ.get(
    "VOICE_SCORE_URL",
    "http://88.222.212.15:5600/predict"
)

VOICE_FEATURE_EXTRACT_API_KEY = os.environ.get(
    "VOICE_FEATURE_EXTRACT_API_KEY",
    ""
)

VOICE_PCA_API_KEY = os.environ.get(
    "VOICE_PCA_API_KEY",
    ""
)

VOICE_SCORE_API_KEY = os.environ.get(
    "VOICE_SCORE_API_KEY",
    ""
)

VOICE_FEATURE_TO_MH = os.environ.get(
    "VOICE_FEATURE_TO_MH",
    ""
)

VOICE_PHONATION_USE_STT = os.environ.get(
    "VOICE_PHONATION_USE_STT",
    "False"
)


# Scenario STT
SARVAM_API_KEY = os.environ.get("SARVAM_API_KEY", "")
SARVAM_STT_MODEL = os.environ.get("SARVAM_STT_MODEL", "saaras:v3")


# Text pipeline
TEXT_EXTRACT_URL = os.environ.get(
    "TEXT_EXTRACT_URL",
    "http://88.222.12.15:8025/analyze"
)

TEXT_SCORE_URL = os.environ.get(
    "TEXT_SCORE_URL",
    "http://88.222.12.15:9000/predict"
)

TEXT_PARAMETER_EXTRACT_API_KEY = os.environ.get(
    "TEXT_PARAMETER_EXTRACT_API_KEY",
    ""
)

TEXT_ANALYSIS_API_KEY = os.environ.get(
    "TEXT_ANALYSIS_API_KEY",
    ""
)


# Fusion pipeline
# Do not default this to 127.0.0.1:8000 if Django also runs on 8000.
FUSION_SCORE_URL = os.environ.get(
    "FUSION_SCORE_URL",
    "http://88.222.12.15:8000/predict"
)

MODEL_API_KEY = os.environ.get("MODEL_API_KEY", "")

# Generic fallback key
API_KEY = os.environ.get("API_KEY", "")

# ============================================================
# CHATBOT CONFIG
# ============================================================

CHATBOT_API_URL = os.environ.get(
    "CHATBOT_API_URL",
    "http://127.0.0.1:7000/chat"
)

CHATBOT_API_KEY = os.environ.get(
    "CHATBOT_API_KEY",
    ""
)


# ============================================================
# UPLOAD LIMITS
# ============================================================

DATA_UPLOAD_MAX_MEMORY_SIZE = env_int("DATA_UPLOAD_MAX_MEMORY_SIZE", 10485760)
FILE_UPLOAD_MAX_MEMORY_SIZE = env_int("FILE_UPLOAD_MAX_MEMORY_SIZE", 10485760)