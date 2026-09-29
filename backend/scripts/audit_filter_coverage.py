"""Quantify how much of the corpus the country and city filters can actually reach.

A stored job only appears under a country when it was tagged, and only under a city when its key is
canonical. This measures both gaps, split by market, so the size of the blind spot is a number
rather than an impression.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core  # noqa: E402,F401
from core import db  # noqa: E402
import sources as S  # noqa: E402


async def main():
    total = await db.jobs.count_documents({})
    print(f"total stored jobs: {total}\n")

    print("=== country tagging ===")
    rows = await db.jobs.aggregate([{"$group": {"_id": "$country", "n": {"$sum": 1}}},
                                    {"$sort": {"n": -1}}]).to_list(40)
    untagged = next((r["n"] for r in rows if r["_id"] in (None, "")), 0)
    for r in rows[:18]:
        print(f"   {str(r['_id']):<6} {r['n']}")
    print(f"\n   untagged: {untagged}  ({untagged * 100 // max(total,1)}% of corpus -> invisible to every country filter)")

    known = set(S.CITY_INDEX)
    print("\n=== city key reachability ===")
    noncanon = await db.jobs.count_documents({"city_key": {"$nin": list(known) + ["", None]}})
    blank = await db.jobs.count_documents({"city_key": {"$in": ["", None]}})
    canonical = total - noncanon - blank
    print(f"   canonical city key : {canonical}")
    print(f"   non-canonical key  : {noncanon}  (real city, spelling not in the alias table)")
    print(f"   blank city key     : {blank}")

    # Untagged jobs that nonetheless sit in a city we do know: the highest-value fix, because the
    # country is recoverable from the city key without touching the source data.
    recoverable = await db.jobs.aggregate([
        {"$match": {"country": {"$in": [None, ""]}}},
        {"$group": {"_id": "$city_key", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}}, {"$limit": 100},
    ]).to_list(100)
    by_cc = {}
    for r in recoverable:
        cc = S.CITY_KEY_COUNTRY.get(r["_id"]) or ("SA" if r["_id"] in S.SA_CITY_KEYS else None)
        if cc:
            by_cc[cc] = by_cc.get(cc, 0) + r["n"]
    total_rec = sum(by_cc.values())
    print(f"\n=== untagged jobs recoverable from their own city key: {total_rec} ===")
    for cc, n in sorted(by_cc.items(), key=lambda kv: -kv[1])[:15]:
        print(f"   {cc}  +{n}")


asyncio.run(main())
