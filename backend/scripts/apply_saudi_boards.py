"""Apply the verified Saudi ATS boards to the live database and run every enabled source.

Board tokens live in db.sources, not only in DEFAULT_SOURCES, so an existing database has to be
updated too. Only boards that were confirmed to return jobs are written.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core  # noqa: E402,F401  -- loads backend/.env
import sources as S  # noqa: E402
from core import db, NOID  # noqa: E402

# Confirmed working against the live public ATS APIs (see find_saudi_boards.py).
VERIFIED = {
    "greenhouse": ["careem", "tamara"],
    "workable": ["foodics", "salla", "lucidya", "fetchr"],
    "smartrecruiters": ["namshi"],
}


async def main():
    for sid, boards in VERIFIED.items():
        cur = await db.sources.find_one({"source_id": sid}, NOID)
        if not cur:
            print(f"{sid}: not in database, skipped")
            continue
        # Replace rather than merge, so a token left behind by testing cannot persist.
        merged = list(boards)
        await db.sources.update_one({"source_id": sid}, {"$set": {"config": {"boards": merged}}})
        print(f"{sid}: boards -> {merged}")

    print("\nrunning all enabled sources ...")
    queries = await S._queries()
    async for src in db.sources.find({"enabled": True}, NOID):
        n = await S.run_source(src, queries)
        after = await db.sources.find_one({"source_id": src["source_id"]}, NOID)
        print(f"  {src['source_id']:<18} status={after.get('status'):<10} fetched={after.get('last_count')} new={n}"
              + (f"  error={str(after.get('last_error'))[:80]}" if after.get("last_error") else ""))

    total = await db.jobs.count_documents({})
    sa = await db.jobs.count_documents({"country": "SA"})
    print(f"\ntotal jobs: {total} | Saudi: {sa}")
    top = await db.jobs.aggregate([
        {"$match": {"country": "SA"}},
        {"$group": {"_id": "$company", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}}, {"$limit": 15},
    ]).to_list(15)
    print("\nSaudi jobs by employer:")
    for r in top:
        print(f"  {r['n']:>3}  {r['_id']}")


asyncio.run(main())
