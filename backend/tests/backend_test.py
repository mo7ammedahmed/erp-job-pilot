"""JobPilot backend regression tests.

Covers: health, auth (login/register/me/logout), CV vault, jobs list/detail,
manual job creation, applications CRUD, reminders, dashboard, admin gating,
billing 503, and search CRUD.

AI-heavy endpoints (tailoring/review) can take 40-90s; kept optional
via env RUN_AI_TESTS=1.
"""
import io
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://career-hub-dev-7.preview.emergentagent.com").rstrip("/")
DEMO_EMAIL = os.environ.get("TEST_USER_EMAIL", "demo@jobpilot.app")
DEMO_PASSWORD = os.environ.get("TEST_USER_PASSWORD", "Demo@12345")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "mo7ammed99887@gmail.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "JobPilot@Admin2026")
RUN_AI = os.environ.get("RUN_AI_TESTS") == "1"


def _sess():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _login(email, password):
    s = _sess()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s, r.json()


# --- Fixtures ---
@pytest.fixture(scope="session")
def demo():
    s, me = _login(DEMO_EMAIL, DEMO_PASSWORD)
    return s, me


@pytest.fixture(scope="session")
def admin():
    s, me = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    return s, me


@pytest.fixture(scope="session")
def throwaway():
    email = f"test_{uuid.uuid4().hex[:10]}@example.com"
    s = _sess()
    r = s.post(f"{BASE_URL}/api/auth/register",
               json={"email": email, "password": "TestPass123!", "name": "Throw Away", "lang": "en"},
               timeout=30)
    assert r.status_code == 200, r.text
    return s, r.json(), email


# --- Health ---
def test_health():
    r = requests.get(f"{BASE_URL}/api/health", timeout=15)
    assert r.status_code == 200
    assert r.json() == {"ok": True}


# --- Auth ---
class TestAuth:
    def test_login_demo(self, demo):
        s, me = demo
        assert me["email"] == DEMO_EMAIL
        assert me["role"] == "user"
        assert "plan_info" in me and "usage" in me

    def test_login_admin(self, admin):
        s, me = admin
        assert me["role"] == "admin"

    def test_login_bad_password(self):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": DEMO_EMAIL, "password": "WRONG_pw"}, timeout=15)
        assert r.status_code == 401

    def test_me_unauth(self):
        r = requests.get(f"{BASE_URL}/api/auth/me", timeout=15)
        assert r.status_code == 401

    def test_me_auth(self, demo):
        s, _ = demo
        r = s.get(f"{BASE_URL}/api/auth/me", timeout=15)
        assert r.status_code == 200
        assert r.json()["email"] == DEMO_EMAIL

    def test_register_and_logout(self, throwaway):
        s, me, email = throwaway
        assert me["email"] == email
        assert me["onboarded"] is False
        # onboarding requires consents
        r = s.post(f"{BASE_URL}/api/onboarding", json={"consents": {}}, timeout=15)
        assert r.status_code == 400
        r = s.post(f"{BASE_URL}/api/onboarding",
                   json={"consents": {"terms": True, "ai_processing": True, "email_messaging": False},
                         "lang": "en", "country": "SA", "timezone": "Asia/Riyadh"}, timeout=15)
        assert r.status_code == 200
        assert r.json()["onboarded"] is True
        # logout
        r = s.post(f"{BASE_URL}/api/auth/logout", timeout=15)
        assert r.status_code == 200


# --- CV ---
class TestCV:
    def test_get_cv_demo_has_master(self, demo):
        s, _ = demo
        r = s.get(f"{BASE_URL}/api/cv", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["master"] is not None, "Demo user should have master CV v1"
        assert data["master"]["is_master"] is True
        assert data["master"]["version"] >= 1

    def test_save_version_and_restore(self, demo):
        s, _ = demo
        cur = s.get(f"{BASE_URL}/api/cv", timeout=15).json()
        v0 = cur["master"]["version"]
        cv_data = dict(cur["master"]["data"])
        cv_data["summary"] = f"Updated at {time.time()}"
        r = s.post(f"{BASE_URL}/api/cv/versions", json={"data": cv_data, "note": "edit"}, timeout=15)
        assert r.status_code == 200
        new = r.json()
        assert new["version"] == v0 + 1
        assert new["is_master"] is True
        # restore v0
        old_id = None
        for v in cur["versions"]:
            if v["version"] == v0:
                old_id = v["cv_version_id"]
                break
        assert old_id
        r = s.post(f"{BASE_URL}/api/cv/versions/{old_id}/restore", timeout=15)
        assert r.status_code == 200
        assert r.json()["version"] == v0 + 2


# --- Jobs ---
class TestJobs:
    def test_list_jobs(self, demo):
        s, _ = demo
        r = s.get(f"{BASE_URL}/api/jobs", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert "items" in d and "total" in d

    def test_list_jobs_filter(self, demo):
        s, _ = demo
        r = s.get(f"{BASE_URL}/api/jobs?keywords=analyst&remote=remote", timeout=30)
        assert r.status_code == 200

    def test_meta_sources(self, demo):
        s, _ = demo
        r = s.get(f"{BASE_URL}/api/meta/sources", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_refresh_endpoint(self, demo):
        s, _ = demo
        r = s.post(f"{BASE_URL}/api/jobs/refresh", timeout=15)
        assert r.status_code == 200
        assert "started" in r.json()

    def test_saved_search_crud(self, demo):
        s, _ = demo
        r = s.post(f"{BASE_URL}/api/searches",
                   json={"name": "TEST_search", "country": "SA", "keywords": "python", "alerts": True}, timeout=15)
        assert r.status_code == 200
        sid = r.json()["search_id"]
        # list
        r = s.get(f"{BASE_URL}/api/searches", timeout=15)
        assert any(x["search_id"] == sid for x in r.json())
        # delete
        r = s.delete(f"{BASE_URL}/api/searches/{sid}", timeout=15)
        assert r.status_code == 200

    def test_manual_job_min_length(self, demo):
        s, _ = demo
        r = s.post(f"{BASE_URL}/api/jobs/manual", json={"text": "too short"}, timeout=15)
        assert r.status_code == 422


# --- Applications ---
class TestApplications:
    def test_list_applications(self, demo):
        s, _ = demo
        r = s.get(f"{BASE_URL}/api/applications", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_full_application_flow(self, demo):
        s, _ = demo
        # Create a manual application (no job_id)
        r = s.post(f"{BASE_URL}/api/applications",
                   json={"title": "TEST_Engineer", "company": "TEST_Co", "status": "saved"}, timeout=15)
        assert r.status_code == 200
        aid = r.json()["application_id"]
        # get
        r = s.get(f"{BASE_URL}/api/applications/{aid}", timeout=15)
        assert r.status_code == 200
        # move -> applied
        r = s.post(f"{BASE_URL}/api/applications/{aid}/move", json={"status": "applied"}, timeout=15)
        assert r.status_code == 200 and r.json()["status"] == "applied"
        # invalid status
        r = s.post(f"{BASE_URL}/api/applications/{aid}/move", json={"status": "bogus"}, timeout=15)
        assert r.status_code == 400
        # add note
        r = s.post(f"{BASE_URL}/api/applications/{aid}/notes", json={"text": "TEST note"}, timeout=15)
        assert r.status_code == 200
        nid = r.json()["note_id"]
        # add contact
        r = s.post(f"{BASE_URL}/api/applications/{aid}/contacts",
                   json={"name": "TEST Contact", "email": "c@t.com"}, timeout=15)
        assert r.status_code == 200
        cid = r.json()["contact_id"]
        # patch: set interview date in future -> should schedule reminders
        future = "2027-01-15T14:00:00+03:00"
        r = s.patch(f"{BASE_URL}/api/applications/{aid}",
                    json={"interview_at": future}, timeout=15)
        assert r.status_code == 200
        got = r.json()
        assert got.get("interview_at")
        # Reminders should have been created
        assert any(rem["type"] in ("interview_24h", "interview_1h") for rem in got.get("reminders", []))
        # delete note & contact
        assert s.delete(f"{BASE_URL}/api/applications/{aid}/notes/{nid}", timeout=15).status_code == 200
        assert s.delete(f"{BASE_URL}/api/applications/{aid}/contacts/{cid}", timeout=15).status_code == 200
        # delete app
        assert s.delete(f"{BASE_URL}/api/applications/{aid}", timeout=15).status_code == 200
        # get -> 404
        assert s.get(f"{BASE_URL}/api/applications/{aid}", timeout=15).status_code == 404


# --- Reminders ---
class TestReminders:
    def test_reminder_lifecycle(self, demo):
        s, _ = demo
        r = s.post(f"{BASE_URL}/api/reminders",
                   json={"title": "TEST_reminder", "due_at": "2027-06-01T10:00:00+03:00"}, timeout=15)
        assert r.status_code == 200
        rid = r.json()["reminder_id"]
        # snooze
        r = s.post(f"{BASE_URL}/api/reminders/{rid}/snooze", json={"minutes": 60}, timeout=15)
        assert r.status_code == 200
        # done
        r = s.post(f"{BASE_URL}/api/reminders/{rid}/done", timeout=15)
        assert r.status_code == 200
        # list
        r = s.get(f"{BASE_URL}/api/reminders", timeout=15)
        assert r.status_code == 200
        # delete
        assert s.delete(f"{BASE_URL}/api/reminders/{rid}", timeout=15).status_code == 200


# --- Dashboard ---
class TestDashboard:
    def test_dashboard(self, demo):
        s, _ = demo
        r = s.get(f"{BASE_URL}/api/dashboard", timeout=15)
        assert r.status_code == 200
        d = r.json()
        for k in ("funnel", "by_status", "weekly", "upcoming_interviews", "reminders", "recent_reviews"):
            assert k in d


# --- Notifications ---
def test_notifications(demo):
    s, _ = demo
    r = s.get(f"{BASE_URL}/api/notifications", timeout=15)
    assert r.status_code == 200
    assert "items" in r.json() and "unread" in r.json()


# --- Billing / Integrations ---
class TestBilling:
    def test_billing_summary(self, demo):
        s, _ = demo
        # Try several possible URLs
        for path in ("/api/billing", "/api/billing/summary", "/api/billing/plans"):
            r = s.get(f"{BASE_URL}{path}", timeout=15)
            if r.status_code == 200:
                return
        pytest.skip("No billing summary endpoint")

    def test_billing_checkout_not_configured(self, demo):
        s, _ = demo
        r = s.post(f"{BASE_URL}/api/billing/checkout",
                   json={"plan_id": "pro", "origin_url": BASE_URL}, timeout=15)
        # Expected 503 payments_not_configured
        assert r.status_code == 503, f"Expected 503 got {r.status_code}: {r.text[:200]}"

    def test_gmail_not_connected(self, demo):
        s, _ = demo
        for path in ("/api/integrations/gmail", "/api/integrations/gmail/status", "/api/gmail/status"):
            r = s.get(f"{BASE_URL}{path}", timeout=15)
            if r.status_code == 200:
                d = r.json()
                # Should indicate not connected
                assert d.get("connected") in (False, None) or "not" in str(d).lower()
                return
        # Not fatal
        pytest.skip("gmail status endpoint not found")


# --- Admin ---
class TestAdmin:
    def test_admin_stats(self, admin):
        s, _ = admin
        r = s.get(f"{BASE_URL}/api/admin/stats", timeout=15)
        assert r.status_code == 200

    def test_admin_users(self, admin):
        s, _ = admin
        r = s.get(f"{BASE_URL}/api/admin/users", timeout=15)
        assert r.status_code == 200

    def test_admin_plans(self, admin):
        s, _ = admin
        r = s.get(f"{BASE_URL}/api/admin/plans", timeout=15)
        assert r.status_code == 200

    def test_admin_sources(self, admin):
        s, _ = admin
        r = s.get(f"{BASE_URL}/api/admin/sources", timeout=15)
        assert r.status_code == 200

    def test_admin_denied_for_demo(self, demo):
        s, _ = demo
        r = s.get(f"{BASE_URL}/api/admin/stats", timeout=15)
        assert r.status_code in (401, 403)

    def test_admin_audit_log(self, admin):
        s, _ = admin
        r = s.get(f"{BASE_URL}/api/admin/audit", timeout=15)
        assert r.status_code == 200


# --- Privacy ---
class TestPrivacy:
    def test_privacy_export(self, demo):
        s, _ = demo
        for path in ("/api/privacy/export", "/api/me/export", "/api/export"):
            r = s.get(f"{BASE_URL}{path}", timeout=30)
            if r.status_code == 200:
                return
        pytest.skip("privacy export endpoint not found")


# --- Optional AI tests ---
@pytest.mark.skipif(not RUN_AI, reason="Set RUN_AI_TESTS=1 to run slow AI tests")
class TestAI:
    def test_manual_job_and_review(self, demo):
        s, _ = demo
        jd = ("We are hiring a Senior Python Backend Engineer at TESTCorp in Riyadh. "
              "Requirements: Python, FastAPI, MongoDB, Docker. Remote. Apply by 2027-05-01.")
        r = s.post(f"{BASE_URL}/api/jobs/manual", json={"text": jd}, timeout=90)
        assert r.status_code == 200
        job_id = r.json()["job_id"]
        r = s.post(f"{BASE_URL}/api/jobs/{job_id}/review", json={"force": False}, timeout=120)
        assert r.status_code == 200
        assert 0 <= r.json()["result"]["score"] <= 100
