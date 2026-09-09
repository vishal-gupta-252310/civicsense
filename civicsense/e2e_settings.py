"""Test-only settings: replaces MySQL with a scratch SQLite database.

Used by the Playwright E2E harness (tests_e2e/). The production app keeps
using MySQL from settings.py — nothing here touches real configuration.
"""

from pathlib import Path
import os

from .settings import *  # noqa: F401,F403

BASE_DIR = Path(__file__).resolve().parent.parent

# The E2E harness overrides these via env so it never touches the dev server's
# database/media (CIVICSENSE_E2E_DB defaults to the local dev db_e2e.sqlite3).
E2E_DB = os.environ.get("CIVICSENSE_E2E_DB", "db_e2e.sqlite3")
E2E_MEDIA = os.environ.get("CIVICSENSE_E2E_MEDIA", "media_e2e")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / E2E_DB,
    }
}

MEDIA_ROOT = BASE_DIR / E2E_MEDIA