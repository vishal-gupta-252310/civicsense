"""
CivicSense — Django settings.

Configuration is read from environment variables / a local .env file so the
same code runs in development and production without changes (see Listing 3.4).
"""

import os
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env if present (never commit it).
env = environ.Env()
env_file = BASE_DIR / ".env"
if env_file.exists():
    environ.Env.read_env(str(env_file))

SECRET_KEY = env("DJANGO_SECRET_KEY", default="django-insecure-dev-only")

DEBUG = env.bool("DJANGO_DEBUG", default=True)

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "issues",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "civicsense.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
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

WSGI_APPLICATION = "civicsense.wsgi.application"

# Database chosen by configuration: "mysql" (default, local/report) or "postgres" (deploy).
DB_ENGINE = env("DB_ENGINE", default="mysql")

DATABASES = {
    "default": {
        "ENGINE": (
            "django.db.backends.postgresql"
            if DB_ENGINE == "postgres"
            else "django.db.backends.mysql"
        ),
        "NAME": env("DB_NAME", default="civicsense"),
        "USER": env("DB_USER", default="civicsense"),
        "PASSWORD": env("DB_PASSWORD", default=""),
        "HOST": env("DB_HOST", default="127.0.0.1"),
        "PORT": env("DB_PORT", default="3306"),
    }
}
if DB_ENGINE == "postgres":
    DATABASES["default"]["OPTIONS"] = {"sslmode": env("DB_SSLMODE", default="require")}
else:
    DATABASES["default"]["OPTIONS"] = {"charset": "utf8mb4"}

# AI micro-service and provider are chosen purely by configuration (Listing 3.4).
AI_SERVICE_URL = env("AI_SERVICE_URL", default="http://localhost:8001")

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Store uploaded photos on Cloudinary when credentials are configured; otherwise
# keep the local filesystem (development). Selected purely by configuration.
if env("CLOUDINARY_CLOUD_NAME", default="") and env("CLOUDINARY_API_KEY", default=""):
    STORAGES = {
        "default": {"BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage"},
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    }
    CLOUDINARY_STORAGE = {
        "CLOUD_NAME": env("CLOUDINARY_CLOUD_NAME"),
        "API_KEY": env("CLOUDINARY_API_KEY"),
        "API_SECRET": env("CLOUDINARY_API_SECRET", default=""),
    }

# Login/logout redirects
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

# Email (used by password reset). Console backend prints reset links to the
# server log in development; point it at a real SMTP via .env for production.
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="CivicSense <noreply@civicsense.local>")
EMAIL_HOST = env("EMAIL_HOST", default="localhost")
EMAIL_PORT = env.int("EMAIL_PORT", default=25)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=False)

# Public site URL. Used as the domain in password-reset emails so they never
# reference the request Host (e.g. "localhost"). Change to the real deploy URL.
SITE_URL = env("SITE_URL", default="https://civicsense-django.onrender.com")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {
            "format": "%(asctime)s %(levelname)s %(name)s: %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": os.environ.get("LOG_LEVEL", "INFO"),
    },
    "loggers": {
        "civicsense": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}
