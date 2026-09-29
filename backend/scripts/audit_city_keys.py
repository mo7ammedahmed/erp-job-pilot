"""Report stored city_keys that are not canonical, to find transliteration gaps in the alias table.

Every slug here is a city the data actually contains but the alias table does not know, so its jobs
are invisible to that city's filter. Fixing them means adding the real-world spelling as an alias
rather than renaming keys in the database.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core  # noqa: E402,F401
from core import db  # noqa: E402
import sources as S  # noqa: E402


async def main():
    known = set(S.CITY_INDEX)
    rows = await db.jobs.aggregate([
        {"$match": {"city_key": {"$nin": ["", None]}}},
        {"$group": {"_id": {"key": "$city_key", "city": "$city", "country": "$country"}, "n": {"$sum": 1}}},
        {"$sort": {"n": -1}}, {"$limit": 500},
    ]).to_list(500)

    print("stored city_keys that are not canonical:")
    unknown = 0
    for r in rows:
        k = r["_id"]["key"]
        if k not in known:
            unknown += 1
            print(f"   key={k:<24} city={str(r['_id']['city'])[:32]:<32} country={str(r['_id']['country']):<5} n={r['n']}")
    print(f"\n{unknown} distinct non-canonical keys")

    # Which canonical Saudi cities currently have no jobs at all.
    empty = [(k, S.CITY_INDEX[k][0] if S.CITY_INDEX[k] else k) for k in sorted(S.SA_CITY_KEYS)]
    counts = {r["_id"]["key"]: r["n"] for r in rows}
    zero = [k for k, _ in empty if counts.get(k, 0) == 0]
    print(f"\nSaudi cities with zero stored jobs ({len(zero)} of {len(empty)}):")
    for k in zero:
        print(f"   {k}")


asyncio.run(main())
