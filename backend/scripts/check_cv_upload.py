"""Reproduce the CV upload path exactly as the UI calls it, and report the precise failure."""
import asyncio
import io
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core  # noqa: E402,F401  -- loads backend/.env
import requests  # noqa: E402
from docx import Document  # noqa: E402

BASE = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8000").rstrip("/")


def make_docx():
    d = Document()
    d.add_heading("Layla Al-Sayed", level=1)
    d.add_paragraph("Senior Data Analyst · Riyadh, Saudi Arabia · layla@example.com")
    d.add_paragraph("Data analyst with 6 years of experience across retail and logistics in Saudi Arabia.")
    d.add_paragraph("Experience")
    d.add_paragraph("Senior Data Analyst, Almarai Company, 2022-03 to Present")
    d.add_paragraph("Built the demand forecast used by 14 distribution centres, cutting stock-outs by 18%.")
    d.add_paragraph("Data Analyst, Jarir Holding, 2019-06 to 2022-02")
    d.add_paragraph("Owned the SQL and Power BI layer behind dashboards used by 90 managers.")
    d.add_paragraph("Education: Bachelor of Statistics, King Saud University, 2014 to 2018")
    d.add_paragraph("Skills: SQL, Python, Power BI, Tableau, dbt, Snowflake, forecasting, A/B testing")
    buf = io.BytesIO()
    d.save(buf)
    buf.seek(0)
    return buf


def main():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": os.environ["TEST_USER_EMAIL"],
                                              "password": os.environ["TEST_USER_PASSWORD"]}, timeout=30)
    r.raise_for_status()
    print("logged in as demo")

    # what the app is currently configured to use
    cfg = s.get(f"{BASE}/api/admin/models") if False else None

    for name, blob, ctype in [("cv.docx", make_docx().read(),
                               "application/vnd.openxmlformats-officedocument.wordprocessingml.document")]:
        r = s.post(f"{BASE}/api/cv/upload", files={"file": (name, blob, ctype)}, timeout=300)
        print(f"\nPOST /api/cv/upload ({name}, {len(blob)} bytes) -> {r.status_code}")
        print("body:", r.text[:600])

    # also confirm the storage backend the upload would write to
    print("\nLOCAL_STORAGE =", core.LOCAL_STORAGE, "| dir =", core.LOCAL_STORAGE_DIR)

    # This upload consumed the demo account's single free-plan CV allowance, which would then
    # block the demo user from uploading at all. Give the allowance back.
    asyncio.run(reset_demo_usage())


async def reset_demo_usage():
    import asyncio
    from core import db
    user = await db.users.find_one({"email": os.environ["TEST_USER_EMAIL"]}, {"user_id": 1})
    if not user:
        return
    await db.usage.update_one(
        {"user_id": user["user_id"], "period": core.period()},
        {"$set": {"reviews": 0, "tailors": 0, "parses": 0}},
        upsert=True,
    )
    print("\ndemo usage reset ->", await core.usage_of(user["user_id"]))


if __name__ == "__main__":
    main()
