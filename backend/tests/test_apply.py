"""Auto-apply regression tests.

These cover the API surface and the safety rules that matter most: the tracker must never be
advanced unless a submission was actually verified, unmodelled hosts are refused, and nothing
works without a session.

Nothing here submits to a real ATS on purpose. A live submission would send a fabricated
application to an actual employer; the browser-level behaviour is covered instead by
scripts/test_apply_engine.py, which drives the engine against a local mock form.
"""
import sys
import uuid
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core  # noqa: E402
# The shared motor client binds to the first event loop it is used on, so a second asyncio.run()
# in the same process fails with "event loop is closed". conftest provides one suite-wide loop.
from conftest import run  # noqa: E402

BASE_URL = "http://localhost:8000"
DEMO_EMAIL = "demo@jobpilot.app"
DEMO_PASSWORD = "Demo@12345"


def _sess():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def demo():
    s = _sess()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s, r.json()


@pytest.fixture(scope="module")
def throwaway():
    email = f"apply_{uuid.uuid4().hex[:10]}@example.com"
    s = _sess()
    r = s.post(f"{BASE_URL}/api/auth/register",
               json={"email": email, "password": "TestPass123!", "name": "Apply Tester", "lang": "en"},
               timeout=30)
    assert r.status_code == 200, r.text
    return s, r.json(), email


def _mk_job(s, **over):
    """Insert a job straight into Mongo so the test controls the application URL exactly.

    The only public creation route is /api/jobs/manual, which runs an AI parse over free text and
    cannot guarantee a particular url, and the apply URL is exactly what these tests are about.
    """
    body = {"title": "Backend Engineer", "company": "Acme", "location": "Riyadh",
            "url": "https://jobs.lever.co/acme/123", "description": "Apply here.",
            "source": "lever", "source_ref": f"t{uuid.uuid4().hex[:8]}"}
    body.update(over)
    job_id = f"job_t{uuid.uuid4().hex[:12]}"

    async def _ins():
        await core.db.jobs.insert_one({**body, "job_id": job_id, "fingerprint": f"fp-{job_id}",
                                      "city": "Riyadh", "city_key": "riyadh", "country": "SA",
                                      "remote": "onsite", "created_at": core.iso()})

    run(_ins())
    return job_id


# --- auth ---
def test_apply_requires_auth():
    for path, method in (("/api/apply/profile", "get"), ("/api/apply/runs", "get")):
        r = getattr(requests, method)(f"{BASE_URL}{path}", timeout=15)
        assert r.status_code == 401, f"{path} should require auth, got {r.status_code}"


def test_apply_submit_requires_auth():
    r = requests.post(f"{BASE_URL}/api/apply", json={"job_id": "job_x", "submit": False}, timeout=15)
    assert r.status_code == 401


# --- profile ---
def test_profile_seeds_from_account(throwaway):
    s, me, _ = throwaway
    r = s.get(f"{BASE_URL}/api/apply/profile", timeout=30)
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["email"] == me["email"]
    assert p["first_name"] == "Apply"


def test_profile_roundtrip(throwaway):
    s, me, _ = throwaway
    body = {"first_name": "Amal", "last_name": "K", "email": me["email"], "phone": "+966500000000",
            "linkedin": "https://linkedin.com/in/amal", "website": "", "location": "Jeddah",
            "cover_letter": "Hello.", "attach_cv": False}
    r = s.put(f"{BASE_URL}/api/apply/profile", json=body, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json()["phone"] == "+966500000000"
    r = s.get(f"{BASE_URL}/api/apply/profile", timeout=30)
    assert r.json()["first_name"] == "Amal"
    assert r.json()["attach_cv"] is False


def test_profile_email_required_before_apply(throwaway):
    """An apply run must refuse to start when the profile has no email to submit under."""
    s, me, _ = throwaway
    s.put(f"{BASE_URL}/api/apply/profile",
          json={"first_name": "No", "last_name": "Mail", "email": "", "phone": "", "linkedin": "",
                "website": "", "location": "", "cover_letter": "", "attach_cv": False}, timeout=30)
    jid = _mk_job(s)
    r = s.post(f"{BASE_URL}/api/apply/preview", json={"job_id": jid}, timeout=60)
    assert r.status_code == 400, r.text
    # restore
    s.put(f"{BASE_URL}/api/apply/profile",
          json={"first_name": "Amal", "last_name": "K", "email": me["email"], "phone": "", "linkedin": "",
                "website": "", "location": "", "cover_letter": "", "attach_cv": False}, timeout=30)


# --- safety rules ---
def test_missing_job_404(throwaway):
    s, _, _ = throwaway
    r = s.post(f"{BASE_URL}/api/apply/preview", json={"job_id": "job_does_not_exist"}, timeout=30)
    assert r.status_code == 404, r.text


def test_job_without_link_400(throwaway):
    s, _, _ = throwaway
    jid = _mk_job(s, url="", description="no link")
    r = s.post(f"{BASE_URL}/api/apply/preview", json={"job_id": jid}, timeout=30)
    assert r.status_code == 400, r.text
    assert "no application link" in r.text.lower()


def test_unmodelled_host_refused(throwaway):
    """A scraped job pointing anywhere we do not model must not be driven by the browser."""
    s, _, _ = throwaway
    jid = _mk_job(s, url="https://definitely-not-an-ats.example.com/jobs/1")
    r = s.post(f"{BASE_URL}/api/apply/preview", json={"job_id": jid}, timeout=60)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "unsupported", body
    assert body["submitted"] is False
    assert "unrecognised_ats_host" in body["blockers"]


def test_blocked_run_does_not_advance_tracker(throwaway):
    """A refused or failed run must leave the tracker exactly as it was."""
    s, _, _ = throwaway
    jid = _mk_job(s, url="https://definitely-not-an-ats.example.com/jobs/2")
    r = s.post(f"{BASE_URL}/api/apply", json={"job_id": jid, "submit": True}, timeout=60)
    assert r.status_code == 200, r.text
    assert r.json()["submitted"] is False
    apps = s.get(f"{BASE_URL}/api/applications", timeout=30).json()
    mine = [a for a in (apps if isinstance(apps, list) else apps.get("applications", []))
            if a.get("job_id") == jid]
    for a in mine:
        assert a["status"] not in ("applied", "interview", "offer"), a


# --- history ---
def test_runs_history_records_blocked_attempt(throwaway):
    s, _, _ = throwaway
    runs = s.get(f"{BASE_URL}/api/apply/runs", timeout=30)
    assert runs.status_code == 200, runs.text
    body = runs.json()
    items = body if isinstance(body, list) else body.get("runs", [])
    assert items, "an apply run should have been recorded"
    first = items[0]
    for field in ("run_id", "job_id", "status", "submitted", "created_at"):
        assert field in first, f"missing {field} in run record: {first}"
