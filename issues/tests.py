"""System tests mirroring the report's test cases (TC01-TC15).

Real interactions only: Django test client, live MySQL schema via the test DB,
and real classification through the local fallback classifier (no mocks).
"""

from io import BytesIO
import re

from django.contrib.auth.models import User
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image

from .models import Category, Issue, StatusUpdate, Upvote, UserProfile
from .services import classify_issue, find_duplicate

DEFAULT_AI_URL = "http://localhost:9"  # unreachable -> forces Django fallback


def make_photo():
    buf = BytesIO()
    Image.new("RGB", (16, 16), "brown").save(buf, format="JPEG")
    return SimpleUploadedFile(
        "photo.jpg", buf.getvalue(), content_type="image/jpeg"
    )


@override_settings(AI_SERVICE_URL=DEFAULT_AI_URL, ALLOWED_HOSTS=["testserver"])
class CivicSenseTests(TestCase):
    def setUp(self):
        self.citizen = User.objects.create_user("cit", "cit@test.com", "StrongPass123!")
        UserProfile.objects.create(user=self.citizen, role="citizen")
        self.admin = User.objects.create_user("adm", "adm@test.com", "StrongPass123!")
        UserProfile.objects.create(user=self.admin, role="admin")
        self.admin.is_staff = True
        self.admin.save()

    def report(self, description, lat=28.6139, lng=77.2090, address=""):
        return self.client.post(
            "/report/",
            {
                "description": description,
                "address": address,
                "latitude": lat,
                "longitude": lng,
                "photo": make_photo(),
            },
        )

    # TC01-TC03: auth
    def test_tc01_register_creates_account(self):
        resp = self.client.post(
            "/register/",
            {
                "username": "newuser",
                "email": "new@test.com",
                "role": "citizen",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(User.objects.filter(username="newuser").exists())
        self.assertTrue(
            UserProfile.objects.filter(user__username="newuser", role="citizen").exists()
        )

    def test_tc02_login_valid(self):
        self.assertTrue(self.client.login(username="cit", password="StrongPass123!"))

    def test_tc03_login_wrong_password(self):
        self.assertFalse(self.client.login(username="cit", password="wrong"))

    # TC04-TC05: reporting
    def test_tc04_report_issue_with_photo_and_location(self):
        self.client.force_login(self.citizen)
        resp = self.report("A big pothole near the school gate")
        self.assertEqual(resp.status_code, 302)
        issue = Issue.objects.latest("id")
        self.assertEqual(issue.reporter, self.citizen)
        self.assertTrue(issue.photo)
        self.assertEqual(issue.latitude, 28.6139)

    def test_tc05_report_without_location_rejected(self):
        self.client.force_login(self.citizen)
        resp = self.client.post(
            "/report/",
            {"description": "No location here", "photo": make_photo()},
        )
        self.assertEqual(resp.status_code, 200)  # form re-rendered with error
        self.assertEqual(Issue.objects.count(), 0)

    # TC06-TC07: AI classification
    def test_tc06_classifies_pothole(self):
        self.client.force_login(self.citizen)
        self.report("A big pothole on the main road")
        issue = Issue.objects.latest("id")
        self.assertEqual(issue.category.name, "Pothole")

    def test_manual_address_is_saved(self):
        self.client.force_login(self.citizen)
        resp = self.report(
            "pothole near the park", address="MG Road, Bengaluru", lng=77.5946
        )
        self.assertEqual(resp.status_code, 302)
        issue = Issue.objects.latest("id")
        self.assertEqual(issue.address, "MG Road, Bengaluru")

    def test_tc07_priority_high_for_severe(self):
        self.client.force_login(self.citizen)
        self.report("Accident risk, dangerous pothole in front of school")
        issue = Issue.objects.latest("id")
        self.assertEqual(issue.ai_priority, "High")

    def test_priority_medium_for_average(self):
        self.client.force_login(self.citizen)
        self.report("Garbage not collected")
        issue = Issue.objects.latest("id")
        self.assertEqual(issue.ai_priority, "Medium")

    # TC08: duplicate detection
    def test_tc08_duplicate_detected_nearby(self):
        self.client.force_login(self.citizen)
        self.report("A big pothole near the school gate", 28.6139, 77.2090)
        self.report("another pothole near the school road", 28.6141, 77.2093)
        dup = Issue.objects.latest("id")
        self.assertEqual(dup.duplicate_of.pk, Issue.objects.get(pk=dup.pk - 1).pk)

    def test_duplicate_not_flagged_far_away(self):
        self.client.force_login(self.citizen)
        self.report("A big pothole near the school gate", 28.6139, 77.2090)
        self.report("a pothole in another neighbourhood", 30.0, 78.0)
        self.assertIsNone(Issue.objects.latest("id").duplicate_of)

    # TC09: AI service down -> text fallback
    def test_tc09_fallback_when_ai_unreachable(self):
        self.client.force_login(self.citizen)
        self.report("broken streetlight not working for weeks")
        issue = Issue.objects.latest("id")
        self.assertEqual(issue.category.name, "Streetlight")

    def test_classify_issue_returns_fallback(self):
        result = classify_issue("water leak from the pipe")
        self.assertEqual(result["category"], "Water")

    # TC10: status update by admin
    def test_tc10_admin_updates_status(self):
        self.client.force_login(self.citizen)
        self.report("pothole near the park")
        issue = Issue.objects.latest("id")
        self.client.force_login(self.admin)
        resp = self.client.post(
            f"/issue/{issue.pk}/",
            {"new_status": "progress", "note": "dispatched"},
        )
        self.assertEqual(resp.status_code, 302)
        issue.refresh_from_db()
        self.assertEqual(issue.status, "progress")
        self.assertEqual(issue.status_updates.count(), 1)
        self.assertEqual(issue.status_updates.first().staff, self.admin)

    # TC11: citizen status tracking
    def test_tc11_citizen_sees_status(self):
        self.client.force_login(self.citizen)
        self.report("pothole near the park")
        issue = Issue.objects.latest("id")
        resp = self.client.get(f"/issue/{issue.pk}/")
        self.assertContains(resp, "Open")

    # TC13: upvote
    def test_tc13_upvote_counts_once_per_user(self):
        self.client.force_login(self.citizen)
        self.report("pothole near the park")
        issue = Issue.objects.latest("id")
        self.client.post(f"/issue/{issue.pk}/upvote/")
        self.client.post(f"/issue/{issue.pk}/upvote/")
        self.assertEqual(Upvote.objects.filter(issue=issue, user=self.citizen).count(), 0)
        self.client.post(f"/issue/{issue.pk}/upvote/")
        self.assertEqual(issue.upvotes.count(), 1)

    # TC12: map renders
    def test_tc12_map_renders_issues(self):
        self.client.force_login(self.citizen)
        self.report("pothole near the park")
        resp = self.client.get("/map/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "pothole near the park")

    # TC14: analytics dashboard (admin only)
    def test_tc14_analytics_for_admin(self):
        self.client.force_login(self.admin)
        resp = self.client.get("/analytics/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Analytics Dashboard")

    # TC15: access control
    def test_tc15_citizen_blocked_from_analytics(self):
        self.client.force_login(self.citizen)
        resp = self.client.get("/analytics/")
        self.assertEqual(resp.status_code, 302)

    def test_unauthenticated_redirects_to_login(self):
        resp = self.client.get("/report/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp.url)

    def test_unauthenticated_cannot_update_status(self):
        self.client.force_login(self.citizen)
        self.report("pothole near the park")
        issue = Issue.objects.latest("id")
        self.client.logout()
        resp = self.client.post(
            f"/issue/{issue.pk}/",
            {"new_status": "resolved", "note": ""},
        )
        self.assertEqual(resp.status_code, 302)  # redirected to login

    def test_resolved_sets_resolved_at(self):
        self.client.force_login(self.citizen)
        self.report("pothole near the park")
        issue = Issue.objects.latest("id")
        self.client.force_login(self.admin)
        self.client.post(
            f"/issue/{issue.pk}/",
            {"new_status": "resolved", "note": "fixed"},
        )
        issue.refresh_from_db()
        self.assertEqual(issue.status, "resolved")
        self.assertIsNotNone(issue.resolved_at)


class FallbackClassifierTests(TestCase):
    def test_categories(self):
        from fallback import classify

        self.assertEqual(classify("big pothole in the road")["category"], "Pothole")
        self.assertEqual(classify("garbage pile dumped")["category"], "Garbage")
        self.assertEqual(classify("street light not working")["category"], "Streetlight")
        self.assertEqual(classify("water leak from pipe")["category"], "Water")
        self.assertEqual(classify("something totally unrelated")["category"], "Other")

    def test_find_duplicate_returns_none_on_empty(self):
        self.assertIsNone(find_duplicate("anything", 28.6, 77.2))

    def test_no_categories_required_for_classify(self):
        self.assertEqual(Category.objects.count(), 0)


@override_settings(AI_SERVICE_URL=DEFAULT_AI_URL)
class LLMSettingsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("llmuser", "llm@test.com", "StrongPass123!")
        UserProfile.objects.create(user=self.user, role="citizen")

    def test_settings_page_requires_login(self):
        resp = self.client.get("/settings/llm/")
        self.assertEqual(resp.status_code, 302)

    def test_settings_page_renders(self):
        self.client.force_login(self.user)
        resp = self.client.get("/settings/llm/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "AI Settings")

    def test_save_settings(self):
        self.client.force_login(self.user)
        resp = self.client.post(
            "/settings/llm/",
            {"platform": "groq", "api_key": "gsk_test", "model": "qwen1.5-1.8b-chat"},
        )
        self.assertEqual(resp.status_code, 302)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.llm_platform, "groq")
        self.assertEqual(self.user.profile.llm_api_key, "gsk_test")
        self.assertEqual(self.user.profile.llm_model, "groq/qwen1.5-1.8b-chat")

    def test_unknown_platform_rejected(self):
        self.client.force_login(self.user)
        resp = self.client.post(
            "/settings/llm/",
            {"platform": "nope", "api_key": "x", "model": "y"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_models_api_rejects_unknown_platform(self):
        self.client.force_login(self.user)
        resp = self.client.get("/api/llm/models/?platform=nope&api_key=x")
        self.assertEqual(resp.status_code, 400)

    def test_nav_shows_ai_badge(self):
        self.user.profile.llm_platform = "groq"
        self.user.profile.llm_model = "groq/qwen3.6-27b"
        self.user.profile.save()
        self.client.force_login(self.user)
        resp = self.client.get("/")
        self.assertContains(resp, "groq · groq/qwen3.6-27b")
        self.assertContains(resp, '/settings/llm/')

    def test_nav_hides_badge_when_unconfigured(self):
        self.client.force_login(self.user)
        resp = self.client.get("/")
        self.assertNotContains(resp, "· groq")

    def test_suggest_description_surfaces_fallback_as_error(self):
        # AI_SERVICE_URL default in tests is unreachable -> Django local fallback,
        # which must surface as an error instead of echoing the hint.
        self.client.force_login(self.user)
        resp = self.client.post(
            "/api/suggest-description/",
            data='{"hint": "pothole on the road"}',
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 502)
        self.assertIn("error", resp.json())


@override_settings(ALLOWED_HOSTS=["testserver"], EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class PasswordResetTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("resetuser", "reset@test.com", "OldPass123!")
        UserProfile.objects.create(user=self.user, role="citizen")

    def _reset_url(self):
        mail.outbox.clear()
        resp = self.client.post("/password-reset/", {"email": "reset@test.com"})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, "/password-reset/done/")
        self.assertEqual(len(mail.outbox), 1)
        match = re.search(
            r"/password-reset/([A-Za-z0-9_-]+)/([A-Za-z0-9_-]+)/", mail.outbox[0].body
        )
        self.assertIsNotNone(match)
        # The token GET validates and 302s to /<uidb64>/set-password/, where the
        # form is actually posted (so the token never leaks as a Referer).
        resp = self.client.get(match.group(0), follow=True)
        self.assertEqual(resp.status_code, 200)
        return resp.request["PATH_INFO"]

    def test_reset_link_flow_changes_password(self):
        url = self._reset_url()
        resp = self.client.post(
            url, {"new_password1": "NewPass456!", "new_password2": "NewPass456!"}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, "/password-reset/complete/")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewPass456!"))

    def test_login_with_new_password(self):
        url = self._reset_url()
        self.client.post(url, {"new_password1": "NewPass456!", "new_password2": "NewPass456!"})
        self.assertTrue(self.client.login(username="resetuser", password="NewPass456!"))

    @override_settings(
        SITE_URL="https://civicsense.example.com",
        ALLOWED_HOSTS=["testserver", "localhost", "localhost:8000"],
    )
    def test_reset_email_local_request_links_to_localhost(self):
        mail.outbox.clear()
        resp = self.client.post(
            "/password-reset/", {"email": "reset@test.com"}, HTTP_HOST="localhost:8000"
        )
        self.assertEqual(resp.status_code, 302)
        msg = mail.outbox[0]
        self.assertIn("http://localhost:8000/password-reset/", msg.body)
        self.assertNotIn("civicsense.example.com", msg.body)
        html = next(content for content, mimetype in msg.alternatives if mimetype == "text/html")
        self.assertIn("http://localhost:8000/password-reset/", html)
        self.assertNotIn("civicsense.example.com", html)

    @override_settings(SITE_URL="https://civicsense.example.com")
    def test_reset_email_is_branded_and_uses_public_domain(self):
        mail.outbox.clear()
        self.client.post("/password-reset/", {"email": "reset@test.com"})
        msg = mail.outbox[0]
        self.assertEqual(msg.subject, "CivicSense — reset your password")
        self.assertIn("The CivicSense team", msg.body)
        self.assertIn("civicsense.example.com", msg.body)
        self.assertNotIn("localhost", msg.body)
        html = next(content for content, mimetype in msg.alternatives if mimetype == "text/html")
        for token in (
            "background:#28594c",
            "background:#326d5b",
            "background:#f6faf6",
            "civicsense.example.com",
            "Reset your password",
"automated message from CivicSense",
        ):
            self.assertIn(token, html)
        self.assertNotIn("localhost", html)

    def test_unknown_email_still_shows_done_page(self):
        mail.outbox.clear()
        self.client.post("/password-reset/", {"email": "ghost@test.com"})
        self.assertEqual(len(mail.outbox), 0)
        resp = self.client.get("/password-reset/done/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Check your email")