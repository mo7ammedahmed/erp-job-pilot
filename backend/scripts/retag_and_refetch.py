"""Re-tag already-stored jobs and re-fetch every source.

Fixing the Workable location bug only affects newly inserted documents, so existing jobs keep
their empty country. This recomputes country/city_key for stored jobs and re-runs the sources.
"""
import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core  # noqa: E402,F401
import sources as S  # noqa: E402
from core import db, NOID  # noqa: E402


async def retag():
    fixed = 0
    async for j in db.jobs.find({"country": None}, NOID):
        loc = j.get("location") or ""
        title = j.get("title") or ""
        c = S.detect_country(loc) or S.detect_country(f"{loc} {title}")
        if not c:
            continue
        city = (loc.split(",")[0] if loc else "").strip()
        await db.jobs.update_one({"job_id": j["job_id"]},
                                 {"$set": {"country": c, "city_key": S.normalize_city(city) or j.get("city_key")}})
        fixed += 1
    print(f"re-tagged {fixed} previously untagged jobs")


async def main():
    await retag()
    print("\nrunning all enabled sources ...")
    queries = await S._queries()
    async for src in db.sources.find({"enabled": True}, NOID):
        n = await S.run_source(src, queries)
        after = await db.sources.find_one({"source_id": src["source_id"]}, NOID)
        print(f"  {src['source_id']:<18} status={after.get('status'):<10} fetched={after.get('last_count')} new={n}")

    total = await db.jobs.count_documents({})
    sa = await db.jobs.count_documents({"country": "SA"})
    none = await db.jobs.count_documents({"country": None})
    print(f"\ntotal={total}  saudi={sa}  untagged={none}")
    top = await db.jobs.aggregate([
        {"$match": {"country": "SA"}},
        {"$group": {"_id": "$company", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}}, {"$limit": 20},
    ]).to_list(20)
    print("\nSaudi jobs by employer:")
    for r in top:
        print(f"  {r['n']:>3}  {r['_id']}")
    riyadh = await db.jobs.count_documents({"city_key": "riyadh"})
    print(f"\nRiyadh jobs: {riyadh}")


asyncio.run(main())
