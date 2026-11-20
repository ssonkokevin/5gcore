"""
Django settings for OAM project.
Multi-database support: srg_db (STP/DRA) and hssdb (UDM/HSS)
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "django-insecure-dev-key-change-in-production")

DEBUG = os.getenv("DJANGO_DEBUG", "True").lower() == "true"

ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "oam.core",
]

MIDDLEWARE = [
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "oam.urls"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.getenv("DB_NAME", "srg_db"),
        "USER": os.getenv("DB_USER", "net5gc"),
        "PASSWORD": os.getenv("DB_PASSWORD", "net5gc"),
        "HOST": os.getenv("DB_HOST", "db"),
        "PORT": os.getenv("DB_PORT", "3306"),
        "OPTIONS": {"charset": "utf8mb4"},
    },
    "hssdb": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.getenv("HSS_DB_NAME", "hssdb"),
        "USER": os.getenv("HSS_DB_USER", "hss"),
        "PASSWORD": os.getenv("HSS_DB_PASSWORD", "hss123"),
        "HOST": os.getenv("HSS_DB_HOST", "hssdb"),
        "PORT": os.getenv("HSS_DB_PORT", "3306"),
        "OPTIONS": {"charset": "utf8mb4"},
    },
}

DATABASE_ROUTERS = ["oam.core.routers.DatabaseRouter"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "format": '{"time": "%(asctime)s", "level": "%(levelname)s", "name": "%(name)s", "message": "%(message)s"}',
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": os.getenv("LOG_LEVEL", "INFO"),
    },
}