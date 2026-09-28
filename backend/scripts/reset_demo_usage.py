"""Reset the seeded demo account's usage counters for the current period.

Manual verification runs (uploading CVs as the demo user) consume the free plan's single
CV-upload allowance, which then blocks the demo account from uploading at all.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core  # noqa: E402
from core import db  # noqa: E402


async def main():
    user = await db.users.find_one({"email": "demo@jobpilot.app"}, {"user_id": 1, "plan": 1})
    if not user:
        print("demo user not found")
        return
    uid = user["user_id"]
    await db.usage.update_one(
        {"user_id": uid, "period": core.period()},
        {"$set": {"reviews": 0, "tailors": 0, "parses": 0}},
        upsert=True,
    )
    print("demo usage reset ->", await core.usage_of(uid))

    # A failed parse must never have left a half-parsed file behind.
    stale = await db.files.count_documents({"user_id": uid, "is_deleted": False})
    print("demo stored files:", stale)


asyncio.run(main())
