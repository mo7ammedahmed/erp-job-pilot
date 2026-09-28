"""Remove duplicate jobs left behind when a fetzer's location parsing was fixed.

Before the fix, Workable rows were stored with an empty city, so their fingerprint
(title|company|city) differed from the corrected rows and both survived. Keep the newest
document per fingerprint and drop the rest, preferring the one with a real location.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core  # noqa: E402,F401
from core import db, NOID  # noqa: E402


async def main():
    removed = 0
    seen = {}
    # newest first, so the survivor is the most recently fetched
    async for j in db.jobs.find({}, NOID).sort("fetched_at", -1):
        fp = j.get("fingerprint")
        if not fp:
            continue
        if fp in seen:
            await db.jobs.delete_one({"job_id": j["job_id"]})
            removed += 1
        else:
            seen[fp] = j["job_id"]
    print(f"removed {removed} duplicate job rows")

    total = await db.jobs.count_documents({})
    sa = await db.jobs.count_documents({"country": "SA"})
    riyadh = await db.jobs.count_documents({"city_key": "riyadh"})
    none = await db.jobs.count_documents({"country": None})
    print(f"total={total}  saudi={sa}  riyadh={riyadh}  untagged={none}")


asyncio.run(main())
