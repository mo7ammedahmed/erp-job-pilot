"""One-off maintenance: drop stale accounts and report DB state."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import db  # noqa: E402

STALE = ["admin@jobpilot.local"]


async def main():
    for email in STALE:
        u = await db.users.find_one({"email": email}, {"_id": 0, "user_id": 1, "role": 1})
        if u:
            await db.users.delete_one({"email": email})
            await db.workspaces.delete_many({"owner_id": u["user_id"]})
            print(f"removed stale user {email} ({u['role']})")

    for prefix in ("test_", "trial_"):
        n = await db.users.count_documents({"email": {"$regex": f"^{prefix}"}})
        print(f"throwaway users matching {prefix}*: {n}")

    for coll in ("users", "jobs", "applications", "cv_versions", "audit_logs", "reminders", "ai_logs", "sources", "plans"):
        print(f"{coll}: {await db[coll].count_documents({})}")


asyncio.run(main())
