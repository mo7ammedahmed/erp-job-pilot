"""Drop Workable rows stored before the location-parsing fix.

Those rows have an empty location and a different fingerprint from the corrected rows for the
same posting, so fingerprint de-duplication cannot merge them. Every Workable posting now comes
back with a real city, so the empty ones are pure duplicates with no usable location data.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core  # noqa: E402,F401
from core import db, NOID  # noqa: E402


async def main():
    stale = await db.jobs.count_documents({"sources": "workable", "$or": [{"location": ""}, {"location": None}]})
    print(f"workable rows with no location: {stale}")
    if stale:
        res = await db.jobs.delete_many({"sources": "workable", "$or": [{"location": ""}, {"location": None}]})
        print(f"deleted {res.deleted_count}")

    total = await db.jobs.count_documents({})
    sa = await db.jobs.count_documents({"country": "SA"})
    riyadh = await db.jobs.count_documents({"city_key": "riyadh"})
    print(f"total={total}  saudi={sa}  riyadh={riyadh}")

    top = await db.jobs.aggregate([
        {"$match": {"country": "SA"}},
        {"$group": {"_id": "$company", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}}, {"$limit": 12},
    ]).to_list(12)
    print("\nSaudi jobs by employer:")
    for r in top:
        print(f"  {r['n']:>3}  {r['_id']}")


asyncio.run(main())
