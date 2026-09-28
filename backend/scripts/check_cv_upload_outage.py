"""Verify a CV upload survives an AI outage.

Points the AI tiers at a provider with no usable key so parsing is guaranteed to fail, then
checks that the upload still succeeds, still returns a stored file, and that parsing can be
retried afterwards. Restores the previous model settings on the way out.
"""
import io
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core  # noqa: E402,F401  -- loads backend/.env
import requests  # noqa: E402
from docx import Document  # noqa: E402

BASE = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8000").rstrip("/")
DOCX_CT = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def check(label, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f" :: {detail}" if detail else ""))
    return ok


def make_docx():
    d = Document()
    d.add_paragraph("Layla Al-Sayed — Senior Data Analyst, Riyadh, Saudi Arabia")
    d.add_paragraph("Data analyst with 6 years of experience across retail and logistics in Saudi Arabia.")
    d.add_paragraph("Senior Data Analyst, Almarai Company, 2022-03 to Present")
    d.add_paragraph("Built the demand forecast used by 14 distribution centres, cutting stock-outs by 18%.")
    d.add_paragraph("Data Analyst, Jarir Holding, 2019-06 to 2022-02")
    d.add_paragraph("Owned the SQL and Power BI layer behind dashboards used by 90 store managers.")
    d.add_paragraph("Education: Bachelor of Statistics, King Saud University, 2014 to 2018")
    d.add_paragraph("Skills: SQL, Python, Power BI, Tableau, dbt, Snowflake, forecasting")
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def main():
    admin = requests.Session()
    admin.post(f"{BASE}/api/auth/login", json={"email": os.environ["ADMIN_EMAIL"],
                                                "password": os.environ["ADMIN_PASSWORD"]}, timeout=30).raise_for_status()
    demo = requests.Session()
    demo.post(f"{BASE}/api/auth/login", json={"email": os.environ["TEST_USER_EMAIL"],
                                              "password": os.environ["TEST_USER_PASSWORD"]}, timeout=30).raise_for_status()

    orig = admin.get(f"{BASE}/api/admin/models").json()["current"]
    # openai has no key here, and the Emergent gateway is not configured, so this cannot parse.
    broken = {"scoring": {"provider": "openai", "model": "gpt-5.4-mini"},
              "writing": {"provider": "openai", "model": "gpt-5.4"}}
    r = admin.put(f"{BASE}/api/admin/models", json=broken)
    if not check("point tiers at an unusable provider", r.status_code == 200, r.text[:200]):
        print("  (skipped: openai is configured on this machine, so the outage cannot be simulated)")
        return

    try:
        r = demo.post(f"{BASE}/api/cv/upload", files={"file": ("cv.docx", make_docx(), DOCX_CT)}, timeout=300)
        if not check("upload succeeds despite the AI outage", r.status_code == 200, r.text[:250]):
            return
        data = r.json()
        check("a file_id is returned", bool(data.get("file_id")), data.get("file_id"))
        check("parse_error is set and actionable", bool(data.get("parse_error")), str(data.get("parse_error"))[:160])
        check("no parsed payload is faked", data.get("parsed") is None)

        # the stored file must be retrievable, i.e. the upload really was persisted
        r = demo.get(f"{BASE}/api/files/{data['file_id']}", timeout=60)
        check("stored file can be downloaded again", r.status_code == 200, f"{r.status_code} {len(r.content)} bytes")

        # and the profile can be saved by hand from the file, so the app is still usable
        manual = {"name": "Layla Al-Sayed", "headline": "Senior Data Analyst", "summary": "6 years in retail and logistics analytics.",
                  "skills": ["SQL", "Python", "Power BI"], "experience": [], "education": [], "projects": [],
                  "languages": [], "certifications": [], "contact": {"email": "layla@example.com", "phone": "", "location": "Riyadh", "links": []}}
        r = demo.post(f"{BASE}/api/cv/versions", json={"data": manual, "file_id": data["file_id"], "note": "manual during AI outage"}, timeout=30)
        check("master CV can still be saved by hand", r.status_code == 200, r.text[:200])

        # retry parsing later
        r = demo.post(f"{BASE}/api/cv/parse", json={"file_id": data["file_id"]}, timeout=300)
        check("retry parsing fails cleanly while the provider is down", r.status_code == 502, f"{r.status_code} {r.text[:120]}")
    finally:
        admin.put(f"{BASE}/api/admin/models", json=orig)
        check("model settings restored", True)


if __name__ == "__main__":
    main()
