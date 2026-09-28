"""Recompute country for every stored job after a detection change.

detect_country changed from substring to word-boundary matching, so jobs that were tagged by a
spurious substring need correcting. Also fills in country for anything still untagged.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core  # noqa: E402,F401
import sources as S  # noqa: E402
from core import db, NOID  # noqa: E402


async def main():
    changed = filled = 0
    async for j in db.jobs.find({}, NOID):
        loc, title = j.get("location") or "", j.get("title") or ""
        city = (loc.split(",")[0] if loc else "").strip()
        new = S.detect_country(loc) or S.detect_country(f"{city} {title}")
        old = j.get("country")
        if new == old:
            continue
        sets = {"city_key": S.normalize_city(city) or j.get("city_key")}
        if new is None and old is not None:
            sets["country"] = None
            changed += 1
        elif new is not None:
            sets["country"] = new
            changed += 1
            if old is None:
                filled += 1
        await db.jobs.update_one({"job_id": j["job_id"]}, {"$set": sets})
    print(f"country changed on {changed} jobs ({filled} newly identified)")

    total = await db.jobs.count_documents({})
    sa = await db.jobs.count_documents({"country": "SA"})
    riyadh = await db.jobs.count_documents({"city_key": "riyadh"})
    none = await db.jobs.count_documents({"country": None})
    print(f"total={total}  saudi={sa}  riyadh={riyadh}  untagged={none}")


asyncio.run(main())
