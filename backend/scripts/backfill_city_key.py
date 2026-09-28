"""
One-time backfill: sets `city_key` on jobs stored before the location-normalization
update (see sources.py: normalize_city / CITY_INDEX). Jobs picked up again by a
scheduled source fetch heal themselves automatically (see upsert_jobs); this script
covers everything else — manual jobs, and jobs no longer returned by their source.

Run once from backend/:
    python -m scripts.backfill_city_key
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import db  # noqa: E402
from sources import normalize_city  # noqa: E402


async def main():
    n = 0
    async for j in db.jobs.find({"city_key": {"$exists": False}}, {"_id": 1, "city": 1}):
        await db.jobs.update_one({"_id": j["_id"]}, {"$set": {"city_key": normalize_city(j.get("city"))}})
        n += 1
    print(f"Backfilled city_key on {n} job(s).")


if __name__ == "__main__":
    asyncio.run(main())
