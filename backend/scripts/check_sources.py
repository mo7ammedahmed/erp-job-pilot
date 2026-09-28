"""Report the live status of every configured job source."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core  # noqa: E402,F401  -- loads backend/.env
from core import db, NOID  # noqa: E402


async def main():
    rows = []
    async for s in db.sources.find({}, NOID):
        rows.append(s)
    rows.sort(key=lambda r: r.get("source_id", ""))
    for s in rows:
        cfg = s.get("config") or {}
        boards = cfg.get("boards")
        print(f"{s.get('source_id'):<18} enabled={str(s.get('enabled')):<5} status={str(s.get('status')):<14} "
              f"count={s.get('last_count')} new={s.get('last_new')} boards={boards if boards is not None else '-'}")
        if s.get("last_error"):
            print(f"    error: {s['last_error'][:160]}")

    total = await db.jobs.count_documents({})
    sa = await db.jobs.count_documents({"country": "SA"})
    print(f"\ntotal jobs: {total} | Saudi: {sa}")


asyncio.run(main())
