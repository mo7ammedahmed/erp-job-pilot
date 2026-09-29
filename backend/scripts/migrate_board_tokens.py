"""Add the verified ATS board tokens to source configs on databases seeded before this change.

server.py seeds sources with $setOnInsert, so DEFAULT_SOURCES only reaches new installs. Existing
databases keep whatever boards they were created with, which is why the previous board additions
needed a migration too.

Boards are unioned, never replaced: an admin may have added or removed boards by hand through
Admin -> Source health, and this must not undo that. Pass --replace to force the defaults instead.

    python scripts/migrate_board_tokens.py            # add missing boards
    python scripts/migrate_board_tokens.py --replace  # reset to the validated defaults
    python scripts/migrate_board_tokens.py --dry-run  # show what would change
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core  # noqa: E402,F401
from core import db  # noqa: E402
from sources import DEFAULT_SOURCES  # noqa: E402

ATS_SOURCE_IDS = {"greenhouse", "lever", "ashby", "workable", "smartrecruiters"}


async def main():
    dry = "--dry-run" in sys.argv
    replace = "--replace" in sys.argv
    total_added = 0

    for s in DEFAULT_SOURCES:
        if s["source_id"] not in ATS_SOURCE_IDS:
            continue
        sid = s["source_id"]
        defaults = list(s["config"].get("boards", []))
        doc = await db.sources.find_one({"source_id": sid}, {"_id": 0, "source_id": 1, "config": 1})

        if not doc:
            print(f"  {sid:<16} not present yet; will be seeded with defaults by server startup")
            continue

        current = list((doc.get("config") or {}).get("boards", []))
        merged = defaults if replace else current + [b for b in defaults if b not in current]
        added = [b for b in merged if b not in current]

        if not added and not replace:
            print(f"  {sid:<16} up to date ({len(current)} boards)")
            continue

        total_added += len(added)
        detail = f"replace with {len(defaults)}" if replace else f"add {added}"
        print(f"  {sid:<16} {detail}")
        if not dry:
            existing_cfg = doc.get("config") or {}
            await db.sources.update_one({"source_id": sid}, {"$set": {"config": {**existing_cfg, "boards": merged}}})

    verb = "would add" if dry else "added"
    print(f"\n{verb} {total_added} board tokens across {len(ATS_SOURCE_IDS)} ATS sources")


asyncio.run(main())
