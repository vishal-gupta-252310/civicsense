"""Pytest conftest: starts Django + FastAPI on scratch SQLite, seeds users."""

import os
import subprocess
import sys
import time

import pytest
import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DJANGO_PORT = 9100
FASTAPI_PORT = 8100
DB_FILE = os.path.join(BASE_DIR, "db_e2e_test.sqlite3")
MEDIA_DIR = os.path.join(BASE_DIR, "media_e2e_test")

ENV = {
    **os.environ,
    "DJANGO_SETTINGS_MODULE": "civicsense.e2e_settings",
    "AI_SERVICE_URL": f"http://127.0.0.1:{FASTAPI_PORT}",
    # Scratch DB/media, separate from the local dev server's data — running
    # the E2E suite must never wipe your dev account/password.
    "CIVICSENSE_E2E_DB": "db_e2e_test.sqlite3",
    "CIVICSENSE_E2E_MEDIA": "media_e2e_test",
}


def _wait(url, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            requests.get(url, timeout=2)
            return True
        except requests.ConnectionError:
            time.sleep(0.5)
    return False


def _rm(path):
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture(scope="session", autouse=True)
def servers():
    # Fresh scratch DB + media dir each run.
    for ext in ("", "-shm", "-wal"):
        _rm(DB_FILE + ext)
    subprocess.run(["rm", "-rf", MEDIA_DIR], check=False)

    subprocess.run(
        [sys.executable, "manage.py", "migrate"],
        cwd=BASE_DIR,
        env=ENV,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    django_proc = subprocess.Popen(
        [sys.executable, "manage.py", "runserver",
         f"127.0.0.1:{DJANGO_PORT}", "--noreload"],
        cwd=BASE_DIR, env=ENV,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    fastapi_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "ai_service.main:app",
         "--host", "127.0.0.1", "--port", str(FASTAPI_PORT)],
        cwd=BASE_DIR, env=ENV,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    django_ok = _wait(f"http://127.0.0.1:{DJANGO_PORT}/login/")
    fastapi_ok = _wait(f"http://127.0.0.1:{FASTAPI_PORT}/docs")
    assert django_ok, "Django server failed to start"
    assert fastapi_ok, "FastAPI server failed to start"

    subprocess.run(
        [sys.executable, "manage.py", "shell", "-c", """
from django.contrib.auth.models import User
from issues.models import UserProfile

if not User.objects.filter(username='citizen1').exists():
    u = User.objects.create_user('citizen1', 'citizen1@test.com', 'TestPass123!')
    UserProfile.objects.create(user=u, role='citizen')

if not User.objects.filter(username='admin1').exists():
    u = User.objects.create_user('admin1', 'admin1@test.com', 'TestPass123!')
    u.is_staff = True
    u.save()
    UserProfile.objects.create(user=u, role='admin')
"""],
        cwd=BASE_DIR, env=ENV, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    yield {
        "base_url": f"http://127.0.0.1:{DJANGO_PORT}",
        "api_url": f"http://127.0.0.1:{FASTAPI_PORT}",
    }

    django_proc.terminate()
    fastapi_proc.terminate()
    django_proc.wait()
    fastapi_proc.wait()


@pytest.fixture(scope="session")
def base_url(servers):
    return servers["base_url"]


@pytest.fixture(scope="session")
def api_url(servers):
    return servers["api_url"]


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {
        **browser_context_args,
        "geolocation": {"latitude": 28.6139, "longitude": 77.2090},
        "permissions": ["geolocation"],
    }