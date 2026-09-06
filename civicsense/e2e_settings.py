"""Test-only settings: replaces MySQL with a scratch SQLite database.

Used by the Playwright E2E harness (tests_e2e/). The production app keeps
using MySQL from settings.py — nothing here touches real configuration.
"""

from pathlib import Path

from .settings import *  # noqa: F401,F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": Path(__file__).resolve().parent.parent / "db_e2e.sqlite3",
    }
}

MEDIA_ROOT = Path(__file__).resolve().parent.parent / "media_e2e"