"""Direct test of upload_cv when AI parsing raises.

The HTTP-level outage simulation is blocked by design (the API refuses to point tiers at a
provider with no key), so this exercises the handler itself with llm_json stubbed to fail --
which is exactly the condition the fix is about.
"""
import asyncio
import io
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core  # noqa: E402,F401  -- loads backend/.env
import r_cv  # noqa: E402
from fastapi import UploadFile  # noqa: E402
from docx import Document  # noqa: E402

DOCX_CT = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def check(label, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f" :: {detail}" if detail else ""))
    return ok


def make_docx_bytes():
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


async def main():
    email = "outage_test@jobpilot.app"
    await core.db.users.delete_many({"email": email})
    await core.db.users.delete_many({"email": "throwaway_outage@jobpilot.app"})
    user = await core.db.users.find_one({"email": "throwaway_outage@jobpilot.app"})
    if not user:
        doc = r_cv.new_user_doc if hasattr(r_cv, "new_user_doc") else None
        from r_auth import new_user_doc, create_user
        await create_user(new_user_doc("throwaway_outage@jobpilot.app", "Outage Tester", onboarded=True))
        user = await core.db.users.find_one({"email": "throwaway_outage@jobpilot.app"}, core.NOID)

    before = await core.usage_of(user["user_id"])

    # force the AI parse to fail
    original = r_cv.llm_json

    async def boom(*a, **k):
        raise RuntimeError('503: {"error":{"message":"Service temporarily overloaded"}}')

    r_cv.llm_json = boom
    try:
        up = UploadFile(file=io.BytesIO(make_docx_bytes()), filename="cv.docx", headers={"content-type": DOCX_CT})
        result = await r_cv.upload_cv(up, user=user)
    finally:
        r_cv.llm_json = original

    ok = check("upload_cv returns normally on AI failure", True, str(result.get("file_id")))
    ok &= check("file_id is present", bool(result.get("file_id")), str(result.get("file_id")) or "MISSING")
    ok &= check("parsed is None, not faked", result.get("parsed") is None)
    check("parse_error is actionable", bool(result.get("parse_error")), str(result.get("parse_error"))[:170])

    after = await core.usage_of(user["user_id"])
    check("usage is not charged for a failed parse", after["parses"] == before["parses"],
          f"parses {before['parses']} -> {after['parses']}")

    stored = await core.db.files.find_one({"file_id": result["file_id"]}, core.NOID)
    check("file row was persisted", bool(stored), stored["filename"] if stored else "MISSING")
    try:
        data, _ = await core.get_file(result["file_id"], user["user_id"])
        check("file bytes round-trip from storage", len(data) > 1000, f"{len(data)} bytes")
    except Exception as e:
        check("file bytes round-trip from storage", False, str(e)[:160])

    # audit records that the upload happened even though parsing did not
    log = await core.db.audit_logs.find_one({"user_id": user["user_id"], "action": "cv_uploaded"}, core.NOID)
    check("audit records parsed=false", bool(log) and log["meta"].get("parsed") is False,
          str(log["meta"]) if log else "MISSING")

    await core.db.users.delete_many({"user_id": user["user_id"]})
    await core.db.workspaces.delete_many({"owner_id": user["user_id"]})
    await core.db.files.delete_many({"user_id": user["user_id"]})
    print("\nRESULT:", "PASS" if ok else "FAIL")


asyncio.run(main())
