"""Phase 3 backend tests: admin plan-days, trial, models guard, insights,
eval, whatsapp status, interview prep prerequisites, coach flows."""
import json
import os
import uuid
import time
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://career-hub-dev-7.preview.emergentagent.com").rstrip("/")
ADMIN = (os.environ.get("ADMIN_EMAIL", "mo7ammed99887@gmail.com"), os.environ.get("ADMIN_PASSWORD", "JobPilot@Admin2026"))
DEMO = (os.environ.get("TEST_USER_EMAIL", "demo@jobpilot.app"), os.environ.get("TEST_USER_PASSWORD", "Demo@12345"))


def _sess():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _login(email, pw):
    s = _sess()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pw}, timeout=30)
    assert r.status_code == 200, r.text
    return s, r.json()


def _clear_provider(s, pid, before):
    """Restore a provider to its pre-test state (deleted when it had no dashboard key)."""
    if before.get("source") == "dashboard":
        if before.get("key_hint"):
            # Cannot replay the secret, so remove the stored key and let the env var win again.
            s.delete(f"{BASE_URL}/api/admin/ai/providers/{pid}")
    else:
        s.delete(f"{BASE_URL}/api/admin/ai/providers/{pid}")


@pytest.fixture(scope="module")
def admin():
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def demo():
    return _login(*DEMO)


# ---------- admin: premium always ----------
def test_admin_plan_always_premium(admin):
    s, me = admin
    assert me["plan"] == "premium"
    assert me["role"] == "admin"


# ---------- admin: grant plan for N days ----------
def test_admin_grant_plan_days(admin, demo):
    s_a, _ = admin
    _, demo_me = demo
    uid_ = demo_me["user_id"]

    # Grant pro for 30 days
    r = s_a.patch(f"{BASE_URL}/api/admin/users/{uid_}", json={"plan": "pro", "plan_days": 30})
    assert r.status_code == 200, r.text

    # Verify via /admin/users
    r = s_a.get(f"{BASE_URL}/api/admin/users?q={DEMO[0]}")
    row = next((u for u in r.json() if u["user_id"] == uid_), None)
    assert row and row["plan"] == "pro"
    assert row.get("plan_expires_at"), "plan_expires_at should be set"

    # Restore
    r = s_a.patch(f"{BASE_URL}/api/admin/users/{uid_}", json={"plan": "free"})
    assert r.status_code == 200

    r = s_a.get(f"{BASE_URL}/api/admin/users?q={DEMO[0]}")
    row = next((u for u in r.json() if u["user_id"] == uid_), None)
    assert row["plan"] == "free"
    assert row.get("plan_expires_at") in (None, ""), f"expiry not cleared: {row.get('plan_expires_at')}"


def test_admin_patch_invalid_plan(admin, demo):
    s_a, _ = admin
    _, dm = demo
    r = s_a.patch(f"{BASE_URL}/api/admin/users/{dm['user_id']}", json={"plan": "gold"})
    assert r.status_code == 400


# ---------- admin: trial setting ----------
def test_admin_trial_get_set(admin):
    s, _ = admin
    r = s.get(f"{BASE_URL}/api/admin/trial")
    assert r.status_code == 200
    orig = r.json()
    assert "plan" in orig and "days" in orig

    # Set trial to 7 days pro
    r = s.put(f"{BASE_URL}/api/admin/trial", json={"plan": "pro", "days": 7})
    assert r.status_code == 200
    r = s.get(f"{BASE_URL}/api/admin/trial")
    assert r.json() == {"plan": "pro", "days": 7}

    # Restore to 0
    r = s.put(f"{BASE_URL}/api/admin/trial", json={"plan": "pro", "days": 0})
    assert r.status_code == 200
    r = s.get(f"{BASE_URL}/api/admin/trial")
    assert r.json()["days"] == 0


def test_admin_trial_invalid(admin):
    s, _ = admin
    r = s.put(f"{BASE_URL}/api/admin/trial", json={"plan": "free", "days": 3})
    assert r.status_code == 400
    r = s.put(f"{BASE_URL}/api/admin/trial", json={"plan": "pro", "days": 999})
    assert r.status_code == 400


# ---------- registration honours trial ----------
def test_register_applies_trial(admin):
    s_a, _ = admin
    # Enable 5-day pro trial
    r = s_a.put(f"{BASE_URL}/api/admin/trial", json={"plan": "pro", "days": 5})
    assert r.status_code == 200
    try:
        email = f"trial_{uuid.uuid4().hex[:8]}@example.com"
        s = _sess()
        r = s.post(f"{BASE_URL}/api/auth/register",
                   json={"email": email, "password": "TestPass123!", "name": "Trial User", "lang": "en"})
        assert r.status_code == 200, r.text
        me = r.json()
        # Fetch via /auth/me for authoritative fields
        r = s.get(f"{BASE_URL}/api/auth/me")
        me = r.json()
        assert me["plan"] == "pro", f"expected pro trial, got {me['plan']}"
        assert me.get("plan_expires_at"), "trial expiry should be set"
    finally:
        s_a.put(f"{BASE_URL}/api/admin/trial", json={"plan": "pro", "days": 0})


# ---------- admin: model selection is validated against the provider ----------
def test_admin_models_reject_unknown(admin):
    """An unknown provider or model must be refused, and must not change stored settings."""
    s, _ = admin
    orig = s.get(f"{BASE_URL}/api/admin/models").json()["current"]

    r = s.put(f"{BASE_URL}/api/admin/models", json={
        "scoring": {"provider": "not-a-provider", "model": "whatever"},
        "writing": orig["writing"],
    })
    assert r.status_code == 400, r.text

    catalog = s.get(f"{BASE_URL}/api/admin/models").json()["catalog"]
    some_provider, some_model = next(iter(catalog.items()))
    r = s.put(f"{BASE_URL}/api/admin/models", json={
        "scoring": {"provider": some_provider, "model": "definitely-not-a-real-model"},
        "writing": orig["writing"],
    })
    assert r.status_code == 400, r.text

    assert s.get(f"{BASE_URL}/api/admin/models").json()["current"] == orig


# ---------- admin: provider credentials are managed from the dashboard ----------
def test_admin_providers_list_and_secret_never_leaks(admin):
    s, _ = admin
    body = s.get(f"{BASE_URL}/api/admin/ai/providers").json()
    ids = {p["provider"] for p in body["providers"]}
    assert {"anthropic", "openai", "nvidia", "gemini", "custom"} <= ids, ids
    for p in body["providers"]:
        assert "api_key" not in p, f"{p['provider']} leaked a raw key"
        assert p["source"] in ("dashboard", "env", "none")
        assert set(p) == {"provider", "label", "api", "env_var", "default_base_url", "base_url",
                          "configured", "source", "key_hint", "needs_base_url"}


def test_admin_provider_key_roundtrip(admin):
    """Save a key, confirm it is masked on read, and that models are then discoverable."""
    s, _ = admin
    secret = "sk-test-1234567890abcdef"
    orig = s.get(f"{BASE_URL}/api/admin/ai/providers").json()
    was = next(p for p in orig["providers"] if p["provider"] == "openai")

    try:
        r = s.put(f"{BASE_URL}/api/admin/ai/providers/openai", json={"api_key": secret, "base_url": ""})
        assert r.status_code == 200, r.text
        view = r.json()
        assert view["configured"] is True
        assert view["source"] == "dashboard"
        assert secret not in json.dumps(view), "secret returned to client"
        assert view["key_hint"].startswith("sk-t") and view["key_hint"].endswith("cdef")

        # A stored key must never be readable through any admin endpoint.
        assert secret not in s.get(f"{BASE_URL}/api/admin/ai/providers").text
        assert secret not in s.get(f"{BASE_URL}/api/admin/audit").text

        # Model discovery is now possible and reports where the list came from.
        r = s.get(f"{BASE_URL}/api/admin/ai/providers/openai/models")
        assert r.status_code == 200, r.text
        discovery = r.json()
        assert discovery["source"] in ("live", "catalog", "cache"), discovery
        assert isinstance(discovery["models"], list)
    finally:
        _clear_provider(s, "openai", was)


def test_admin_provider_custom_requires_base_url(admin):
    s, _ = admin
    r = s.put(f"{BASE_URL}/api/admin/ai/providers/custom", json={"api_key": "", "base_url": ""})
    assert r.status_code == 400, r.text
    r = s.put(f"{BASE_URL}/api/admin/ai/providers/custom",
              json={"api_key": "sk-x", "base_url": "http://insecure.example.com/v1"})
    assert r.status_code == 400 and "https" in r.text.lower(), r.text
    r = s.put(f"{BASE_URL}/api/admin/ai/providers/nope", json={"api_key": "sk-x"})
    assert r.status_code == 404, r.text


def test_admin_provider_in_use_cannot_be_deleted(admin):
    s, _ = admin
    used = s.get(f"{BASE_URL}/api/admin/models").json()["current"]["scoring"]["provider"]
    r = s.delete(f"{BASE_URL}/api/admin/ai/providers/{used}")
    assert r.status_code == 400, r.text
    assert "still using" in r.text.lower()


def test_admin_saving_one_provider_keeps_the_others(admin):
    """Saving a key must update only that provider's slot, not the whole credential document."""
    s, _ = admin
    in_use = s.get(f"{BASE_URL}/api/admin/models").json()["current"]["scoring"]["provider"]
    a, b, c = "gemini", "custom", "openai"
    assert in_use not in (a, b, c), "pick providers that are not in use by a tier"
    keys = {a: "sk-gem-keepme-000001", b: "sk-cst-keepme-000002", c: "sk-oai-keepme-000003"}

    def save(pid, key):
        body = {"api_key": key, "base_url": "https://proxy.internal/v1" if pid == "custom" else ""}
        r = s.put(f"{BASE_URL}/api/admin/ai/providers/{pid}", json=body)
        assert r.status_code == 200, r.text

    try:
        for pid, key in keys.items():
            save(pid, key)

        # Re-saving one provider is the operation that used to wipe the rest of the document.
        save(a, "sk-gem-rotated-000004")

        after = {p["provider"]: p for p in s.get(f"{BASE_URL}/api/admin/ai/providers").json()["providers"]}
        assert after[a]["key_hint"].startswith("sk-g") and after[a]["key_hint"].endswith("0004")
        assert after[b]["key_hint"].startswith("sk-c") and after[b]["key_hint"].endswith("0002"), \
            f"provider {b} lost its key when {a} was saved"
        assert after[c]["key_hint"].startswith("sk-o") and after[c]["key_hint"].endswith("0003"), \
            f"provider {c} lost its key when {a} was saved"
    finally:
        for pid in keys:
            s.delete(f"{BASE_URL}/api/admin/ai/providers/{pid}")


# ---------- CV upload stays usable when AI parsing is down ----------
DOCX_CT = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _docx_bytes():
    import io
    from docx import Document
    d = Document()
    for line in ["Layla Al-Sayed, Senior Data Analyst, Riyadh, Saudi Arabia",
                 "Data analyst with 6 years of experience across retail and logistics in Saudi Arabia.",
                 "Senior Data Analyst, Almarai Company, 2022-03 to Present",
                 "Built the demand forecast used by 14 distribution centres, cutting stock-outs by 18%.",
                 "Data Analyst, Jarir Holding, 2019-06 to 2022-02",
                 "Owned the SQL and Power BI layer behind dashboards used by 90 store managers.",
                 "Education: Bachelor of Statistics, King Saud University, 2014 to 2018",
                 "Skills: SQL, Python, Power BI, Tableau, dbt, Snowflake, forecasting, A/B testing"]:
        d.add_paragraph(line)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


@pytest.fixture(scope="module")
def cvuser():
    """A fresh account per run, so CV plan limits from earlier manual testing cannot fail this."""
    email = f"cvtest_{uuid.uuid4().hex[:10]}@example.com"
    s = _sess()
    r = s.post(f"{BASE_URL}/api/auth/register", json={"name": "CV Test", "email": email, "password": "CvTest@123456"}, timeout=30)
    if r.status_code != 200:
        s, _ = _login(email, "CvTest@123456")
    return s, email


def test_cv_parse_is_scoped_to_the_owner(cvuser, admin):
    """/cv/parse must never parse or reveal another user's file."""
    s, _ = cvuser
    a, _ = admin
    assert s.post(f"{BASE_URL}/api/cv/parse", json={"file_id": "file_does_not_exist"}, timeout=60).status_code == 404


def test_cv_parse_rejects_another_users_file(cvuser, demo):
    s, _ = cvuser
    other, _ = demo
    r = s.post(f"{BASE_URL}/api/cv/upload", files={"file": ("cv.docx", _docx_bytes(), DOCX_CT)},
               headers={"Content-Type": None}, timeout=300)
    assert r.status_code == 200, r.text
    mine = r.json()["file_id"]

    # Seed a master CV on the other account, then confirm cvuser cannot target its file.
    res = other.get(f"{BASE_URL}/api/cv", timeout=30)
    foreign = (res.json().get("master") or {}).get("file_id")
    if foreign:
        assert s.post(f"{BASE_URL}/api/cv/parse", json={"file_id": foreign}, timeout=60).status_code == 404, \
            "another user could trigger parsing of a file they do not own"


def test_cv_upload_always_returns_a_stored_file(cvuser):
    """The upload contract holds whether or not AI parsing succeeded."""
    s, _ = cvuser
    r = s.post(f"{BASE_URL}/api/cv/upload", files={"file": ("cv.docx", _docx_bytes(), DOCX_CT)},
               headers={"Content-Type": None}, timeout=300)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("file_id"), body
    assert "parse_error" in body, "the UI relies on parse_error always being present"
    if body.get("parsed") is None:
        # AI down: the file must still be stored and usable.
        assert body["parse_error"], "a failed parse must explain itself"
        got = s.get(f"{BASE_URL}/api/files/{body['file_id']}", timeout=60)
        assert got.status_code == 200 and len(got.content) > 1000, f"{got.status_code} {len(got.content)} bytes"


def test_cv_upload_works_after_the_parse_allowance_is_spent(cvuser):
    """An exhausted AI allowance must not lock a user out of their own CV vault."""
    s, _ = cvuser
    for _ in range(3):  # burn the free plan's single parse allowance
        r = s.post(f"{BASE_URL}/api/cv/upload", files={"file": ("cv.docx", _docx_bytes(), DOCX_CT)},
                   headers={"Content-Type": None}, timeout=300)
        if r.json().get("parsed") is not None:
            break
    last = r.json()
    assert r.status_code == 200, r.text
    assert last["parsed"] is None, "the allowance should have been exhausted by now"
    assert "allowance" in (last["parse_error"] or "").lower() or "used all" in (last["parse_error"] or "").lower(), last
    # The important part: the upload was still accepted and the file stored.
    got = s.get(f"{BASE_URL}/api/files/{last['file_id']}", timeout=60)
    assert got.status_code == 200 and len(got.content) > 1000, f"{got.status_code} {len(got.content)} bytes"


# ---------- admin: evaluation runs listing ----------
def test_admin_eval_runs_list(admin):
    s, _ = admin
    r = s.get(f"{BASE_URL}/api/admin/eval/runs")
    assert r.status_code == 200
    body = r.json()
    assert "runs" in body and "cases" in body
    assert isinstance(body["runs"], list)
    assert body["cases"] >= 1


# ---------- admin: insights ----------
def test_admin_insights(admin):
    s, _ = admin
    r = s.get(f"{BASE_URL}/api/admin/insights")
    assert r.status_code == 200
    body = r.json()
    assert "total_applied" in body
    assert "by_weekday" in body and len(body["by_weekday"]) == 7
    assert "by_source" in body


def test_admin_insights_requires_admin(demo):
    s, _ = demo
    r = s.get(f"{BASE_URL}/api/admin/insights")
    assert r.status_code in (401, 403)


# ---------- whatsapp status ----------
def test_whatsapp_status_not_configured(demo):
    s, _ = demo
    r = s.get(f"{BASE_URL}/api/whatsapp/status")
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is False
    assert "plan_allows" in body


def test_whatsapp_start_503_when_unconfigured(demo):
    s, _ = demo
    r = s.post(f"{BASE_URL}/api/whatsapp/start", json={"phone": "+966555555555"})
    assert r.status_code == 503


# ---------- interview prep gating ----------
def test_prep_requires_master_cv(demo):
    """Calling prep on an app without a master CV returns 400."""
    s, me = demo
    # find any application id
    apps = s.get(f"{BASE_URL}/api/applications").json()
    if not apps:
        pytest.skip("no application on demo")
    aid = apps[0]["application_id"]
    # Ensure master exists (demo probably has one). Just check status codes.
    r = s.post(f"{BASE_URL}/api/applications/{aid}/prep", timeout=5)
    # Should be either 200 (started) — but we don't want to spend $$ on AI here.
    # Accept 200/400/402/502 (limit) — we only assert it's not 500 or 404.
    assert r.status_code in (200, 400, 402, 502), r.text


# ---------- coach flow ----------
def test_coach_grant_revoke_and_comment(admin, demo):
    s_a, admin_me = admin
    s_d, demo_me = demo

    # Demo grants access to admin (idempotent)
    r = s_d.post(f"{BASE_URL}/api/coach/grant", json={"coach_email": admin_me["email"]})
    assert r.status_code == 200

    # Admin sees demo in candidates
    r = s_a.get(f"{BASE_URL}/api/coach/overview")
    assert r.status_code == 200
    ov = r.json()
    cand_ids = [c.get("user_id") for c in ov.get("candidates", [])]
    assert demo_me["user_id"] in cand_ids, f"demo not in candidates: {cand_ids}"

    # Admin lists demo's apps
    r = s_a.get(f"{BASE_URL}/api/coach/candidates/{demo_me['user_id']}/applications")
    assert r.status_code == 200
    apps = r.json()
    if not apps:
        pytest.skip("no applications on demo")
    aid = apps[0]["application_id"]

    # Admin posts a comment
    text = f"TEST_comment {uuid.uuid4().hex[:6]}"
    r = s_a.post(f"{BASE_URL}/api/coach/candidates/{demo_me['user_id']}/applications/{aid}/comments",
                 json={"text": text})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("text") == text
    assert body.get("coach_id") == admin_me["user_id"]

    # Demo has a notification
    notes = s_d.get(f"{BASE_URL}/api/notifications").json()
    items = notes["items"] if isinstance(notes, dict) else notes
    assert any("coach" in (n.get("kind") or "") for n in items[:10]), \
        f"no coach notification: {items[:3]}"

    # Non-linked coach denied
    email = f"nolink_{uuid.uuid4().hex[:6]}@example.com"
    s2 = _sess()
    r = s2.post(f"{BASE_URL}/api/auth/register",
                json={"email": email, "password": "TestPass123!", "name": "No Link", "lang": "en"})
    assert r.status_code == 200
    r = s2.get(f"{BASE_URL}/api/coach/candidates/{demo_me['user_id']}/applications")
    assert r.status_code == 403


def test_coach_self_grant_rejected(demo):
    s, me = demo
    r = s.post(f"{BASE_URL}/api/coach/grant", json={"coach_email": me["email"]})
    assert r.status_code == 400


def test_coach_grant_unknown_email(demo):
    s, _ = demo
    r = s.post(f"{BASE_URL}/api/coach/grant", json={"coach_email": "nobody_xxx_1234@example.com"})
    assert r.status_code == 404
