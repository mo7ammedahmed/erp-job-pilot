"""Emit the frontend SA city list from the backend CITY_INDEX so the two cannot drift.

Writes the generated block to stdout; it is pasted into frontend/src/lib/constants.js.
Keys are the backend canonical city keys, which is what the jobs filter matches on.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sources as S  # noqa: E402

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
    "al-qaisumah": ("Al Qaisumah", "القaisyمة"),
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


def display(key, aliases):
    if key in DISPLAY_OVERRIDE:
        return DISPLAY_OVERRIDE[key]
    ascii_names = [a for a in aliases if a.isascii()]
    arabic = [a for a in aliases if not a.isascii()]
    en = ascii_names[0] if ascii_names else key
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
print("// generated from backend/sources.py CITY_INDEX — keep in sync", file=sys.stderr)
if missing:
    print(f"WARNING missing from regions: {sorted(missing)}", file=sys.stderr)
if extra:
    print(f"WARNING unknown in regions: {sorted(extra)}", file=sys.stderr)

print("  SA: [")
for region, keys in REGIONS:
    present = [k for k in keys if k in by_key]
    if not present:
        continue
    entries = ", ".join(f'["{k}", "{by_key[k][0]}", "{by_key[k][1]}"]' for k in present)
    print(f"       // {region}")
    print(f"       {entries},")
print("       ],")
print(f"  // {len(by_key)} Saudi cities across {len(REGIONS)} regions", file=sys.stderr)
