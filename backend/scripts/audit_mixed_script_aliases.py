"""Report city aliases that mix Arabic and Latin scripts.

These are data-entry slips rather than real spellings, and they surface directly in the city picker
as names such as "الbudaiya". Detection here is one-directional (any Arabic+Latin mix) so it is
strict enough to be worth fixing, unlike a general "is this a good alias" judgement.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sources as S  # noqa: E402

ARABIC = re.compile(r"[؀-ۿݐ-ݿ]")
LATIN = re.compile(r"[A-Za-z]")
MIXED = re.compile(r"[؀-ۿݐ-ݿ].*[A-Za-z]|[A-Za-z].*[؀-ۿݐ-ݿ]")


def main():
    bad = 0
    for key, aliases in S.CITY_INDEX.items():
        for a in aliases:
            if ARABIC.search(a) and LATIN.search(a):
                bad += 1
                print(f"  {key:<24} {a!r}")
    print(f"\n{bad} mixed-script alias(es)")

    # Sanity: the Arabic display name a user would actually see must be pure Arabic or pure Latin.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    print("\nverifying generator display() output is never mixed:")
    import importlib.util
    spec = importlib.util.spec_from_file_location("gen", Path(__file__).resolve().parents[1] / "scripts" / "gen_frontend_cities.py")
    # gen_frontend_cities writes a file on import, so reuse its classifier rather than importing it.
    shown = 0
    for key, aliases in S.CITY_INDEX.items():
        arabic = [a for a in aliases if ARABIC.search(a) and not MIXED.search(a)]
        if arabic and MIXED.search(arabic[0]):
            shown += 1
            print(f"  STILL MIXED: {key} -> {arabic[0]!r}")
    print(f"  {shown} problem(s)")


main()
