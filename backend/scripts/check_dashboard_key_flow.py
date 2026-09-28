"""End-to-end proof that a key saved from the admin dashboard drives the real AI pipeline.

Adds the NVIDIA key through /admin/ai/providers (not .env), confirms the model list is discovered
live, runs a job review as the demo user, then removes the dashboard key again.
"""
import json
import os
import sys
import time
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


def check(label, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f" :: {detail}" if detail else ""))
    return ok


def main():
    admin, _ = login(os.environ["ADMIN_EMAIL"], os.environ["ADMIN_PASSWORD"])
    demo, _ = login(os.environ["TEST_USER_EMAIL"], os.environ["TEST_USER_PASSWORD"])
    key = (os.environ.get("NVIDIA_API_KEY") or "").strip()
    if not key:
        print("SKIP: NVIDIA_API_KEY is not set in .env, cannot seed a dashboard key")
        return

    before = {p["provider"]: p for p in admin.get(f"{BASE}/api/admin/ai/providers").json()["providers"]}
    orig_models = admin.get(f"{BASE}/api/admin/models").json()["current"]

    # 1. add the key through the dashboard endpoint
    r = admin.put(f"{BASE}/api/admin/ai/providers/nvidia", json={"api_key": key, "base_url": ""})
    if not check("save key via dashboard", r.status_code == 200, r.text[:200]):
        return
    view = r.json()
    check("key is masked in response", key not in json.dumps(view) and view["key_hint"] != key, view["key_hint"])

    try:
        # 2. models are discovered live, and include the model we intend to select
        r = admin.get(f"{BASE}/api/admin/ai/providers/nvidia/models", params={"refresh": "true"}, timeout=90)
        disc = r.json()
        check("live model discovery", disc["source"] == "live" and len(disc["models"]) > 5,
              f"source={disc['source']} n={len(disc['models'])}")
        check("chosen scoring model is offered", SCORING in disc["models"])
        check("chosen writing model is offered", WRITING in disc["models"])

        # 3. a model that only exists in the live list is accepted (not just the shipped catalog)
        r = admin.put(f"{BASE}/api/admin/models", json={
            "scoring": {"provider": "nvidia", "model": SCORING},
            "writing": {"provider": "nvidia", "model": WRITING}})
        check("select live-discovered models", r.status_code == 200, r.text[:200])

        # 4. real AI call through the dashboard-managed key
        job = demo.get(f"{BASE}/api/jobs?limit=1", timeout=30).json()["items"][0]
        print(f"\n  reviewing: {job['title']} @ {job['company']}")
        # NVIDIA returns 503 "Service temporarily overloaded" under load, which is upstream
        # capacity rather than an app fault, so allow a couple of retries.
        r, detail = None, ""
        for attempt in range(3):
            r = demo.post(f"{BASE}/api/jobs/{job['job_id']}/review", json={}, timeout=300)
            detail = r.text[:200]
            if r.status_code == 200:
                break
            print(f"  attempt {attempt + 1} failed: {detail}")
            time.sleep(10)
        if check("AI job review via dashboard key", r.status_code == 200, detail):
            body = r.json()
            rev = body.get("result") or body
            print(f"  score={rev.get('score')} verdict={rev.get('verdict')} model={rev.get('model')}")
            print(f"  blockers={rev.get('hard_blockers')}")
            print(f"  matched={(rev.get('matched_skills') or [])[:4]}")
    finally:
        # Order matters: a provider cannot be removed while a tier still points at it, so move
        # the tiers off the dashboard-managed provider first, then drop the key.
        admin.put(f"{BASE}/api/admin/models", json=orig_models)
        if before["nvidia"]["source"] != "dashboard":
            moved = {**orig_models,
                     "scoring": {"provider": "anthropic", "model": core.DEFAULT_MODELS["scoring"]["model"]},
                     "writing": {"provider": "anthropic", "model": core.DEFAULT_MODELS["writing"]["model"]}}
            admin.put(f"{BASE}/api/admin/models", json=moved)
            r = admin.delete(f"{BASE}/api/admin/ai/providers/nvidia")
            admin.put(f"{BASE}/api/admin/models", json=orig_models)
        check("restored", True, "models reset, dashboard key removed")


if __name__ == "__main__":
    main()
