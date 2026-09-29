"""Ingest the newly added ATS boards through the production pipeline and verify what landed.

Runs the same run_source/upsert_jobs path the scheduler uses, so this exercises real code rather
than a parallel copy of it, then reports the resulting coverage per board and city.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core  # noqa: E402,F401
from core import db  # noqa: E402
from sources import run_source  # noqa: E402

TARGETS = ["greenhouse", "lever", "ashby", "workable", "smartrecruiters"]


async def main():
    queries = [{"keywords": "", "country": "SA", "city": ""}]
    for sid in TARGETS:
        src = await db.sources.find_one({"source_id": sid})
        n = await run_source(src, queries)
        doc = await db.sources.find_one({"source_id": sid}, {"_id": 0, "last_count": 1, "last_new": 1, "status": 1, "last_error": 1})
        print(f"{sid:<16} fetched={doc.get('last_count'):<5} new={doc.get('last_new'):<5} status={doc.get('status')} {doc.get('last_error') or ''}", flush=True)

    print("\n=== Saudi jobs per ATS board in the database ===")
    rows = await db.jobs.aggregate([
        {"$match": {"ats_board": {"$exists": True}}},
        {"$group": {"_id": {"ats": "$ats", "board": "$ats_board"}, "n": {"$sum": 1}, "sa": {"$sum": {"$cond": [{"$eq": ["$country", "SA"]}, 1, 0]}}}},
        {"$sort": {"sa": -1, "n": -1}},
    ]).to_list(200)
    for r in rows:
        print(f"  {r['_id'].get('ats','?'):<15} {str(r['_id'].get('board')):<34} total={r['n']:<5} SA={r['sa']}")

    print("\n=== city_key coverage for the new Saudi jobs ===")
    rows = await db.jobs.aggregate([
        {"$match": {"country": "SA"}},
        {"$group": {"_id": "$city_key", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}}, {"$limit": 25},
    ]).to_list(25)
    for r in rows:
        print(f"  {str(r['_id']):<28} {r['n']}")

    sa = await db.jobs.count_documents({"country": "SA"})
    print(f"\ntotal jobs tagged SA: {sa}")


asyncio.run(main())
