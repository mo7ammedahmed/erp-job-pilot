"""Recompute city_key for stored jobs after the city list changed.

The city list is now keyed by the canonical Saudi name, so older rows that were tagged
"mecca" or "medina" would no longer match a city filter. Recomputes city_key (and country where
the new city aliases make it detectable) for every job from its stored location string.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core  # noqa: E402,F401
import sources as S  # noqa: E402
from core import db, NOID  # noqa: E402


async def main():
    before = await db.jobs.aggregate([{"$group": {"_id": "$city_key", "n": {"$sum": 1}}},
                                     {"$sort": {"n": -1}}]).to_list(50)
    print("city_key before:")
    for r in before:
        if r["_id"]:
            print(f"   {str(r['_id']):<24} {r['n']}")

    changed = rekeyed = reflagged = 0
    async for j in db.jobs.find({}, NOID):
        loc = j.get("location") or ""
        # Single source of truth, shared with mk(), so a rule added there applies to stored rows too.
        city, new_key, new_country = S.resolve_location(loc, j.get("title") or "")
        sets = {}
        if new_key != (j.get("city_key") or ""):
            sets["city_key"] = new_key
            changed += 1
        if new_country and new_country != j.get("country"):
            sets["country"] = new_country
            rekeyed += 1
        if sets:
            await db.jobs.update_one({"job_id": j["job_id"]}, {"$set": sets})

    print(f"\ncity_key changed on {changed} jobs; country set on {rekeyed} jobs")
    sa = await db.jobs.count_documents({"country": "SA"})
    riyadh = await db.jobs.count_documents({"city_key": "riyadh"})
    jeddah = await db.jobs.count_documents({"city_key": "jeddah"})
    print(f"Saudi={sa}  riyadh={riyadh}  jeddah={jeddah}")
    after = await db.jobs.aggregate([{"$match": {"country": "SA"}},
                                     {"$group": {"_id": "$city_key", "n": {"$sum": 1}}},
                                     {"$sort": {"n": -1}}, {"$limit": 20}]).to_list(20)
    print("Saudi city_key distribution:")
    for r in after:
        print(f"   {str(r['_id']):<24} {r['n']}")


asyncio.run(main())
