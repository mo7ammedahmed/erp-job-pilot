"""Show exactly which country hint matches a given string, to explain a false positive."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sources as S  # noqa: E402

CASES = [
    "Türkheim (Senior) Berater:in für wirksame Transformation (m/w/d)",
    "Türkheim",
    "Riyadh",
    "Berlin",
    "Türkei",
]

for text in CASES:
    low = f" {text.lower()}"
    hits = [(code, h) for code, hints in S.COUNTRY_HINTS.items() for h in hints if h in low]
    print(f"{text!r}\n   detect_country -> {S.detect_country(text)}")
    for code, h in hits:
        print(f"     matched {code}: {h!r}")
    print()
