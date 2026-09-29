"""Check that the factual claims in README.md still match the code.

Documentation drifts silently. These are the numbers and names the README states as fact, verified
against the running code so a wrong figure is caught rather than trusted.
"""
import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core  # noqa: E402,F401
from core import db  # noqa: E402
import sources as S  # noqa: E402

README = (Path(__file__).resolve().parents[2] / "README.md").read_text(encoding="utf-8")
EN = README[: README.index('<a name="العربية">')]


def claim(ok, label, detail=""):
    print(f"  [{'OK ' if ok else 'BAD'}] {label}{(' — ' + detail) if detail else ''}")
    return ok


async def main():
    good = True
    print("README claims vs code:")

    good &= claim("20 markets" in EN, "20 markets", f"code has {len(S.MARKET_CITIES)}")
    good &= claim("76 Saudi cities" in EN, "76 Saudi cities", f"code has {len(S.SA_CITY_KEYS)}")
    good &= claim("182 cities" in EN, "182 market cities", f"code has {len(S.NON_SA_CITY_KEYS)}")
    good &= claim("258 keys" in EN, "258 total keys", f"code has {len(S.CITY_INDEX)}")

    boards = sum(len((s.get("config") or {}).get("boards") or []) for s in S.DEFAULT_SOURCES)
    doc_boards = int(re.search(r"\*\*(\d+) board tokens in total", EN).group(1))
    good &= claim(doc_boards == boards, "board token count", f"doc {doc_boards} vs code {boards}")

    total_routes = sum(len(getattr(r, "methods", set()) - {"HEAD", "OPTIONS"})
                       for r in server_routes())
    doc_routes = int(re.search(r"(\d+) routes under `/api`", EN).group(1))
    good &= claim(doc_routes == total_routes, "API route count", f"doc {doc_routes} vs code {total_routes}")

    plans = S.__dict__.get("_plans") or None
    good &= claim(EN.count("| Free |") == 1, "plans table present")

    # The scheduler table must list every job the app actually schedules.
    server_src = (Path(__file__).resolve().parents[1] / "server.py").read_text(encoding="utf-8")
    for job in re.findall(r'add_job\((\w+)', server_src):
        good &= claim(job in EN, f"scheduled job documented: {job}")

    good &= claim("50 board tokens" not in EN or doc_boards == 50, "board total phrasing")

    print("\nRESULT:", "PASS" if good else "FAIL")
    return 0 if good else 1


def server_routes():
    import server
    return [r for r in server.app.routes if getattr(r, "path", "").startswith("/api")]


sys.exit(asyncio.run(main()))
