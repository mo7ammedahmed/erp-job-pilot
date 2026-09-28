"""Check city filtering directly against the API for a set of cities."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core  # noqa: E402,F401
import requests  # noqa: E402

import sources as S  # noqa: E402

BASE = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8000").rstrip("/")
s = requests.Session()
s.post(f"{BASE}/api/auth/login", json={"email": os.environ["TEST_USER_EMAIL"],
                                       "password": os.environ["TEST_USER_PASSWORD"]}, timeout=30).raise_for_status()

for city in ["Riyadh", "Jeddah", "Mecca", "Makkah", "Dammam", "Khobar", "Taif", "Abha", "Buraidah", "Tabuk"]:
    key = S.normalize_city(city)
    r = s.get(f"{BASE}/api/jobs", params={"country": "SA", "city": city, "limit": 50}, timeout=60)
    total = r.json().get("total", 0)
    flag = "" if total else "   <-- no match"
    print(f"  {city:<12} -> city_key {key:<12} total={total}{flag}")

print("\nSaudi jobs with no recognised city:")
r = s.get(f"{BASE}/api/jobs", params={"country": "SA", "limit": 50}, timeout=60)
for j in r.json().get("items", []):
    if not j.get("city"):
        print(f"   city={j.get('city')!r} location={j.get('location')!r} title={j.get('title')[:40]!r}")
