"""Verify Saudi job coverage through the public API, exactly as the UI calls it."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core  # noqa: E402,F401
import requests  # noqa: E402

BASE = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8000").rstrip("/")
ok = True


def check(label, cond, detail=""):
    global ok
    ok = ok and bool(cond)
    print(f"[{'PASS' if cond else 'FAIL'}] {label}" + (f" :: {detail}" if detail else ""))


def main():
    s = requests.Session()
    s.post(f"{BASE}/api/auth/login", json={"email": os.environ["TEST_USER_EMAIL"],
                                           "password": os.environ["TEST_USER_PASSWORD"]}, timeout=30).raise_for_status()

    r = s.get(f"{BASE}/api/jobs", params={"country": "SA", "limit": 50}, timeout=60)
    check("GET /jobs?country=SA returns 200", r.status_code == 200, r.text[:120])
    body = r.json()
    jobs = body.get("jobs") or body.get("items") or []
    check("Saudi jobs are returned", len(jobs) > 0, f"{len(jobs)} jobs")
    check("total reports the Saudi count", (body.get("total") or 0) >= len(jobs), f"total={body.get('total')}")

    bad = [j for j in jobs if j.get("country") != "SA"]
    check("every returned job is tagged SA", not bad, f"{len(bad)} mismatched")

    with_loc = [j for j in jobs if j.get("city") or j.get("location")]
    check("jobs carry a usable city", len(with_loc) >= len(jobs) * 0.8, f"{len(with_loc)}/{len(jobs)}")

    r = s.get(f"{BASE}/api/jobs", params={"country": "SA", "city": "Riyadh", "limit": 50}, timeout=60)
    riyadh = r.json().get("jobs") or r.json().get("items") or []
    check("Riyadh filter works", r.status_code == 200 and len(riyadh) > 0, f"{len(riyadh)} Riyadh jobs")

    print("\nSaudi employers in the feed:")
    for name, n in sorted({j.get("company"): sum(1 for x in jobs if x.get("company") == j.get("company"))
                           for j in jobs}.items(), key=lambda kv: -kv[1]):
        if name:
            print(f"   {n:>3}  {name}")

    print("\nRESULT:", "PASS" if ok else "FAIL")


main()
