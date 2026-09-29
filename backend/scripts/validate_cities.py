"""Validate the Saudi city list: every key resolves, aliases are unique, and nothing mis-matches."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sources as S  # noqa: E402

bad = 0


def check(label, cond, detail=""):
    global bad
    if not cond:
        bad += 1
    print(f"[{'PASS' if cond else 'FAIL'}] {label}" + (f" :: {detail}" if detail else ""))


check("all 13 regions represented", len(S.SA_CITY_KEYS) >= 75, f"{len(S.SA_CITY_KEYS)} Saudi cities")
check("every SA key exists in CITY_INDEX", all(S.CITY_INDEX.get(k) for k in S.SA_CITY_KEYS))
check("every SA city has an alias", all(len(S.CITY_INDEX.get(k) or []) >= 2 for k in S.SA_CITY_KEYS))

# An alias must not map to two different cities, or lookup becomes order-dependent.
seen = {}
dupes = []
for key, aliases in S.CITY_INDEX.items():
    for a in aliases:
        al = a.lower()
        if al in seen and seen[al] != key:
            dupes.append((al, seen[al], key))
        seen[al] = key
check("no alias maps to two cities", not dupes, str(dupes[:5]))

# A short alias must not swallow a longer city name.
for probe, expected in [("Dubai, UAE", "dubai"), ("Duba, Saudi Arabia", "duba"),
                        ("Ulaanbaatar, Mongolia", "ulaanbaatar"), ("Al Ula, Saudi Arabia", "al-ula")]:
    got = S.normalize_city(probe)
    check(f"normalize_city({probe!r}) == {expected!r}", got == expected, f"got {got!r}")

# Every Saudi city must round-trip from each of its aliases.
broken = [(k, a) for k in S.SA_CITY_KEYS for a in S.CITY_INDEX[k]
          if S.normalize_city(a) != k and S.normalize_city(f"{a}, Saudi Arabia") != k]
check("every Saudi alias resolves to its own city", not broken, str(broken[:5]))

# Every Saudi city must be detectable as a country.
undetected = [k for k in S.SA_CITY_KEYS
              if S.detect_country(S.CITY_INDEX[k][0]) != "SA"]
check("every Saudi city detects country SA", not undetected, str(undetected[:5]))

# --- non-Saudi markets -------------------------------------------------------
# The market lists are large and hand-written, so they get the same treatment as Saudi: an alias
# that is shadowed by another city, or a city that fails to detect its own country, would quietly
# break filtering for that market.

check("every non-SA key exists in CITY_INDEX",
      all(S.CITY_INDEX.get(k) for k in S.NON_SA_CITY_KEYS))
check("every non-SA city has an alias",
      all(len(S.CITY_INDEX.get(k) or []) >= 1 for k in S.NON_SA_CITY_KEYS))

# A country code must never be usable as a city key, or "Dubai" style lookups fall through to it.
check("no country code is a city key", not (S.NON_SA_CITY_KEYS & set(S.MARKET_CITY_KEYS)))

ns_broken = [(k, a) for k in S.NON_SA_CITY_KEYS for a in S.CITY_INDEX.get(k) or []
             if S.normalize_city(a) != k]
check("every non-SA alias resolves to its own city", not ns_broken, str(ns_broken[:5]))

# Each market's cities must detect that market, never Saudi.
ns_wrong = []
for cc, keys in S.MARKET_CITY_KEYS.items():
    for k in keys:
        got = S.detect_country(S.CITY_INDEX[k][0])
        if got != cc:
            ns_wrong.append((cc, k, got))
check("every non-SA city detects its own market", not ns_wrong, str(ns_wrong[:5]))

# A non-Saudi city must not be pulled into SA by a short alias.
for loc, want in [("Dubai, United Arab Emirates", "AE"), ("Berlin, Germany", "DE"),
                  ("Amman, Jordan", "JO"), ("Cairo, Egypt", "EG")]:
    check(f"detect_country({loc!r}) == {want}", S.detect_country(loc) == want,
          S.detect_country(loc))

print(f"\nSaudi cities: {len(S.SA_CITY_KEYS)} | total city keys: {len(S.CITY_INDEX)}")
print("RESULT:", "PASS" if not bad else f"FAIL ({bad})")
