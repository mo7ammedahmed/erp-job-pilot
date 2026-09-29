"""Splice the generated market data into frontend/src/lib/constants.js.

Replaces the non-Saudi market entries between "  AE:" and the closing "};" of MARKETS, so the
frontend city picker offers exactly the cities the backend can match. Idempotent: re-running
replaces the same region again rather than appending a second copy.
"""
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
FRONTEND = BACKEND.parent / "frontend" / "src" / "lib" / "constants.js"

sys.path.insert(0, str(BACKEND))
import sources as S  # noqa: E402

sys.path.insert(0, str(BACKEND / "scripts"))
import gen_frontend_cities as G  # noqa: E402  (reuses the same display-name rules)

COUNTRY_ORDER = ["AE", "QA", "KW", "BH", "OM", "EG", "JO", "LB", "IQ", "TR",
                 "IN", "PK", "PH", "US", "CA", "GB", "DE", "FR", "AU", "MA"]


def build_block():
    out = ["  // Non-Saudi markets, generated from backend/sources.py MARKET_CITIES."]
    for cc in COUNTRY_ORDER:
        cities = S.MARKET_CITIES.get(cc) or {}
        if not cities:
            continue
        entries = []
        for key, aliases in cities.items():
            en, ar = G.display(key, aliases)
            entries.append(f'["{key}", "{G.titlecase(en)}", "{ar}"]')
        out.append(f"  {cc}: [{', '.join(entries)}],")
    return "\n".join(out)


def main():
    src = FRONTEND.read_text(encoding="utf-8")
    # Split on newlines only so the trailing "\r" of CRLF files stays attached to each line; a
    # regex anchored with ^};$ would not match a CRLF file and would silently over-run, deleting
    # whatever exports followed the market list.
    lines = src.split("\n")

    start = next((i for i, ln in enumerate(lines) if ln.startswith("  AE:")), None)
    if start is None:
        print("ERROR: could not find the first non-Saudi market line (^  AE:) in constants.js",
              file=sys.stderr)
        return 1
    end = next((i for i in range(start, len(lines)) if lines[i].rstrip("\r") == "};"), None)
    if end is None:
        print("ERROR: could not find the line closing MARKETS after the market entries", file=sys.stderr)
        return 1

    out = lines[:start] + build_block().split("\n") + lines[end:]
    text = "\n".join(out)
    FRONTEND.write_text(text, encoding="utf-8")

    # Fail loudly rather than leaving a half-written module behind.
    for required in ("export const STATUSES", "STATUS_DOT", "countryName"):
        if required not in text:
            print(f"ERROR: {required} missing after patch", file=sys.stderr)
            return 1

    print(f"constants.js updated: {len(S.NON_SA_CITY_KEYS)} cities across {len(COUNTRY_ORDER)} markets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
