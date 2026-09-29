"""Clear the local login lockout (dev convenience after running the suite repeatedly)."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core  # noqa: E402,F401
from core import db  # noqa: E402


async def main():
    r = await db.login_attempts.delete_many({})
    print(f"cleared {r.deleted_count} login_attempts row(s)")


asyncio.run(main())
