"""Playwright E2E tests for CivicSense — covers every user-facing feature."""

import os
import time

import pytest
from playwright.sync_api import sync_playwright, expect

BASE = os.environ.get("CIVICSENSE_BASE_URL", "http://127.0.0.1:9100")
RUN_TAG = str(int(time.time()))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def register(page, username=None, email=None, password="StrongPass123!"):
    """Register a fresh unique user; returns (username, email, password)."""
    username = username or f"pwuser{RUN_TAG}"
    email = email or f"{username}@test.com"
    page.goto(f"{BASE}/register/")
    page.fill('input[name="username"]', username)
    page.fill('input[name="email"]', email)
    page.check('input[name="role"][value="citizen"]')
    page.fill('input[name="password1"]', password)
    page.fill('input[name="password2"]', password)
    page.click('button[type="submit"]')
    page.wait_for_url(f"{BASE}/")
    return username, email, password


def login(page, email="citizen1@test.com", password="TestPass123!"):
    page.goto(f"{BASE}/login/")
    page.fill('input[name="email"]', email)
    page.fill('input[name="password"]', password)
    page.click('button[type="submit"]')
    page.wait_for_url(f"{BASE}/")


def logout(page):
    page.goto(f"{BASE}/logout/")
    page.wait_for_load_state("load")


def login_admin(page):
    logout(page)
    login(page, email="admin1@test.com", password="TestPass123!")


def report_issue(page, description="Big pothole near the school gate on main road",
                 with_photo=False):
    page.goto(f"{BASE}/report/")
    page.wait_for_selector("#manual-area", state="visible", timeout=15000)
    page.select_option("#manual-area", "28.6139,77.2090")
    page.fill('textarea[name="description"]', description)
    if with_photo:
        page.locator('input[type="file"]').set_input_files(_create_test_image())
    page.click('button[type="submit"]')
    page.wait_for_url(lambda url: "/issue/" in url)
    return page.url


# ---------------------------------------------------------------------------
# TC01-TC03: Authentication
# ---------------------------------------------------------------------------

class TestRegistration:
    def test_tc01_register_creates_account(self, page):
        _, email, password = register(page)
        assert page.url == f"{BASE}/"
        logout(page)
        login(page, email=email, password=password)
        assert page.url == f"{BASE}/"

    def test_register_duplicate_username_shows_error(self, page):
        page.goto(f"{BASE}/register/")
        page.fill('input[name="username"]', "citizen1")
        page.fill('input[name="email"]', "dup@test.com")
        page.check('input[name="role"][value="citizen"]')
        page.fill('input[name="password1"]', "StrongPass123!")
        page.fill('input[name="password2"]', "StrongPass123!")
        page.click('button[type="submit"]')
        page.wait_for_load_state("load")
        assert "/register/" in page.url
        expect(page.locator(".errorlist, .invalid-feedback, .alert-danger")).not_to_have_count(0)


class TestLogin:
    def test_tc02_login_valid(self, page):
        login(page)
        assert page.url == f"{BASE}/"

    def test_tc03_login_wrong_password(self, page):
        page.goto(f"{BASE}/login/")
        page.fill('input[name="email"]', "citizen1@test.com")
        page.fill('input[name="password"]', "wrongpassword")
        page.click('button[type="submit"]')
        page.wait_for_load_state("load")
        assert "/login/" in page.url
        expect(page.locator(".errorlist, .invalid-feedback, .alert-danger")).not_to_have_count(0)

    def test_login_nonexistent_email(self, page):
        page.goto(f"{BASE}/login/")
        page.fill('input[name="email"]', "nobody@test.com")
        page.fill('input[name="password"]', "whatever")
        page.click('button[type="submit"]')
        page.wait_for_load_state("load")
        assert "/login/" in page.url


# ---------------------------------------------------------------------------
# TC04-TC05: Issue Reporting
# ---------------------------------------------------------------------------

class TestReportIssue:
    def test_tc04_report_with_photo_and_location(self, page):
        login(page)
        issue_url = report_issue(
            page, "A big pothole near the school gate on main road",
            with_photo=True,
        )
        expect(page.locator("body")).to_contain_text("Pothole")

    def test_tc05_report_without_location_submit_disabled(self, page):
        login(page)
        page.goto(f"{BASE}/report/")
        page.wait_for_selector("#manual-area", state="visible", timeout=15000)
        page.fill('textarea[name="description"]', "No location report")
        submit_btn = page.locator('button[type="submit"]')
        expect(submit_btn).to_be_disabled()

    def test_tc05_server_rejects_no_location(self, page):
        login(page)
        page.goto(f"{BASE}/report/")
        page.wait_for_selector("#manual-area", state="visible", timeout=15000)
        page.fill('textarea[name="description"]', "No location report")
        page.evaluate("document.getElementById('report-form').submit()")
        page.wait_for_load_state("load")
        assert "/report/" in page.url


# ---------------------------------------------------------------------------
# TC06-TC07: AI Classification
# ---------------------------------------------------------------------------

class TestAIClassification:
    def test_tc06_classifies_pothole(self, page):
        login(page)
        report_issue(page, "A big pothole on the main road")
        expect(page.locator("body")).to_contain_text("Pothole")

    def test_tc07_priority_high_for_severe(self, page):
        login(page)
        report_issue(page, "Accident risk, dangerous pothole in front of school")
        expect(page.locator("body")).to_contain_text("High")

    def test_classifies_garbage(self, page):
        login(page)
        report_issue(page, "Garbage pile not collected for weeks")
        expect(page.locator("body")).to_contain_text("Garbage")


# ---------------------------------------------------------------------------
# TC08: Duplicate Detection
# ---------------------------------------------------------------------------

class TestDuplicateDetection:
    def test_tc08_duplicate_detected_nearby(self, page):
        login(page)
        report_issue(page, "A big pothole near the school gate on main road")
        page.goto(f"{BASE}/report/")
        page.wait_for_selector("#manual-area", state="visible", timeout=15000)
        page.select_option("#manual-area", "28.6139,77.2090")
        page.fill('textarea[name="description"]', "another pothole near the school road")
        page.click('button[type="submit"]')
        page.wait_for_url(lambda url: "/issue/" in url)
        expect(page.locator(".alert-warning, .alert")).to_contain_text("duplicate")


# ---------------------------------------------------------------------------
# TC09: Fallback when AI unreachable
# ---------------------------------------------------------------------------

class TestAIFallback:
    def test_tc09_fallback_classifies_correctly(self, page):
        login(page)
        report_issue(page, "broken streetlight not working for weeks")
        expect(page.locator("body")).to_contain_text("Streetlight")


# ---------------------------------------------------------------------------
# TC10-TC11: Status Workflow
# ---------------------------------------------------------------------------

class TestStatusWorkflow:
    def test_tc10_admin_updates_status(self, page):
        login(page)
        issue_url = report_issue(page, "Water leak from pipe on the street")
        login_admin(page)
        page.goto(issue_url)
        page.select_option('select[name="new_status"]', "progress")
        page.fill('textarea[name="note"]', "Team dispatched")
        page.click('button:has-text("Update status")')
        page.wait_for_load_state("load")
        expect(page.locator("body")).to_contain_text("In Progress")
        expect(page.locator("body")).to_contain_text("Team dispatched")

    def test_tc11_citizen_sees_status(self, page):
        login(page)
        report_issue(page, "Garbage dumped near park")
        expect(page.locator("body")).to_contain_text("Open")


# ---------------------------------------------------------------------------
# TC12: Map
# ---------------------------------------------------------------------------

class TestMap:
    def test_tc12_map_renders_issues(self, page):
        login(page)
        report_issue(page, "Pothole near the park on main road")
        page.goto(f"{BASE}/map/")
        expect(page.locator("#map, .leaflet-container, #issues-map")).to_be_visible()


# ---------------------------------------------------------------------------
# TC13: Upvotes
# ---------------------------------------------------------------------------

class TestUpvotes:
    def test_tc13_upvote_counts(self, page):
        login(page)
        report_issue(page, "Streetlight broken at the intersection")
        count_badge = page.locator("#upvote-count")
        initial = count_badge.text_content().strip()
        page.click("#upvote-btn")
        time.sleep(0.5)
        new_count = count_badge.text_content().strip()
        assert int(new_count) == int(initial) + 1

    def test_upvote_toggle_removes(self, page):
        login(page)
        report_issue(page, "Garbage bin overflowing near school")
        page.click("#upvote-btn")
        time.sleep(0.5)
        page.click("#upvote-btn")
        time.sleep(0.5)
        expect(page.locator("#upvote-btn")).to_contain_text("Upvote this issue")


# ---------------------------------------------------------------------------
# TC14-TC15: Analytics (admin only)
# ---------------------------------------------------------------------------

class TestAnalytics:
    def test_tc14_analytics_for_admin(self, page):
        login_admin(page)
        page.goto(f"{BASE}/analytics/")
        expect(page.locator("body")).to_contain_text("Analytics Dashboard")

    def test_tc15_citizen_blocked_from_analytics(self, page):
        login(page)
        page.goto(f"{BASE}/analytics/")
        assert page.url == f"{BASE}/"


# ---------------------------------------------------------------------------
# Form Validations (Client-Side)
# ---------------------------------------------------------------------------

class TestFormValidations:
    def test_register_required_fields_present(self, page):
        page.goto(f"{BASE}/register/")
        for name in ("username", "email", "password1", "password2"):
            el = page.locator(f'input[name="{name}"]')
            expect(el).to_have_attribute("required", "")

    def test_register_password_minlength(self, page):
        page.goto(f"{BASE}/register/")
        pw = page.locator('input[name="password1"]')
        expect(pw).to_have_attribute("minlength", "8")

    def test_register_username_maxlength(self, page):
        page.goto(f"{BASE}/register/")
        uname = page.locator('input[name="username"]')
        expect(uname).to_have_attribute("maxlength", "150")

    def test_login_required_fields_present(self, page):
        page.goto(f"{BASE}/login/")
        email = page.locator('input[name="email"]')
        pw = page.locator('input[name="password"]')
        expect(email).to_have_attribute("required", "")
        expect(pw).to_have_attribute("required", "")

    def test_report_description_has_constraints(self, page):
        login(page)
        page.goto(f"{BASE}/report/")
        page.wait_for_selector("#manual-area", state="visible", timeout=15000)
        desc = page.locator('textarea[name="description"]')
        expect(desc).to_have_attribute("required", "")
        expect(desc).to_have_attribute("minlength", "10")
        expect(desc).to_have_attribute("maxlength", "2000")

    def test_report_address_has_maxlength(self, page):
        login(page)
        page.goto(f"{BASE}/report/")
        page.wait_for_selector("#manual-area", state="visible", timeout=15000)
        addr = page.locator('input[name="address"]')
        expect(addr).to_have_attribute("maxlength", "255")

    def test_report_short_description_rejected(self, page):
        login(page)
        page.goto(f"{BASE}/report/")
        page.wait_for_selector("#manual-area", state="visible", timeout=15000)
        page.select_option("#manual-area", "28.6139,77.2090")
        page.fill('textarea[name="description"]', "short")
        page.click('button[type="submit"]')
        page.wait_for_load_state("load")
        assert "/report/" in page.url

    def test_status_note_has_maxlength(self, page):
        login(page)
        issue_url = report_issue(page, "Test issue for note maxlength check")
        login_admin(page)
        page.goto(issue_url)
        note = page.locator('textarea[name="note"]')
        expect(note).to_have_attribute("maxlength", "1000")


# ---------------------------------------------------------------------------
# Access Control
# ---------------------------------------------------------------------------

class TestAccessControl:
    def test_unauthenticated_redirected_to_login(self, page):
        page.goto(f"{BASE}/report/")
        assert "/login/" in page.url

    def test_unauthenticated_cannot_see_issue_detail(self, page):
        login(page)
        issue_url = report_issue(page, "Test issue for access control check")
        logout(page)
        page.goto(issue_url)
        assert "/login/" in page.url

    def test_citizen_cannot_update_status(self, page):
        login(page)
        report_issue(page, "Test issue for status access control")
        expect(page.locator('select[name="new_status"]')).not_to_be_visible()


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _create_test_image():
    path = "/tmp/civicsense_test_photo.jpg"
    if not os.path.exists(path):
        from PIL import Image
        img = Image.new("RGB", (100, 100), "red")
        img.save(path, "JPEG")
    return path