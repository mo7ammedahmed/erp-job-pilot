"""Emit the frontend SA city list from the backend CITY_INDEX so the two cannot drift.

Replaces the `CITIES` block in frontend/src/lib/constants.js in place, writing UTF-8 so Arabic
city names survive on Windows. Pass --stdout to preview the block instead of writing it.

The block used to be copied out of stdout and pasted by hand, which is how a stale city list and a
triplicated comment line ended up committed; writing the file removes that step.

Keys are the backend canonical city keys, which is what the jobs filter matches on.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sources as S  # noqa: E402

CONSTANTS = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "constants.js"

# Display names: prefer the first ASCII alias that reads like a name, then the first Arabic one.
DISPLAY_OVERRIDE = {
    "makkah": ("Mecca", "مكة المكرمة"),
    "madinah": ("Medina", "المدينة المنورة"),
    "al-ahsa": ("Al Ahsa", "الأحساء"),
    "khamis-mushait": ("Khamis Mushait", "خميس مشيط"),
    "hafar-al-batin": ("Hafar Al Batin", "حفر الباطن"),
    "ras-tanura": ("Ras Tanura", "رأس تنورة"),
    "ras-al-khair": ("Ras Al Khair", "رأس الخير"),
    "qaryat-al-kamil": ("Qaryat Al Kamil", "قرية الكامل"),
    "qarn-al-manazil": ("Qarn Al Manazil", "قرن المنازيل"),
    "dumat-al-jandal": ("Dumat Al Jandal", "دومة الجندل"),
    "wadi-ad-dawasir": ("Wadi ad-Dawasir", "وادي الدواسر"),
    "thuayrat": ("Thuayrat", "ثريعات"),
    "umm-al-jimal": ("Umm al-Jimal", "أم الجيال"),
    "qunfudhah": ("Al Qunfudhah", "القنفذة"),
    "al-qaisumah": ("Al Qaisumah", "القايسمة"),
    "yanbu-al-bahar": ("Yanbu al-Bahar", "ينبع البحر"),
    "qurayyat": ("Al Qurayyat", "القريات"),
    "ar-rass": ("Ar Rass", "الراس"),
    "bukayriyah": ("Al Bukayriyah", "البكيرية"),
    "majmaah": ("Al Majmaah", "المجمة"),
    "al-kharj": ("Al Kharj", "الخرج"),
    "dawadmi": ("Ad-Dawadmi", "الدوادمي"),
    "jumum": ("Jumum", "جموم"),
    "qatif": ("Qatif", "القطيف"),
    "safha": ("Safha", "الصفا"),
    "khafji": ("Khafji", "خفجي"),
    "baljurashi": ("Baljurashi", "بلجرشي"),
    "muhajjar": ("Muhajjar", "محجار"),
    "al-harj": ("Al Harj", "الحرج"),
    "al-baha": ("Al Bahah", "الباحة"),
    "skaka": ("Skaka", "سكا"),
    "sakaka": ("Sakaka", "سكاكا"),
    "najd": ("Najd", "نجد"),
    "hail": ("Hail", "حائل"),
    "dhahran": ("Dhahran", "الظهران"),
    "diriyah": ("Diriyah", "الدرعية"),
    "zulfi": ("Al Zulfi", "الزلف"),
    "qiddiya": ("Qiddiya", "القدية"),
    "amaala": ("Amaala", "العمالة"),
    "sabaya": ("Sabaya", "صبيحة"),
    "farasan": ("Farasan", "فراسان"),
    "thawal": ("Thawal", "ثول"),
    "bada": ("Bad'ah", "البدا"),
    "tayma": ("Tayma", "تيماء"),
    "tayyibah": ("Tayyibah", "طيبة"),
    "beesh": ("Beesh", "بيش"),
    "samhat": ("Samhat", "سمهات"),
    "al-wajh": ("Al Wajh", "الوجه"),
    "sharurah": ("Sharurah", "شرورة"),
    "damt": ("Damt", "ضمت"),
}


ARABIC_RE = re.compile(r"[؀-ۿݐ-ݿ]")
LATIN_RE = re.compile(r"[A-Za-z]")
# A city alias that mixes Arabic and Latin ("الbudaiya", "عيسى town", "السalt") is a data-entry slip,
# not a real spelling. Such an alias used to be picked as the Arabic display name and shipped that
# way to the city picker, so it is rejected here rather than shown to users.
MIXED_RE = re.compile(r"[؀-ۿݐ-ݿ].*[A-Za-z]|[A-Za-z].*[؀-ۿݐ-ݿ]")


def display(key, aliases):
    if key in DISPLAY_OVERRIDE:
        # Overrides bypass the alias table, so they are checked here too. A mixed-script name in an
        # override shipped straight to the city picker, because nothing else inspected these.
        en, ar = DISPLAY_OVERRIDE[key]
        if MIXED_RE.search(ar):
            raise ValueError(f"DISPLAY_OVERRIDE[{key!r}] Arabic name mixes scripts: {ar!r}")
        return en, ar
    # Classify by script, not by isascii(): "münchen", "köln" and "İzmir" are Latin but not ASCII,
    # and treating them as Arabic put Latin text in the Arabic column of the city picker.
    arabic = [a for a in aliases if ARABIC_RE.search(a) and not MIXED_RE.search(a)]
    latin = [a for a in aliases if not ARABIC_RE.search(a)]
    # Prefer a plain ASCII spelling when one exists, since that is what reads best in Latin script.
    latin_names = [a for a in latin if a.isascii()] or latin
    en = latin_names[0] if latin_names else key
    # With no Arabic alias, fall back to the English name rather than a raw lowercase alias.
    ar = arabic[0] if arabic else en
    return (en, ar)


def titlecase(s):
    return " ".join(w.capitalize() if w.islower() else w for w in s.split())


rows = []
for key in S.SA_CITY_KEYS:
    en, ar = display(key, S.CITY_INDEX[key])
    rows.append((key, titlecase(en), ar))

# Group by region using the ordering already encoded in SA_CITY_KEYS.
REGIONS = [
    ("Riyadh", ["riyadh", "al-kharj", "majmaah", "zulfi", "dawadmi", "diriyah", "afif", "wadi-ad-dawasir", "thuayrat", "najd"]),
    ("Makkah", ["jeddah", "makkah", "taif", "rabigh", "khaybar", "haradh", "jumum", "thawal", "qunfudhah", "lehaj"]),
    ("Madinah", ["madinah", "yanbu", "yanbu-al-bahar", "al-ula"]),
    ("Eastern Province", ["dammam", "khobar", "dhahran", "jubail", "qatif", "al-ahsa", "hafar-al-batin", "ras-tanura", "khafji", "safha"]),
    ("Qassim", ["buraidah", "unaizah", "ar-rass", "bukayriyah", "qaryat-al-kamil", "ras-al-khair", "al-qassim", "bada"]),
    ("Asir", ["abha", "khamis-mushait", "bisha", "baljurashi", "rany", "al-baha", "muhajjar", "al-harj"]),
    ("Tabuk", ["tabuk", "turayf", "qurayyat", "al-wajh", "duba", "tayyibah", "tayma"]),
    ("Hail", ["hail", "sakaka", "qarn-al-manazil"]),
    ("Al Jawf", ["skaka", "dumat-al-jandal"]),
    ("Northern Borders", ["arar", "al-qaisumah", "rafha"]),
    ("Jazan", ["jazan", "sabaya", "samhat", "farasan", "beesh"]),
    ("Najran", ["najran", "sharurah", "damt", "umm-al-jimal"]),
    ("Giga projects", ["qiddiya", "amaala"]),
]
by_key = {k: (en, ar) for k, en, ar in rows}
covered = {k for _, ks in REGIONS for k in ks}
missing = set(S.SA_CITY_KEYS) - covered
extra = covered - set(S.SA_CITY_KEYS)
if missing:
    print(f"WARNING missing from regions: {sorted(missing)}", file=sys.stderr)
if extra:
    print(f"WARNING unknown in regions: {sorted(extra)}", file=sys.stderr)


def build_block():
    lines = ["// generated from backend/sources.py CITY_INDEX — keep in sync"]
    lines.append("  SA: [")
    for region, keys in REGIONS:
        present = [k for k in keys if k in by_key]
        if not present:
            continue
        entries = ", ".join(f'["{k}", "{by_key[k][0]}", "{by_key[k][1]}"]' for k in present)
        lines.append(f"       // {region}")
        lines.append(f"       {entries},")
    lines.append("       ],")
    lines.append(f"  // {len(by_key)} Saudi cities across {len(REGIONS)} regions")

    # --- non-Saudi markets ---------------------------------------------------
    # Emitted from MARKET_CITIES so the frontend picker offers exactly the cities the backend can
    # match. Hand-maintaining this list is how the two drifted apart in the first place.
    COUNTRY_ORDER = ["AE", "QA", "KW", "BH", "OM", "EG", "JO", "LB", "IQ", "TR",
                     "IN", "PK", "PH", "US", "CA", "GB", "DE", "FR", "AU", "MA"]
    lines.append("  // non-Saudi markets, generated from backend MARKET_CITIES")
    for cc in COUNTRY_ORDER:
        cities = S.MARKET_CITIES.get(cc) or {}
        if not cities:
            continue
        entries = []
        for key, aliases in cities.items():
            en, ar = display(key, aliases)
            entries.append(f'["{key}", "{titlecase(en)}", "{ar}"]')
        lines.append(f"  {cc}: [{', '.join(entries)}],")
    lines.append(f"  // {len(S.NON_SA_CITY_KEYS)} cities across {len(COUNTRY_ORDER)} markets")
    return "\n".join(lines)


block = build_block()

if "--stdout" in sys.argv:
    print(block)
    raise SystemExit(0)

# Replace the CITIES block in place, leaving the rest of constants.js untouched.
text = CONSTANTS.read_text(encoding="utf-8")
start = text.index("export const CITIES = {")
open_brace = text.index("{", start)
close_brace = text.index("\n};", open_brace)
CONSTANTS.write_text(text[:open_brace + 1] + "\n" + block + text[close_brace:], encoding="utf-8")
print(f"wrote {len(by_key)} Saudi cities and {len(S.NON_SA_CITY_KEYS)} market cities to {CONSTANTS}", file=sys.stderr)
