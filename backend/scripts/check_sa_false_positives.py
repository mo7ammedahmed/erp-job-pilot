"""Show the Saudi-tagged jobs that do not look like Saudi postings, to catch false positives."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core  # noqa: E402,F401
from core import db, NOID  # noqa: E402

# Employers that are genuinely Saudi-based, so a job from them is expected to be tagged SA.
KNOWN_SAUDI = {"salla", "lucidya", "foodics", "tamara", "careem", "namshi", "fetchr"}


async def main():
    async for j in db.jobs.find({"country": "SA"}, NOID):
        if (j.get("company") or "").strip().lower() in KNOWN_SAUDI:
            continue
        print(f"company={j.get('company')!r} title={j.get('title')!r}")
        print(f"  location={j.get('location')!r} city_key={j.get('city_key')!r} source={j.get('sources')}")


asyncio.run(main())
