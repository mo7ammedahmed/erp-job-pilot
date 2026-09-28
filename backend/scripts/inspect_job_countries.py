"""Inspect why fetched jobs are not being tagged with a country."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core  # noqa: E402,F401
from core import db, NOID  # noqa: E402


async def main():
    for src in ("workable", "smartrecruiters"):
        print(f"\n=== {src} ===")
        async for j in db.jobs.find({"sources": src}, NOID).limit(6):
            print(f"  title={j.get('title')!r}")
            print(f"    location={j.get('location')!r} city={j.get('city')!r} country={j.get('country')!r} remote={j.get('remote')!r}")
    print("\n=== distinct countries across all jobs ===")
    rows = await db.jobs.aggregate([{"$group": {"_id": "$country", "n": {"$sum": 1}}}, {"$sort": {"n": -1}}]).to_list(20)
    for r in rows:
        print(f"  {str(r['_id']):<8} {r['n']}")


asyncio.run(main())
