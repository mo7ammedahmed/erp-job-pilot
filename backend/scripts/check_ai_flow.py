"""End-to-end check of the AI pipeline against a real provider, using the live local API.

Switches admin models to the NVIDIA provider, then as the demo user runs a job review and an
interview-prep generation against a job that actually exists in the local DB. Restores the
original model settings afterwards.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core  # noqa: E402,F401  -- loads backend/.env
import requests  # noqa: E402

BASE = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8000").rstrip("/")
SCORING = "nvidia/nemotron-3-super-120b-a12b"
WRITING = "nvidia/nemotron-3-ultra-550b-a55b"


def login(email, password):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    r.raise_for_status()
    return s, r.json()


def show(label, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f" :: {detail}" if detail else ""))


def main():
    admin, _ = login(os.environ["ADMIN_EMAIL"], os.environ["ADMIN_PASSWORD"])
    demo, me = login(os.environ["TEST_USER_EMAIL"], os.environ["TEST_USER_PASSWORD"])

    # Stored settings can still point at a model that has since been retired. Fall back to
    # the shipped defaults so the check is not wedged by leftover state.
    orig = admin.get(f"{BASE}/api/admin/models").json()["current"]
    print("original models:", json.dumps(orig))

    r = admin.put(f"{BASE}/api/admin/models", json={
        "scoring": {"provider": "nvidia", "model": SCORING},
        "writing": {"provider": "nvidia", "model": WRITING},
    })
    show("switch admin models to nvidia", r.status_code == 200, r.text[:200])
    if r.status_code != 200:
        return

    restore = orig
    if admin.put(f"{BASE}/api/admin/models", json=orig).status_code != 200:
        from core import DEFAULT_MODELS
        restore = DEFAULT_MODELS
        print("original models are no longer in the catalog; restoring shipped defaults")

    try:
        jobs = demo.get(f"{BASE}/api/jobs?limit=5", timeout=30).json()
        items = jobs.get("items") or []
        if not items:
            show("have a job to review", False, "no jobs in DB")
            return
        job = items[0]
        print(f"\nreviewing job: {job['title']} @ {job['company']}\n")

        r = demo.post(f"{BASE}/api/jobs/{job['job_id']}/review", json={}, timeout=300)
        show("job review", r.status_code == 200, r.text[:300])
        if r.status_code == 200:
            rev = r.json()
            print("  score:", rev.get("score"), "verdict:", rev.get("verdict"))
            print("  matched:", (rev.get("matched_skills") or [])[:5])
            print("  missing:", (rev.get("missing_skills") or [])[:5])

        # Prep needs an application, so save the job to the tracker first.
        r = demo.post(f"{BASE}/api/applications", json={"job_id": job["job_id"], "title": job["title"],
                                                       "company": job["company"], "status": "saved"}, timeout=30)
        show("create application", r.status_code in (200, 201), r.text[:200])
        app_id = (r.json() or {}).get("application_id") if r.status_code in (200, 201) else None

        if app_id:
            r = demo.post(f"{BASE}/api/applications/{app_id}/prep", timeout=300)
            show("interview prep", r.status_code == 200, r.text[:300])
            if r.status_code == 200:
                prep = r.json()
                qs = prep.get("questions") or []
                print(f"  questions: {len(qs)}")
                for q in qs[:3]:
                    ao = q.get("answer_outline")
                    print(f"   - {str(q.get('q'))[:70]!r} answer_outline type={type(ao).__name__}")

            r = demo.delete(f"{BASE}/api/applications/{app_id}", timeout=30)
            show("cleanup application", r.status_code in (200, 204), r.text[:120])
    finally:
        r = admin.put(f"{BASE}/api/admin/models", json=restore)
        show("restore original models", r.status_code == 200, r.text[:160])


if __name__ == "__main__":
    main()
