"""Curated search vocabulary for the Saudi market.

This is the vocabulary the collector and the saved-search UI share. It is deliberately data, not
code: the words employers actually write are the product here, and they change far more often
than the logic that consumes them.

Provenance and confidence
-------------------------
English terms are drawn from live KSA postings and are high confidence. The Arabic set is
deliberately small and hand-checked. A bulk machine translation of the English list was produced
and reviewed, but it came back containing invented tokens (a nonsense word standing in for
"manager", Arabic strings with a stray CJK character, English fragments mid-sentence), so it was
discarded. Only terms that are standard, widely-used Saudi job-posting vocabulary are included.
Adding to this file means being confident the term is one a Saudi employer would actually type --
an invented synonym costs recall and pollutes saved searches.

Structure
---------
Every keyword is (en, ar, [aliases]). `ar` may be None when no standard Arabic term exists for
that concept, which is normal for internationally-styled titles such as "DevOps".
"""

# --- seniority -----------------------------------------------------------------
SENIORITY = [
    ("intern", "متدرب", ["trainee", "training program", "برنامج تدريبي"]),
    ("junior", "مبتدئ", ["entry level", "fresh graduate", "حديث التخرج", "خريج جديد"]),
    ("mid level", "مستوى متوسط", ["intermediate"]),
    ("senior", "خبرة", ["senior level", "experienced", "ذو خبرة"]),
    ("lead", "قيادي", ["team lead"]),
    ("supervisor", "مشرف", ["area incharge"]),
    ("manager", "مدير", []),
    ("head of department", "رئيس قسم", []),
    ("director", "مدير عام", []),
]

# --- sector / industry --------------------------------------------------------
SECTORS = [
    ("oil and gas", "النفط والغاز", ["petroleum", "upstream", "downstream", "النفط", "غاز"]),
    ("petrochemicals", "البتروكيماويات", []),
    ("construction", "البناء", ["construction and contracting", "البناء", "المقاولات", "مقاولات"]),
    ("engineering", "الهندسة", ["consultancy", "هندسة"]),
    ("healthcare", "الرعاية الصحية", ["hospital", "مستشفى", "مستشفيات", "طبي", "الطب"]),
    ("education", "التعليم", ["school", "مدرسة", "مدارس", "جامعة", "university"]),
    ("retail", "تجزئة", ["e-commerce", "تجارة إلكترونية", "متجر", "متاجر"]),
    ("hospitality", "ضيافة", ["tourism", "سياحة", "فندق", "فنادق", "مطعم", "مطاعم"]),
    ("finance", "مالية", ["banking", "بنك", "بنوك", "مصرف"]),
    ("information technology", "تقنية المعلومات", ["IT", "software", "برمجيات", "تقنية"]),
    ("logistics", "لوجستيات", ["supply chain", "سلسلة إمداد", "مستودع", "شحن"]),
    ("human resources", "موارد بشرية", ["HR", "توظيف", "استقطاب"]),
    ("sales", "مبيعات", []),
    ("marketing", "تسويق", ["digital marketing", "تسويق رقمي"]),
    ("accounting", "محاسبة", []),
    ("legal", "قانوني", ["law", "قانون", "محاماة"]),
    ("security", "أمن", ["حماية", "security guard", "حارس أمن"]),
    ("facilities", "مرافق", ["maintenance", "صيانة"]),
    ("aviation", "طيران", ["airlines", "مطارات"]),
    ("manufacturing", "صناعة", ["production", "إنتاج"]),
]

# --- job titles ----------------------------------------------------------------
TITLES = [
    ("software engineer", "مهندس برمجيات", ["developer", "مطور", "full stack", "backend", "frontend"]),
    ("data analyst", "محلل بيانات", ["data scientist", "عالم بيانات", "data engineer"]),
    ("devops engineer", None, ["cloud engineer", "site reliability"]),
    ("cybersecurity analyst", "أخصائي أمن معلومات", ["information security", "أمن معلومات"]),
    ("project manager", "مدير مشروع", []),
    ("business analyst", "محلل أعمال", []),
    ("product manager", "مدير منتج", []),
    ("graphic designer", "مصمم جرافيك", ["designer", "تصميم"]),
    ("accountant", "محاسب", []),
    ("financial analyst", "محلل مالي", []),
    ("auditor", "مدقق", ["internal audit", "تدقيق داخلي"]),
    ("hr specialist", "أخصائي موارد بشرية", []),
    ("recruiter", "متخصص توظيف", ["talent acquisition", "استقطاب مواهب"]),
    ("sales representative", "مندوب مبيعات", ["sales executive", "تنفيذي مبيعات"]),
    ("account manager", "مدير حسابات", ["key account manager"]),
    ("business development", "تطوير الأعمال", []),
    ("marketing manager", "مدير تسويق", ["digital marketing", "تسويق رقمي"]),
    ("content writer", "كاتب محتوى", []),
    ("civil engineer", "مهندس مدني", []),
    ("mechanical engineer", "مهندس ميكانيكي", []),
    ("electrical engineer", "مهندس كهربائي", []),
    ("petroleum engineer", "مهندس نفط", []),
    ("chemical engineer", "مهندس كيميائي", []),
    ("structural engineer", "مهندس إنشائي", ["architect", "معماري"]),
    ("site engineer", "مهندس موقع", []),
    ("qa qc engineer", "مهندس ضبط الجودة", ["quality control", "ضبط جودة", "quality inspector", "مفتش جودة"]),
    ("quantity surveyor", "مساح كميات", ["surveyor", "مساح"]),
    ("hse officer", "مسؤول سلامة", ["safety officer", "سلامة", "HSE", "EHS", "NEBOSH"]),
    ("nurse", "ممرض", ["nursing", "تمريض", "ممرضة"]),
    ("doctor", "طبيب", ["physician", "specialist doctor", "استشاري"]),
    ("pharmacist", "صيدلي", ["pharmacy", "صيدلية"]),
    ("lab technician", "فني مختبر", []),
    ("teacher", "معلم", ["instructor", "معلمة", "teacher"]),
    ("lecturer", "أستاذ جامعي", ["professor"]),
    ("administrative assistant", "مساعد إداري", []),
    ("receptionist", "موظف استقبال", ["front desk", "استقبال"]),
    ("customer service", "خدمة العملاء", ["call center", "مركز اتصال"]),
    ("cashier", "كاشير", []),
    ("store manager", "مدير متجر", []),
    ("supervisor", "مشرف", []),
    ("warehouse supervisor", "مشرف مستودع", ["forklift operator", "مشغل رافعة شوكية"]),
    ("logistics coordinator", "منسق لوجستي", []),
    ("procurement", "مشتريات", ["purchasing"]),
    ("driver", "سائق", ["delivery driver", "سائق توصيل", "heavy driver", "سائق ثقيل"]),
    ("security guard", "حارس أمن", []),
    ("electrician", "كهربائي", []),
    ("welder", "لحام", ["welding inspector", "مفتش لحام"]),
    ("carpenter", "نجّار", []),
    ("mason", "بنّاء", ["bricklayer"]),
    ("plumber", "سبّاك", []),
    ("painter", "رسّام", []),
    ("scaffolder", "سقالات", ["scaffolding supervisor", "مشرف سقالات"]),
    ("rigger", "رِيجر", ["rigging"]),
    ("document controller", "منسق مستندات", ["store keeper", "أمين مستودع"]),
    ("housekeeper", "عامل نظافة", ["cleaning", "نظافة"]),
]

# --- eligibility / employment type --------------------------------------------
# These are unusually strong signals in KSA postings and are worth matching on their own.
ELIGIBILITY = [
    ("saudi national only", "سعودي فقط", ["for saudi nationals only", "للسعوديين فقط", "saudi national required"]),
    ("saudi national", "سعودي", ["saudi nationals", "السعوديين", "nationals only"]),
    ("non saudi", "غير سعودي", ["expat", "وافد", "non saudi candidates"]),
    ("transfer visa", "نقل كفالة", ["kafala transfer", "transferable iqama", "نقل إقامة", "iqama transfer"]),
    ("iqama", "إقامة", ["valid iqama", "إقامة سارية"]),
    ("visa sponsorship", "تأمين تأشيرة", ["work visa", "تأشيرة عمل", "new visa available"]),
    ("males only", "للرجال فقط", []),
    ("females only", "للنساء فقط", []),
    ("both genders", "للجنسين", ["male or female", "males or females"]),
    ("military service", "الخدمة العسكرية", ["military service exemption", "معفى من الخدمة العسكرية", "completed military service"]),
    ("tamheer", "تمهير", ["trainee saudi", "برنامج تمهير"]),
    ("hrdf", "صندوق تنمية الموارد البشرية", ["hadanaf", "هدف", "training institute", "معهد التدريب"]),
    ("nitaqat", "نطاقات", ["saudization", "التوطين", "tasheel", "تسهيل"]),
    ("gami", "قوى", ["qiwa", "منصة قوى", "gomi"]),
    ("muqeem", "مقيم", ["منصة مقيم"]),
    ("saudi professional license", "التصنيف السعودي", ["saudi council", "prometric", "/health council", "مجلس الصحي"]),
]

EMPLOYMENT_TYPE = [
    ("full time", "دوام كامل", ["permanent", "دوام"]),
    ("part time", "دوام جزئي", []),
    ("contract", "عقد", ["contractual", "عقد مؤقت", "fixed term"]),
    ("temporary", "مؤقت", []),
    ("seasonal", "موسمي", []),
    ("internship", "تدريب", []),
    ("fresh graduate", "حديث التخرج", ["new graduate", "خريج جديد", "no experience"]),
    ("immediate joining", "الالتحاق الفوري", ["immediate availability", "join immediately", "متاح فورًا"]),
]

# --- giga-projects: these pay far above market and are heavily advertised -------
GIGA_PROJECTS = [
    ("neom", "نيوم", []),
    ("the line", "ذا لاين", []),
    ("red sea global", "البحر الأحمر", ["red sea project"]),
    ("qiddiya", "القدية", []),
    ("diriyah gate", "بوابة الدرعية", ["diriyah"]),
    ("roshn", "روشن", ["al mursal"]),
    ("new murabba", "المربى", ["murabba"]),
    ("alula", "العلا", []),
    ("kaec", "مدينة الملك عبدالله الاقتصادية", ["king abdullah economic city"]),
    ("sidad", "سداد", []),
    ("amaala", "العمالة", []),
]

# --- work modes ----------------------------------------------------------------
WORK_MODES = [
    ("remote", "عن بعد", ["work from home", "wfh"]),
    ("hybrid", "هجين", []),
    ("onsite", "حضوري", ["on site", "on-site", "بالموقع", "in office", "في المكتب"]),
]

# --- Saudi cities, by hiring concentration -------------------------------------
SA_CITIES_BY_VOLUME = [
    ("riyadh", "الرياض"),
    ("jeddah", "جدة"),
    ("dammam", "الدمام"),
    ("khobar", "الخبر"),
    ("dhahran", "الظهران"),
    ("makkah", "مكة المكرمة"),
    ("madinah", "المدينة المنورة"),
    ("taif", "الطائف"),
    ("abha", "أبها"),
    ("tabuk", "تبوك"),
    ("buraidah", "البريدة"),
    ("khobar", "الخبر"),
    ("yanbu", "ينبع"),
    ("jubail", "الجبيل"),
    ("al-ahsa", "الأحساء"),
    ("hail", "حائل"),
    ("jazan", "جازان"),
    ("najran", "نجران"),
    ("al-ula", "العلا"),
    ("al-kharj", "الخرج"),
    ("unaizah", "النعيزة"),
    ("al-baha", "الباحة"),
    ("sakaka", "سكاكا"),
    ("arar", "عرعر"),
    ("duba", "دبة"),
    ("tayma", "تيماء"),
]


def _all_groups():
    return (SENIORITY, SECTORS, TITLES, ELIGIBILITY, EMPLOYMENT_TYPE, GIGA_PROJECTS, WORK_MODES)


def sa_keywords():
    """Every vetted Saudi search term as (en, ar) pairs, Arabic omitted where none exists."""
    out = []
    for group in _all_groups():
        for en, ar, _aliases in group:
            out.append((en, ar))
    return out


def sa_queries():
    """Query strings for the keyword-driven sources, in the shape sources._queries() builds.

    Arabic is included alongside English because KSA postings are bilingual: a Saudi-only role is
    often written entirely in Arabic, so an English-only term set misses it.
    """
    out = []
    for group in _all_groups():
        for en, ar, aliases in group:
            out.append(en)
            if ar:
                out.append(ar)
            for a in aliases:
                out.append(a)
    seen, uniq = set(), []
    for q in out:
        k = q.strip().lower()
        if k and k not in seen:
            seen.add(k)
            uniq.append(q)
    return uniq
