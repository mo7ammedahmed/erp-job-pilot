import os
import re
import html
import asyncio
import hashlib
from datetime import datetime, timezone
import httpx
from core import db, iso, uid, NOID, logger, notify, get_plan, send_email, email_layout, integration_value

COUNTRY_NAMES = {"SA": "Saudi Arabia", "AE": "United Arab Emirates", "QA": "Qatar", "KW": "Kuwait", "BH": "Bahrain", "OM": "Oman",
                 "EG": "Egypt", "JO": "Jordan", "LB": "Lebanon", "IQ": "Iraq", "MA": "Morocco", "TN": "Tunisia", "TR": "Turkey",
                 "PK": "Pakistan", "PH": "Philippines", "GB": "United Kingdom", "US": "United States", "IN": "India",
                 "DE": "Germany", "FR": "France", "CA": "Canada", "AU": "Australia"}
# Hints used only to GUESS a country when a source doesn't already give one (e.g. manual/AI-normalized posts).
# Real filtering/search matching goes through CITY_INDEX + normalize_city below, not this list.
COUNTRY_HINTS = {
    # "SA" is populated from CITY_INDEX below, so the city list and the country hints cannot
    # drift apart when cities are added.
    "SA": [],
    "AE": ["uae", "emirates", "الإمارات", "dubai", "دبي", "abu dhabi", "أبوظبي", "sharjah", "الشارقة", "ajman", "fujairah", "ras al khaimah"],
    "QA": ["qatar", "قطر", "doha", "الدوحة"], "KW": ["kuwait", "الكويت", "kuwait city"],
    "BH": ["bahrain", "البحرين", "manama", "المنامة"], "OM": ["oman", "عُمان", "muscat", "مسقط", "salalah"],
    "EG": ["egypt", "مصر", "cairo", "القاهرة", "giza", "alexandria", "الإسكندرية"], "JO": ["jordan", "الأردن", "amman", "عمّان"],
    "LB": ["lebanon", "لبنان", "beirut", "بيروت"], "IQ": ["iraq", "العراق", "baghdad", "بغداد", "erbil", "basra"],
    "MA": ["morocco", "المغرب", "casablanca", "rabat"], "TN": ["tunisia", "تونس", "tunis"], "TR": ["turkey", "türkiye", "istanbul"],
    "PK": ["pakistan", "باكستان", "karachi", "lahore", "islamabad"], "PH": ["philippines", "manila", "makati"],
    "GB": ["united kingdom", "london", " uk"], "US": ["united states", "usa", "new york", "san francisco"],
    "IN": ["india", "bangalore", "bengaluru", "mumbai"], "DE": ["germany", "berlin", "munich"],
    "FR": ["france", "paris"], "CA": ["canada", "toronto", "vancouver"], "AU": ["australia", "sydney", "melbourne"],
}
CJ_LOCALES = {"SA": "en_SA", "AE": "en_AE", "QA": "en_QA", "KW": "en_KW", "BH": "en_BH", "OM": "en_OM", "JO": "en_JO",
              "EG": "en_EG", "GB": "en_GB", "US": "en_US", "IN": "en_IN", "DE": "de_DE", "FR": "fr_FR", "CA": "en_CA", "AU": "en_AU"}

# Canonical city key -> aliases in any language/spelling we might see from a source or type in search.
# normalize_city() folds any of these variants to the same key so "Riyadh" / "الرياض" / "riyad" match one another.
# Saudi coverage spans all 13 regions: Riyadh, Makkah, Madinah, Eastern Province, Qassim,
# Asir, Tabuk, Hail, Northern Borders, Jazan, Najran, Al Bahah and Al Jawf.
CITY_INDEX = {
    # --- Riyadh region ---
    "riyadh": ["riyadh", "riyad", "الرياض"],
    "al-kharj": ["al kharj", "alkharj", "الخرج"],
    "majmaah": ["al majmaah", "majmaah", "المجمة"],
    "zulfi": ["al zulfi", "zulfi", "الزلف"],
    "dawadmi": ["dawadmi", "ad dawadmi", "الدوادمي"],
    "diriyah": ["diriyah", "al dariyah", "الدرعية"],
    "afif": ["afif", "عفيف"],
    "wadi-ad-dawasir": ["wadi ad dawasir", "wadi al dawasir", "وادي الدواسر"],
    "thuayrat": ["thuayrat", "thuairat", "ثريعات"],
    "najd": ["najd", "نجد"],
    # --- Makkah region ---
    "jeddah": ["jeddah", "jiddah", "جدة"],
    "makkah": ["makkah", "mecca", "مكة المكرمة", "مكة"],
    "taif": ["taif", "al taif", "الطائف"],
    "rabigh": ["rabigh", "رابغ"],
    "khaybar": ["khaybar", "khaibar", "خيبر"],
    "haradh": ["haradh", "harradh", "حرض"],
    "jumum": ["jumum", "jummum", "جموم"],
    "thawal": ["thawal", "thuwal", "ثول"],
    "qunfudhah": ["al qunfudhah", "qunfudhah", "القنفذة"],
    "lehaj": ["lehaj", "لحج"],
    # --- Madinah region ---
    "madinah": ["madinah", "medina", "al madinah", "al medina", "المدينة المنورة", "المدينة"],
    "yanbu": ["yanbu", "yanbu al uqair", "ينبع"],
    "yanbu-al-bahar": ["yanbu al bahar", "yanbu al-bahar", "ينبع البحر"],
    "al-ula": ["al ula", "ela", "العلا"],
    # --- Eastern Province ---
    "dammam": ["dammam", "ad dammam", "الدمام"],
    "khobar": ["khobar", "al khobar", "الخبر"],
    "dhahran": ["dhahran", "al dhahran", "الظهران"],
    "jubail": ["jubail", "al jubail", "الجبيل"],
    "qatif": ["qatif", "al qatif", "القطيف"],
    "al-ahsa": ["al ahsa", "hofuf", "hufuf", "الأحساء", "الهفوف"],
    "hafar-al-batin": ["hafar al batin", "hafar al-batin", "حفر الباطن"],
    "ras-tanura": ["ras tanura", "ras tannura", "رأس تنورة"],
    "khafji": ["khafji", "al khafji", "خفجي"],
    "safha": ["safha", "الصفا"],
    # --- Qassim region ---
    "buraidah": ["buraidah", "buraida", "بريدة"],
    "unaizah": ["unaizah", "unieza", "عنيزة"],
    "ar-rass": ["ar rass", "al rass", "الراس"],
    "bukayriyah": ["al bukayriyah", "bukayriyah", "البكيرية"],
    "qaryat-al-kamil": ["qaryat al kamil", "qaryat al-kamil", "قرية الكامل"],
    "ras-al-khair": ["ras al khair", "رأس الخير"],
    "al-qassim": ["al qassim", "qassim", "القصيم"],
    "bada": ["badah", "bada", "al badah", "البدا"],
    # --- Asir region ---
    "abha": ["abha", "أبها"],
    "khamis-mushait": ["khamis mushait", "khamis mushayt", "خميس مشيط"],
    "bisha": ["bisha", "بيشة"],
    "baljurashi": ["baljurashi", "baljurashi", "بلجرشي"],
    "rany": ["rany", "reny", "رنية"],
    "al-baha": ["al bahah", "al baha", "الباحة"],
    "muhajjar": ["muhajjar", "محجار"],
    "al-harj": ["al harj", "al harj", "الحرج"],
    # --- Tabuk region ---
    "tabuk": ["tabuk", "تبوك"],
    "turayf": ["turayf", "turaif", "الطارف"],
    "qurayyat": ["al qurayyat", "qurayyat", "qurayat", "القريات"],
    "al-wajh": ["al wajh", "wajh", "al wagh", "الوجه"],
    "duba": ["duba", "دبة"],
    "tayyibah": ["tayyibah", "طيبة"],
    "tayma": ["tayma", "تيماء"],
    # --- Hail region ---
    "hail": ["hail", "ha'il", "ha il", "حائل"],
    "sakaka": ["sakaka", "سكاكا"],
    "qarn-al-manazil": ["qarn al manazil", "qarn al-manazil", "قرن المنازيل"],
    # --- Al Jawf region ---
    "skaka": ["skaka", "سكا"],
    "dumat-al-jandal": ["dumat al jandal", "dumat al-jandal", "دومة الجندل"],
    # --- Northern Borders region ---
    "arar": ["arar", "عرعر"],
    "al-qaisumah": ["al qaisumah", "qaisumah", "القaisyمة"],
    "rafha": ["rafha", "رفح"],
    # --- Jazan region ---
    "jazan": ["jazan", "gizan", "jizan", "جازان"],
    "sabaya": ["sabaya", "sabiyah", "صبيحة"],
    "samhat": ["samhat", "سمهات"],
    "farasan": ["farasan", "farasan islands", "فراسان"],
    "beesh": ["beesh", "بيش"],
    # --- Najran region ---
    "najran": ["najran", "نجران"],
    "sharurah": ["sharurah", "sharura", "شرورة"],
    "damt": ["damt", "ضمت"],
    "umm-al-jimal": ["umm al jimal", "umm al-jimal", "أم الجيال"],
    # --- giga-project locations that appear as "city" in postings ---
    "qiddiya": ["qiddiya", "al qiddiya", "القدية"],
    "amaala": ["amaala", "al amaala", "العمالة"],
    # --- non-Saudi markets are generated from MARKET_CITIES below ---
}

# Major cities per non-Saudi market, so every country the app can filter on has a real city list
# instead of a handful of hardcoded names. Aliases include the spellings that actually appear in
# job postings (with/without the definite article, diacritics dropped, native script where common).
# A short alias is only safe here because normalize_city() matches on word boundaries and longest
# alias first, so e.g. "cairo" cannot be shadowed by a shorter entry.
MARKET_CITIES = {
    "AE": {
        "dubai": ["dubai", "دبي"], "abu-dhabi": ["abu dhabi", "abudhabi", "أبوظبي"],
        "sharjah": ["sharjah", "الشارقة"], "al-ain": ["al ain", "ain", "العين"],
        "ajman": ["ajman", "عجمان"], "ras-al-khaimah": ["ras al khaimah", "رأس الخيمة"],
        "fujairah": ["fujairah", "فجيرة"], "umm-al-quwain": ["umm al quwain", "أم القيوين"],
    },
    "QA": {
        "doha": ["doha", "الدوحة"], "al-rayyan": ["al rayyan", "الريان"], "al-wakrah": ["al wakrah", "الوكرة"],
        "al-khor": ["al khor", "الخور"], "lusail": ["lusail", "لوسيل"], "al-daayen": ["al daayen", "الظعاين"],
        "dukhan": ["dukhan", "دخان"],
    },
    "KW": {
        "kuwait-city": ["kuwait city", "kuwait", "مدينة الكويت", "الكويت"],
        "hawalli": ["hawalli", "حولي"], "salmiya": ["salmiya", "سالمية"], "farwaniya": ["farwaniya", "الفروانية"],
        "jahra": ["jahra", "الجهراء"], "mangaf": ["mangaf", "منقف"], "ahmadi": ["ahmadi", "ahmedi", "الأحمدي"],
        "fahaheel": ["fahaheel", "الفحيحيل"],
    },
    "BH": {
        "manama": ["manama", "المنامة"], "muharraq": ["muharraq", "المحرق"], "riffa": ["riffa", "الرفاع"],
        "isa-town": ["isa town", "عيسى town", "عيسا"], "saitiya": ["saitiya", "سعدية"], "budaiya": ["budaiya", "الbudaiya", "بودايه"],
        "hamad-town": ["hamad town", "مدينة حمد"],
    },
    "OM": {
        "muscat": ["muscat", "maskat", "مسقط"], "salalah": ["salalah", "صلالة"], "sohar": ["sohar", "صحار"],
        # "صور" is deliberately absent: it is also Sidon in Lebanon, and normalize_city() has no
        # country to disambiguate with. Sidon keeps the Arabic alias; Sur is reachable in Latin.
        "nizwa": ["nizwa", "نزوى"], "sur": ["sur"], "ibri": ["ibri", "إبراء"], "rustaq": ["rustaq", "رستاق"],
        "khasab": ["khasab", "خصاب"],
    },
    "EG": {
        "cairo": ["cairo", "القاهرة"], "giza": ["giza", "الجيزة"], "alexandria": ["alexandria", "الإسكندرية"],
        "luxor": ["luxor", "الأقصر"], "aswan": ["aswan", "أسوان"], "port-said": ["port said", "بورسعيد"],
        "suez": ["suez", "السويس"], "sharm-el-sheikh": ["sharm el sheikh", "sharm", "شرم الشيخ"],
        "hurghada": ["hurghada", "الغردقة"], "mansoura": ["mansoura", "المنصورة"], "tanta": ["tanta", "طنطا"],
        "asyut": ["asyut", "أسيوط"], "zagazig": ["zagazig", "الزقازيق"],
    },
    "JO": {
        "amman": ["amman", "عمّان", "عمان"], "zarqa": ["zarqa", "الزرقاء"], "irbid": ["irbid", "إربد"],
        "aqaba": ["aqaba", "العقبة"], "madaba": ["madaba", "مادبا"], "karak": ["karak", "الكرك"],
        "salt": ["salt", "السalt", "سلط"],
    },
    "LB": {
        "beirut": ["beirut", "بيروت"], "tripoli": ["tripoli", "طرابلس"], "sidon": ["sidon", "صور"],
        "byblos": ["byblos", "جبيل"], "jounieh": ["jounieh", "جونية"], "zahle": ["zahle", "زحلة"],
    },
    "IQ": {
        "baghdad": ["baghdad", "بغداد"], "basra": ["basra", "البصرة"], "mosul": ["mosul", "الموصل"],
        "erbil": ["erbil", "أربيل"], "najaf": ["najaf", "النجف"], "karbala": ["karbala", "كربلاء"],
        "kirkuk": ["kirkuk", "كركوك"], "nasiriyah": ["nasiriyah", "الناصرية"],
    },
    "TR": {
        "istanbul": ["istanbul", "constantinople", "إسطنبول"], "ankara": ["ankara", "أنقرة"],
        "izmir": ["izmir", "İzmir", "إزمير"], "bursa": ["bursa", "بورصة"], "antalya": ["antalya", "أنطاليا"],
        "adana": ["adana", "أضنة"], "konya": ["konya", "قونية"], "gaziantep": ["gaziantep", "غازي عنتاب"],
    },
    "IN": {
        "mumbai": ["mumbai", "bombay", "मुंबई"], "delhi": ["delhi", "new delhi", "नई दिल्ली", "दिल्ली"],
        "bengaluru": ["bengaluru", "bangalore", "बेंगलुरु"], "hyderabad": ["hyderabad", "हैदराबाद"],
        "chennai": ["chennai", "madras", "चेन्नई"], "pune": ["pune", "पुणे"], "kolkata": ["kolkata", "calcutta", "कोलकाता"],
        "ahmedabad": ["ahmedabad", "अहमदाबाद"], "jaipur": ["jaipur", "जयपुर"],
    },
    "PK": {
        "karachi": ["karachi", "کراچی"], "lahore": ["lahore", "لاہور"], "islamabad": ["islamabad", "اسلام آباد"],
        "rawalpindi": ["rawalpindi", "راولپنڈی"], "peshawar": ["peshawar", "پشاور"], "quetta": ["quetta", "کوئٹہ"],
        "multan": ["multan", "ملتان"], "gujranwala": ["gujranwala", "گوجرانوالہ"],
    },
    "PH": {
        "manila": ["manila", "Maynila"], "quezon-city": ["quezon city", "quezon"], "makati": ["makati"],
        "cebu-city": ["cebu city", "cebu"], "davao": ["davao", "davao city"], "bacoor": ["bacoor"],
        "pasig": ["pasig"], "taguig": ["taguig"],
    },
    "US": {
        "new-york": ["new york", "new york city", "nyc", "brooklyn", "manhattan"], "los-angeles": ["los angeles", "la"],
        "chicago": ["chicago", "chicago il"], "houston": ["houston"], "phoenix": ["phoenix"],
        "philadelphia": ["philadelphia", "philly"], "san-francisco": ["san francisco", "sf"],
        "seattle": ["seattle"], "denver": ["denver"], "boston": ["boston"], "austin": ["austin"],
        "miami": ["miami"], "dallas": ["dallas"], "washington-dc": ["washington dc", "washington", "dc"],
        "atlanta": ["atlanta"],
    },
    "CA": {
        "toronto": ["toronto"], "vancouver": ["vancouver"], "montreal": ["montreal", "montréal"],
        "calgary": ["calgary"], "ottawa": ["ottawa"], "edmonton": ["edmonton"], "winnipeg": ["winnipeg"],
        "quebec-city": ["quebec city", "québec", "quebec"], "hamilton": ["hamilton"], "halifax": ["halifax"],
    },
    "GB": {
        "london": ["london"], "manchester": ["manchester"], "birmingham": ["birmingham"], "glasgow": ["glasgow"],
        "leeds": ["leeds"], "bristol": ["bristol"], "edinburgh": ["edinburgh"], "liverpool": ["liverpool"],
        "cardiff": ["cardiff"], "belfast": ["belfast"],
    },
    "DE": {
        "berlin": ["berlin"], "munich": ["munich", "münchen", "muenchen"], "hamburg": ["hamburg"],
        "frankfurt": ["frankfurt", "frankfurt am main"], "cologne": ["cologne", "köln", "koeln"],
        "stuttgart": ["stuttgart"], "dusseldorf": ["düsseldorf", "dusseldorf", "duesseldorf"],
        "leipzig": ["leipzig"], "dortmund": ["dortmund"], "essen": ["essen"], "bremen": ["bremen"],
        "dresden": ["dresden"], "hanover": ["hanover", "hannover"], "nuremberg": ["nuremberg", "nürnberg"],
    },
    "FR": {
        "paris": ["paris"], "marseille": ["marseille"], "lyon": ["lyon", "lyon"], "toulouse": ["toulouse"],
        "nice": ["nice"], "nantes": ["nantes"], "montpellier": ["montpellier"], "strasbourg": ["strasbourg"],
        "bordeaux": ["bordeaux"], "lille": ["lille"], "rennes": ["rennes"],
    },
    "AU": {
        "sydney": ["sydney"], "melbourne": ["melbourne"], "brisbane": ["brisbane"], "perth": ["perth"],
        "adelaide": ["adelaide"], "gold-coast": ["gold coast"], "canberra": ["canberra"], "hobart": ["hobart"],
        "darwin": ["darwin"],
    },
    "MA": {
        "casablanca": ["casablanca", "الدار البيضاء"], "rabat": ["rabat", "الرباط"],
        "marrakech": ["marrakech", "marrakesh", "مراكش"], "tangier": ["tangier", "tanger", "طنجة"],
        "agadir": ["agadir", "أكادير"], "fez": ["fez", "fes"], "meknes": ["meknes", "مكناس"], "oujda": ["oujda", "وجدة"],
    },
}
# Keys that belong to Saudi Arabia. Used to derive the country hints and to build the city picker.
SA_CITY_KEYS = {
    "riyadh", "al-kharj", "majmaah", "zulfi", "dawadmi", "diriyah", "afif", "wadi-ad-dawasir", "thuayrat", "najd",
    "jeddah", "makkah", "taif", "rabigh", "khaybar", "haradh", "jumum", "thawal", "qunfudhah", "lehaj",
    "madinah", "yanbu", "yanbu-al-bahar", "al-ula",
    "dammam", "khobar", "dhahran", "jubail", "qatif", "al-ahsa", "hafar-al-batin", "ras-tanura", "khafji", "safha",
    "buraidah", "unaizah", "ar-rass", "bukayriyah", "qaryat-al-kamil", "ras-al-khair", "al-qassim", "bada",
    "abha", "khamis-mushait", "bisha", "baljurashi", "rany", "al-baha", "muhajjar", "al-harj",
    "tabuk", "turayf", "qurayyat", "al-wajh", "duba", "tayyibah", "tayma",
    "hail", "sakaka", "qarn-al-manazil",
    "skaka", "dumat-al-jandal",
    "arar", "al-qaisumah", "rafha",
    "jazan", "sabaya", "samhat", "farasan", "beesh",
    "najran", "sharurah", "damt", "umm-al-jimal",
    "qiddiya", "amaala",
}

# Every city key outside Saudi Arabia, grouped by the market it belongs to. The grouping drives
# both the country hints and the city picker, so a city can never be claimed by two countries.
MARKET_CITY_KEYS = {cc: set(cities) for cc, cities in MARKET_CITIES.items()}
NON_SA_CITY_KEYS = set().union(*MARKET_CITY_KEYS.values()) if MARKET_CITY_KEYS else set()
# Flatten country -> {city -> aliases} into city -> aliases. Note MARKET_CITIES is nested one level
# deeper than CITY_INDEX, so the merge below must walk the inner dicts, not the country codes.
MARKET_ALIASES = {city: aliases for cities in MARKET_CITIES.values() for city, aliases in cities.items()}

# Fold the market cities into the flat lookup CITY_INDEX, and guard against a key that would
# silently shadow a Saudi city (which would make Saudi filtering match the wrong market).
_collisions = NON_SA_CITY_KEYS & set(SA_CITY_KEYS)
if _collisions:
    raise ValueError(f"City keys used by both Saudi and another market: {sorted(_collisions)}")
for _k, _aliases in MARKET_ALIASES.items():
    CITY_INDEX.setdefault(_k, list(_aliases))
# Region and country words that are not cities but still identify a Saudi posting.
_SA_EXTRA_HINTS = [
    "saudi", "saudi arabia", "ksa", "neom", "hijaz", "asir", "eastern province", "riyadh province",
    "makkah province", "al madinah province", "qassim region", "najran region", "jazan region",
    "red sea", "al jawf", "tabuk region", "hail region", "northern borders",
    "السعودية", "المملكة العربية السعودية", "نجد", "الحجاز", "عسير", "الشرقية", "القصيم", "نجران", "جازان", "الجوف",
]

_CITY_LOOKUP = {alias.lower(): key for key, aliases in CITY_INDEX.items() if aliases for alias in aliases}
# Longest alias first: a short alias can sit inside a longer city name ("duba" inside "dubai",
# "ula" inside "ulaan"), and matching that way would label the wrong city.
_CITY_ALIASES_BY_LEN = sorted(_CITY_LOOKUP.items(), key=lambda kv: -len(kv[0]))

COUNTRY_HINTS["SA"] = sorted(
    {a.lower() for k in SA_CITY_KEYS for a in (CITY_INDEX.get(k) or [])} | set(_SA_EXTRA_HINTS)
)

# Each market's own cities become country hints, so a job posted in "Manchester" is tagged GB even
# though the posting never spells out the country. Existing hand-written hints (country names, "gulf")
# are kept and these are added on top.
for _cc, _keys in MARKET_CITY_KEYS.items():
    hints = {a.lower() for k in _keys for a in (CITY_INDEX.get(k) or [])}
    if hints:
        COUNTRY_HINTS[_cc] = sorted(set(COUNTRY_HINTS.get(_cc) or []) | hints)


def normalize_city(s):
    """Fold a free-text city/location string to a canonical key so Arabic/English/misspelled variants match.
    Falls back to a slugified version of the raw text so unknown cities still compare consistently."""
    s = (s or "").strip().lower()
    if not s:
        return ""
    head = re.split(r"[,،/|]", s)[0].strip()
    if head in _CITY_LOOKUP:
        return _CITY_LOOKUP[head]
    # Longest alias first, matched on word boundaries. Plain substring matching would let a
    # short alias win from inside a longer city name ("duba" inside "dubai", "ula" in "ulaan").
    for alias, key in _CITY_ALIASES_BY_LEN:
        if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", head):
            return key
    slug = re.sub(r"[^a-z0-9\u0600-\u06ff]+", "-", head).strip("-")
    return slug


DEFAULT_SOURCES = [
    {"source_id": "careerjet", "name": "Careerjet", "kind": "publisher_api", "env_key": "CAREERJET_AFFID", "attribution": "Jobs by Careerjet", "config": {}},
    {"source_id": "jooble", "name": "Jooble", "kind": "partner_api", "env_key": "JOOBLE_API_KEY", "attribution": "Jobs by Jooble", "config": {}},
    # Board tokens below are employer account slugs on each public ATS. They can be edited at
    # runtime from Admin -> Source health, so new employers never need a code change.
    {"source_id": "greenhouse", "name": "Greenhouse boards", "kind": "ats_feed", "env_key": None, "attribution": "Company careers (Greenhouse)", "config": {"boards": ["careem", "tamara"]}},
    {"source_id": "lever", "name": "Lever boards", "kind": "ats_feed", "env_key": None, "attribution": "Company careers (Lever)", "config": {"boards": []}},
    {"source_id": "ashby", "name": "Ashby boards", "kind": "ats_feed", "env_key": None, "attribution": "Company careers (Ashby)", "config": {"boards": []}},
    {"source_id": "workable", "name": "Workable boards", "kind": "ats_feed", "env_key": None, "attribution": "Company careers (Workable)", "config": {"boards": ["foodics", "salla", "lucidya", "fetchr"]}},
    {"source_id": "smartrecruiters", "name": "SmartRecruiters boards", "kind": "ats_feed", "env_key": None, "attribution": "Company careers (SmartRecruiters)", "config": {"boards": ["namshi"]}},
    {"source_id": "remotive", "name": "Remotive", "kind": "public_api", "env_key": None, "attribution": "Remote jobs by Remotive", "config": {}},
    {"source_id": "arbeitnow", "name": "Arbeitnow", "kind": "public_api", "env_key": None, "attribution": "Jobs by Arbeitnow", "config": {}},
    {"source_id": "adzuna", "name": "Adzuna", "kind": "partner_api", "env_key": ["ADZUNA_APP_ID", "ADZUNA_APP_KEY"], "attribution": "Jobs by Adzuna", "config": {}},
    # Both boards below permit crawling in robots.txt; jobb.ae additionally publishes an RSS feed.
    {"source_id": "jobb", "name": "Jobb.ae (UAE & GCC)", "kind": "rss_feed", "env_key": None, "attribution": "Jobs by Jobb.ae", "config": {}},
    {"source_id": "jobhunt", "name": "JobHunt (UAE)", "kind": "html_index", "env_key": None, "attribution": "Jobs by JobHunt.ae", "config": {}},
    # LinkedIn has no public jobs API and its User Agreement forbids scraping, so LinkedIn-listed
    # roles reach JobPilot through the employers' own ATS boards above. A licensed aggregator that
    # is allowed to redistribute LinkedIn postings can be added as a normal partner_api source:
    # add its env_key here plus a f_<name> fetcher, and it plugs into run_source/upsert unchanged.
]


def strip_html(s):
    s = html.unescape(s or "")
    s = re.sub(r"<(br|/p|/li|/h\d)[^>]*>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n\n", s)).strip()


def detect_country(loc):
    """First country whose hint appears in `loc` as a whole word.

    Hints are matched on word boundaries, not as bare substrings: a short hint like "ksa" would
    otherwise match inside unrelated words (the German "wi*rksa*me" was detected as Saudi Arabia).
    """
    l = f" {(loc or '').lower()} "
    for code, hints in COUNTRY_HINTS.items():
        for h in hints:
            if re.search(rf"(?<!\w){re.escape(h.lower())}(?!\w)", l):
                return code
    return None


def fingerprint(title, company, city):
    norm = lambda s: re.sub(r"[^a-z0-9\u0600-\u06ff]+", "", (s or "").lower())
    return hashlib.sha1(f"{norm(title)}|{norm(company)}|{norm(city)}".encode()).hexdigest()


def mk(source, source_ref, title, company, location, url, description, country=None, remote="onsite", posted_at=None,
       salary_min=None, salary_max=None, currency=None, owner_user_id=None, **extra):
    city = (location or "").split(",")[0].strip()
    country = country or detect_country(location)
    if not country:
        # Many boards leave the location empty. The title and description often still name the
        # city or country, and an untagged job is invisible to every country filter.
        country = detect_country(f"{city} {title}")
    haystack = f"{location} {title}"
    if remote == "onsite" and re.search(r"\bremote\b", haystack, re.I):
        remote = "remote"
    elif remote == "onsite" and re.search(r"\bhybrid\b", haystack, re.I):
        remote = "hybrid"
    return {"source": source, "source_ref": str(source_ref), "title": (title or "").strip(), "company": (company or "").strip(),
            "location": location or "", "city": city, "city_key": normalize_city(city), "country": country, "remote": remote,
            "url": url, "description": strip_html(description)[:15000], "posted_at": posted_at, "salary_min": salary_min,
            "salary_max": salary_max, "currency": currency, "owner_user_id": owner_user_id,
            "fingerprint": fingerprint(title, company, city), **extra}


def _ts(v):
    try:
        if isinstance(v, (int, float)):
            return datetime.fromtimestamp(v / 1000 if v > 1e11 else v, tz=timezone.utc).isoformat()
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except Exception:
        return None


async def f_careerjet(c, queries, cfg):
    key, out = await integration_value("CAREERJET_AFFID"), []
    for q in queries:
        r = await c.get("http://public.api.careerjet.net/search", params={
            "affid": key, "keywords": q["keywords"], "location": q["city"] or COUNTRY_NAMES.get(q["country"], ""),
            "locale_code": CJ_LOCALES.get(q["country"], "en_GB"), "pagesize": 50, "user_ip": "1.1.1.1", "user_agent": "JobPilot/1.0"})
        r.raise_for_status()
        for j in r.json().get("jobs", []):
            out.append(mk("careerjet", j.get("url"), j.get("title"), j.get("company"), j.get("locations"), j.get("url"),
                          j.get("description"), country=q["country"], posted_at=_ts(j.get("date")),
                          salary_min=j.get("salary_min") or None, salary_max=j.get("salary_max") or None, currency=j.get("salary_currency_code")))
    return out


async def f_jooble(c, queries, cfg):
    key, out = await integration_value("JOOBLE_API_KEY"), []
    for q in queries:
        r = await c.post(f"https://jooble.org/api/{key}", json={"keywords": q["keywords"], "location": q["city"] or COUNTRY_NAMES.get(q["country"], "")})
        r.raise_for_status()
        for j in r.json().get("jobs", []):
            out.append(mk("jooble", j.get("id"), j.get("title"), j.get("company"), j.get("location"), j.get("link"),
                          j.get("snippet"), country=q["country"], posted_at=_ts(j.get("updated"))))
    return out


async def f_greenhouse(c, queries, cfg):
    out = []
    for b in cfg.get("boards", []):
        r = await c.get(f"https://boards-api.greenhouse.io/v1/boards/{b}/jobs", params={"content": "true"})
        if r.status_code != 200:
            continue
        for j in r.json().get("jobs", []):
            out.append(mk("greenhouse", j["id"], j.get("title"), b.replace("-", " ").title(), (j.get("location") or {}).get("name"),
                          j.get("absolute_url"), j.get("content"), posted_at=_ts(j.get("updated_at")),
                          ats="greenhouse", ats_board=b, apply_url=j.get("absolute_url")))
    return out


async def f_lever(c, queries, cfg):
    out = []
    for b in cfg.get("boards", []):
        r = await c.get(f"https://api.lever.co/v0/postings/{b}", params={"mode": "json"})
        if r.status_code != 200:
            continue
        for j in r.json():
            cat = j.get("categories") or {}
            wt = (j.get("workplaceType") or "").lower()
            out.append(mk("lever", j["id"], j.get("text"), b.replace("-", " ").title(), cat.get("location"), j.get("hostedUrl"),
                          j.get("descriptionPlain") or j.get("description"), remote=wt if wt in ("remote", "hybrid") else "onsite",
                          posted_at=_ts(j.get("createdAt")),
                          ats="lever", ats_board=b, apply_url=f"{j.get('hostedUrl', '').rstrip('/')}/apply"))
    return out


async def f_ashby(c, queries, cfg):
    out = []
    for b in cfg.get("boards", []):
        r = await c.get(f"https://api.ashbyhq.com/posting-api/job-board/{b}", params={"includeCompensation": "true"})
        if r.status_code != 200:
            continue
        for j in r.json().get("jobs", []):
            if j.get("isListed") is False:
                continue
            wt = (j.get("workplaceType") or "").lower()
            out.append(mk("ashby", j.get("id") or j.get("jobUrl"), j.get("title"), b.replace("-", " ").title(),
                          j.get("location"), j.get("jobUrl") or j.get("applyUrl"), j.get("descriptionPlain") or j.get("descriptionHtml"),
                          remote=wt if wt in ("remote", "hybrid") else ("remote" if j.get("isRemote") else "onsite"),
                          posted_at=_ts(j.get("publishedAt")),
                          ats="ashby", ats_board=b, apply_url=j.get("applyUrl") or j.get("jobUrl")))
    return out


async def f_workable(c, queries, cfg):
    out = []
    for b in cfg.get("boards", []):
        r = await c.get(f"https://apply.workable.com/api/v1/widget/accounts/{b}", params={"details": "true"})
        if r.status_code != 200:
            continue
        for j in r.json().get("jobs", []):
            # Workable exposes country/city/state at the top level plus a `locations` array;
            # there is no `location` key, so read the first entry that is actually present.
            locs = j.get("locations") or []
            loc = locs[0] if isinstance(locs, list) and locs else {}
            if not isinstance(loc, dict):
                loc = {}
            city = ", ".join(str(x) for x in (loc.get("city") or j.get("city"),
                                               loc.get("state") or j.get("state"),
                                               loc.get("country") or j.get("country")) if x)
            out.append(mk("workable", j.get("shortcode") or j.get("id"), j.get("title"), b.replace("-", " ").title(), city,
                          j.get("url") or j.get("shortlink"), j.get("full_description") or j.get("description"),
                          country=(loc.get("countryCode") or j.get("country_code")),
                          remote="remote" if (j.get("telecommuting") or loc.get("telecommuting")) else "onsite",
                          posted_at=_ts(j.get("published_on") or j.get("created_at")),
                          ats="workable", ats_board=b, apply_url=j.get("url") or j.get("shortlink")))
    return out


async def f_smartrecruiters(c, queries, cfg):
    out = []
    for b in cfg.get("boards", []):
        r = await c.get(f"https://api.smartrecruiters.com/v1/companies/{b}/postings", params={"limit": 100})
        if r.status_code != 200:
            continue
        postings = (r.json() or {}).get("content", [])[:60]  # bounded: description needs one extra call per posting

        async def _detail(p):
            try:
                dr = await c.get(f"https://api.smartrecruiters.com/v1/companies/{b}/postings/{p['id']}")
                dr.raise_for_status()
                sections = ((dr.json().get("jobAd") or {}).get("sections")) or {}
                return "\n\n".join(s.get("text", "") for s in sections.values() if isinstance(s, dict) and s.get("text"))
            except Exception:
                return ""

        descs = await asyncio.gather(*(_detail(p) for p in postings))
        for p, desc in zip(postings, descs):
            loc = p.get("location") or {}
            city = ", ".join(x for x in (loc.get("city"), loc.get("region"), loc.get("country")) if x)
            out.append(mk("smartrecruiters", p.get("id"), p.get("name"), (p.get("company") or {}).get("name"), city,
                          f"https://jobs.smartrecruiters.com/{b}/{p.get('id')}", desc,
                          remote="remote" if loc.get("remote") else "onsite", posted_at=_ts(p.get("releasedDate")),
                          ats="smartrecruiters", ats_board=b,
                          apply_url=f"https://jobs.smartrecruiters.com/{b}/{p.get('id')}"))
    return out


async def f_remotive(c, queries, cfg):
    out = []
    for kw in {q["keywords"] for q in queries}:
        r = await c.get("https://remotive.com/api/remote-jobs", params={"search": kw, "limit": 50})
        r.raise_for_status()
        for j in r.json().get("jobs", []):
            out.append(mk("remotive", j["id"], j.get("title"), j.get("company_name"), j.get("candidate_required_location") or "Remote",
                          j.get("url"), j.get("description"), country=None, remote="remote", posted_at=_ts(j.get("publication_date"))))
    return out


async def f_arbeitnow(c, queries, cfg):
    r = await c.get("https://www.arbeitnow.com/api/job-board-api")
    r.raise_for_status()
    return [mk("arbeitnow", j.get("slug"), j.get("title"), j.get("company_name"), j.get("location"), j.get("url"), j.get("description"),
               remote="remote" if j.get("remote") else "onsite", posted_at=_ts(j.get("created_at"))) for j in r.json().get("data", [])]


async def f_adzuna(c, queries, cfg):
    app_id, key, out = await integration_value("ADZUNA_APP_ID"), await integration_value("ADZUNA_APP_KEY"), []
    supported = {"GB": "gb", "US": "us", "IN": "in", "DE": "de", "AU": "au", "CA": "ca", "FR": "fr", "NL": "nl", "SG": "sg", "ZA": "za"}
    for q in queries:
        cc = supported.get(q["country"])
        if not cc:
            continue
        r = await c.get(f"https://api.adzuna.com/v1/api/jobs/{cc}/search/1", params={"app_id": app_id, "app_key": key, "results_per_page": 50,
                                                                                   "what": q["keywords"], "where": q["city"], "content-type": "application/json"})
        r.raise_for_status()
        for j in r.json().get("results", []):
            out.append(mk("adzuna", j.get("id"), j.get("title"), (j.get("company") or {}).get("display_name"), (j.get("location") or {}).get("display_name"),
                          j.get("redirect_url"), j.get("description"), country=q["country"], posted_at=_ts(j.get("created")),
                          salary_min=j.get("salary_min"), salary_max=j.get("salary_max")))
    return out


async def f_jobb_rss(c, queries, cfg):
    """jobb.ae publishes an RSS 2.0 feed for its UAE/GCC listings and permits crawling in robots.txt."""
    r = await c.get("https://jobb.ae/feed/")
    r.raise_for_status()
    out = []
    for item in re.findall(r"<item>(.*?)</item>", r.text, re.S):
        def tag(t):
            m = re.search(rf"<{t}[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{t}>", item, re.S)
            return strip_html(m.group(1)) if m else ""
        title, link = tag("title"), tag("link")
        if not title or not link:
            continue
        # The feed has no location element: the site puts it in a trailing "(City, Emirate, UAE)"
        # on the title, e.g. "Procurement Executive - Immediate Joiner (Al Ain, Abu Dhabi, UAE)".
        loc = "UAE"
        m = re.search(r"\s*\(([^()]{3,60})\)\s*$", title)
        if m:
            loc = m.group(1).strip()
            title = title[:m.start()].strip()
        out.append(mk("jobb", link, title, tag("dc:creator"), loc, link,
                      tag("description"), posted_at=_ts(tag("pubDate"))))
    return out


async def f_jobhunt(c, queries, cfg):
    """jobhunt.ae allows all crawlers except its app/admin paths (robots.txt `User-agent: *`)."""
    r = await c.get("https://jobhunt.ae/jobs")
    r.raise_for_status()
    out = []
    for card in re.findall(r'<article class="card job-card.*?</article>', r.text, re.S):
        def grab(pat, s=card):
            m = re.search(pat, s, re.S)
            return strip_html(m.group(1)) if m else ""
        link = grab(r'href="(/job/[^"]+)"')
        title = grab(r'<div class="job-title">(.*?)</div>')
        if not title or not link:
            continue
        company = grab(r'<div class="company">(.*?)</div>')
        meta = grab(r'<div class="meta">(.*?)</div>')
        parts = [p.strip() for p in meta.split("·")]
        city = parts[0] if parts else "UAE"
        work = (parts[1] if len(parts) > 1 else "").lower()
        remote = "remote" if "remote" in work else "onsite"
        out.append(mk("jobhunt", link, title, company, city, f"https://jobhunt.ae{link}", f"{title} at {company}", remote=remote))
    return out


FETCHERS = {"careerjet": f_careerjet, "jooble": f_jooble, "greenhouse": f_greenhouse, "lever": f_lever, "ashby": f_ashby,
            "workable": f_workable, "smartrecruiters": f_smartrecruiters, "remotive": f_remotive, "arbeitnow": f_arbeitnow,
            "adzuna": f_adzuna, "jobb": f_jobb_rss, "jobhunt": f_jobhunt}


async def upsert_jobs(items):
    new = 0
    for j in items:
        if not j["title"]:
            continue
        ex = await db.jobs.find_one({"fingerprint": j["fingerprint"]}, {"_id": 0, "job_id": 1})
        if ex:
            # Backfill apply metadata on every re-ingest: jobs are stored once and only refreshed,
            # so without this the ATS fields would only ever exist on newly discovered jobs.
            refresh = {"last_seen": iso(), "city_key": j["city_key"]}
            for f in ("ats", "ats_board", "apply_url"):
                if j.get(f):
                    refresh[f] = j[f]
            await db.jobs.update_one({"job_id": ex["job_id"]}, {"$addToSet": {"sources": j["source"]}, "$set": refresh})
        else:
            j.update(job_id=uid("job_"), sources=[j["source"]], fetched_at=iso(), last_seen=iso())
            await db.jobs.insert_one(j)
            new += 1
    return new


async def _queries():
    qs = {}
    async for s in db.searches.find({}, NOID):
        k = (s.get("keywords") or "", s.get("country") or "SA", s.get("city") or "")
        qs[k] = {"keywords": k[0], "country": k[1], "city": k[2]}
    return list(qs.values())[:20] or [{"keywords": "", "country": "SA", "city": ""}]


async def run_source(src, queries):
    fn = FETCHERS.get(src["source_id"])
    need = src.get("env_key")
    need = [need] if isinstance(need, str) else (need or [])
    if need and not all(await integration_value(k) for k in need):
        await db.sources.update_one({"source_id": src["source_id"]}, {"$set": {"status": "not_connected", "last_run": iso()}})
        return 0
    try:
        async with httpx.AsyncClient(timeout=40, follow_redirects=True, headers={"User-Agent": "JobPilot/1.0 (+jobs aggregator)"}) as c:
            items = await fn(c, queries, src.get("config") or {})
        new = await upsert_jobs(items)
        await db.sources.update_one({"source_id": src["source_id"]}, {"$set": {"status": "ok", "last_run": iso(), "last_count": len(items), "last_new": new, "last_error": None}})
        return new
    except Exception as e:
        logger.warning(f"source {src['source_id']} failed: {e}")
        await db.sources.update_one({"source_id": src["source_id"]}, {"$set": {"status": "error", "last_run": iso(), "last_error": str(e)[:300]}})
        return 0


async def run_all_sources():
    queries = await _queries()
    total = 0
    async for src in db.sources.find({"enabled": True}, NOID):
        total += await run_source(src, queries)
    await send_alerts()
    return total


def job_query(f, user_id):
    conds = [{"$or": [{"owner_user_id": None}, {"owner_user_id": user_id}]}]
    country, remote = f.get("country"), f.get("remote")
    if remote in ("remote", "onsite", "hybrid"):
        conds.append({"remote": remote})
    if country:
        # A country filter means this country, for every work mode. The remote branch used to skip
        # it, so a Saudi + remote search returned 109 roles from 12 other markets (Germany, the UK,
        # Qatar, ...) while "any work mode" correctly returned only the 85 Saudi ones. A user's own
        # manually added jobs stay visible whatever the market filter says.
        conds.append({"$or": [{"country": country}, {"owner_user_id": user_id}]})
    if f.get("keywords"):
        ors = []
        for kw in [k.strip() for k in f["keywords"].split(",") if k.strip()]:
            rx = {"$regex": re.escape(kw), "$options": "i"}
            ors += [{"title": rx}, {"description": rx}, {"company": rx}]
        conds.append({"$or": ors})
    if f.get("city"):
        key = normalize_city(f["city"])
        rx = {"$regex": re.escape(f["city"]), "$options": "i"}
        # Match the canonical key or the city field only. Matching the raw location string also
        # hits the province, so a "Makkah" search returned every job in "Jeddah, Makkah Province".
        ors = [{"city": rx}]
        if key:
            ors.append({"city_key": key})
        conds.append({"$or": ors})
    if f.get("seniority"):
        conds.append({"title": {"$regex": re.escape(f["seniority"]), "$options": "i"}})
    if f.get("min_salary"):
        conds.append({"$or": [{"salary_max": {"$gte": float(f["min_salary"])}}, {"salary_max": None}]})
    if f.get("source"):
        conds.append({"sources": f["source"]})
    return {"$and": conds}


async def send_alerts():
    async for s in db.searches.find({"alerts": True}, NOID):
        since = s.get("last_alert_at") or s.get("created_at")
        q = job_query(s, s["user_id"])
        q["$and"].append({"fetched_at": {"$gt": since}})
        n = await db.jobs.count_documents(q)
        await db.searches.update_one({"search_id": s["search_id"]}, {"$set": {"last_alert_at": iso()}})
        if not n:
            continue
        user = await db.users.find_one({"user_id": s["user_id"]}, {"_id": 0, "password_hash": 0})
        if not user:
            continue
        ar = user.get("lang") == "ar"
        title = f"{n} وظيفة جديدة: {s['name']}" if ar else f"{n} new jobs for “{s['name']}”"
        await notify(user["user_id"], title, link=f"/app/jobs?search={s['search_id']}", kind="alert")
        plan = await get_plan(user)
        if plan["features"].get("email_reminders") and user.get("consents", {}).get("email_messaging"):
            await send_email(to=user["email"], subject=title, html=email_layout(title, [
                "افتح JobPilot لمراجعة الوظائف الجديدة." if ar else "Open JobPilot to review the new matches."],
                "عرض الوظائف" if ar else "View jobs", "/app/jobs", rtl=ar))
