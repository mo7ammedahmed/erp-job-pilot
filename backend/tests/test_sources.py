"""Country detection tests for job sources.

These guard the two failure modes that actually shipped:
  - substring matching let a short hint ("ksa") match inside an unrelated word, so a German job
    in "Türkheim" was tagged Saudi Arabia;
  - a fetcher that read a field the API does not return (Workable has no "location" key) stored
    jobs with no country at all, making them invisible to every country filter.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sources as S  # noqa: E402


def test_saudi_cities_detected():
    for loc in ["Riyadh, Saudi Arabia", "Jeddah", "الرياض", "Dammam, Eastern Province",
                "Mecca", "المدينة المنورة", "Abha", "Khobar", "NEOM", "Tabuk", "Al Ahsa"]:
        assert S.detect_country(loc) == "SA", f"{loc!r} was not detected as Saudi Arabia"


def test_hint_does_not_match_inside_a_word():
    # "ksa" used to match inside the German "wirksame", mislabelling the job as Saudi.
    assert S.detect_country("Türkheim (Senior) Berater:in für wirksame Transformation") is None
    assert S.detect_country("Wirksame Stellen in Deutschland") is None


def test_other_countries_still_detected():
    assert S.detect_country("Berlin, Germany") == "DE"
    assert S.detect_country("Dubai, United Arab Emirates") == "AE"
    assert S.detect_country("London, UK") == "GB"
    assert S.detect_country("Cairo, Egypt") == "EG"
    assert S.detect_country("Amman, Jordan") == "JO"


def test_unknown_location_is_not_forced_to_a_country():
    assert S.detect_country("Türkheim") is None
    assert S.detect_country("") is None
    assert S.detect_country(None) is None


def test_mk_falls_back_to_the_title_when_location_is_empty():
    """A board that omits location must not leave the job untagged."""
    job = S.mk("x", "1", "CEO Office Manager- Riyadh", "Acme", "", "https://example.com/1", "desc")
    assert job["country"] == "SA", job
    assert job["city_key"] == "" or job["city_key"] is not None


def test_workable_reads_the_fields_the_api_actually_returns():
    """Workable has no "location" key; country/city live at the top level and in `locations`."""
    import inspect
    src = inspect.getsource(S.f_workable)
    assert 'j.get("locations")' in src, "f_workable must read the locations array"
    assert 'j.get("city")' in src, "f_workable must fall back to the top-level city field"


def test_mk_keeps_an_explicit_country():
    job = S.mk("x", "1", "Engineer", "Acme", "Somewhere", "u", "d", country="SA")
    assert job["country"] == "SA"


# ---------- Saudi city coverage ----------

def test_all_saudi_regions_are_covered():
    assert len(S.SA_CITY_KEYS) >= 75, f"only {len(S.SA_CITY_KEYS)} Saudi cities"
    # A representative city from each of the 13 regions.
    for key in ["riyadh", "jeddah", "makkah", "madinah", "dammam", "buraidah", "abha",
                "tabuk", "hail", "skaka", "arar", "jazan", "najran"]:
        assert key in S.SA_CITY_KEYS, f"{key} is missing from the Saudi city list"


def test_city_alias_is_not_ambiguous():
    seen = {}
    for key, aliases in S.CITY_INDEX.items():
        for a in aliases:
            al = a.lower()
            assert seen.get(al, key) == key, f"alias {al!r} maps to both {seen.get(al)} and {key}"
            seen[al] = key


def test_short_alias_does_not_swallow_a_longer_city_name():
    # Substring matching used to resolve "Dubai" to the Saudi town "Duba".
    assert S.normalize_city("Dubai, United Arab Emirates") == "dubai"
    assert S.normalize_city("Duba, Saudi Arabia") == "duba"
    assert S.normalize_city("Ulaanbaatar, Mongolia") == "ulaanbaatar"
    assert S.normalize_city("Al Ula, Saudi Arabia") == "al-ula"


def test_every_saudi_city_round_trips_through_its_aliases():
    for key in S.SA_CITY_KEYS:
        for alias in S.CITY_INDEX[key]:
            assert S.normalize_city(alias) == key, f"{alias!r} did not resolve to {key}"
            assert S.detect_country(alias) == "SA", f"{alias!r} not detected as Saudi"


def test_renamed_cities_use_the_canonical_key():
    """Mecca/Medina used to be the keys; they are now makkah/madinah."""
    assert S.normalize_city("Mecca") == "makkah"
    assert S.normalize_city("Medina") == "madinah"
    assert S.normalize_city("مكة") == "makkah"
    assert S.normalize_city("المدينة المنورة") == "madinah"


def test_newly_added_cities_are_detected():
    for loc, city in [("Duba, Saudi Arabia", "duba"), ("Al Ula, Saudi Arabia", "al-ula"),
                      ("Tayma, Tabuk", "tayma"), ("Ar Rass, Qassim", "ar-rass"),
                      ("Skaka, Al Jawf", "skaka"), ("Dumat Al Jandal", "dumat-al-jandal"),
                      ("Umm al-Jimal, Najran", "umm-al-jimal"), ("Khafji", "khafji")]:
        assert S.detect_country(loc) == "SA", f"{loc!r} -> {S.detect_country(loc)}"
        assert S.normalize_city(loc) == city, f"{loc!r} -> {S.normalize_city(loc)}"


def test_country_hints_are_derived_from_the_city_list():
    """SA hints must not be maintained by hand, or they drift from CITY_INDEX."""
    for key in S.SA_CITY_KEYS:
        for alias in S.CITY_INDEX[key]:
            assert alias.lower() in S.COUNTRY_HINTS["SA"], f"{alias!r} missing from SA hints"


def test_country_filter_does_not_leak_other_markets():
    """country=SA must not match remote jobs that are actually in another country.

    This leaked before: a German job board supplied hundreds of country-less remote roles, which
    the query ORed into every country filter, so the Saudi list showed German jobs.
    """
    q = S.job_query({"country": "SA"}, "user_x")
    branches = q["$and"][1]["$or"]
    assert {"country": "SA"} in branches, branches
    # No branch may admit a remote job regardless of its country.
    assert not any("remote" in b for b in branches), branches

    remote_q = S.job_query({"remote": "remote"}, "user_x")
    assert {"remote": "remote"} in remote_q["$and"], remote_q

    # One event loop for both database checks: the shared motor client is bound to the first
    # loop it is used on, so a second asyncio.run() in the same process would fail.
    async def _verify():
        from core import db, NOID  # noqa: F401

        cur = db.jobs.find(q, {"country": 1, "owner_user_id": 1, "title": 1, "company": 1})
        bad = [d async for d in cur
               if d.get("country") != "SA" and d.get("owner_user_id") != "user_x"]
        assert not bad, f"{len(bad)} non-Saudi jobs matched the Saudi filter, e.g. {bad[:2]}"
        assert await db.jobs.count_documents(remote_q) > 0, "remote filter returned nothing"

        # Two spellings of the same city must reach the same jobs. This regressed when the
        # city keys were renamed: "Mecca" fell back to plain text matching and missed the
        # rows keyed by the canonical name.
        def city_q(city):
            return S.job_query({"country": "SA", "city": city}, "user_x")

        for a, b in [("Mecca", "Makkah"), ("مكة", "مكة المكرمة"), ("Medina", "Madinah")]:
            na = await db.jobs.count_documents(city_q(a))
            nb = await db.jobs.count_documents(city_q(b))
            assert na == nb, f"{a!r} matched {na} jobs but {b!r} matched {nb}"

        # The same must hold for work-mode filters: Saudi + remote returns Saudi jobs only.
        sa_remote = S.job_query({"country": "SA", "remote": "remote"}, "user_x")
        leaked = [c for c in await db.jobs.distinct("country", sa_remote) if c and c != "SA"]
        assert not leaked, f"Saudi + remote leaked other markets: {leaked}"

    import asyncio
    from conftest import run
    run(_verify())


def test_country_filter_applies_to_every_work_mode():
    """country=SA must constrain the results whatever the work-mode filter is.

    The remote branch used to skip the country condition entirely, so "Saudi Arabia" + "remote"
    returned 109 roles from 12 other markets (Germany, the UK, Qatar, ...) while "any work mode"
    correctly returned only the 7 Saudi remote ones.
    """
    for mode in ["remote", "onsite", "hybrid"]:
        conds = S.job_query({"country": "SA", "remote": mode}, "user_x")["$and"]
        assert {"remote": mode} in conds, conds
        country_conds = [c for c in conds if isinstance(c.get("$or"), list)
                         and {"country": "SA"} in c["$or"]]
        assert country_conds, f"work mode {mode!r} dropped the country filter: {conds}"
        # A user's own jobs stay visible regardless of the market filter.
        assert any("owner_user_id" in b for b in country_conds[0]["$or"]), country_conds


def _mk_location(location):
    return S.mk("x", "1", "Role", "Co", location, "https://example.com/1", "desc")


def test_explicit_city_outranks_a_country_word_elsewhere_in_the_string():
    """A recognised city must decide the country, not a stray country name in the same string.

    Greenhouse published a Jensen Hughes role as "Abu Dhabi, Saudi Arabia". Scanning the whole
    location string matched "saudi" and filed a UAE job under Saudi Arabia, so it leaked into the
    Saudi job list.
    """
    assert _mk_location("Abu Dhabi, Saudi Arabia")["country"] == "AE"
    assert _mk_location("Dubai, United Arab Emirates")["country"] == "AE"
    assert _mk_location("Jeddah, Saudi Arabia")["country"] == "SA"


def test_bare_city_name_identifies_its_market():
    """A posting that names only the city still gets tagged, instead of being invisible to filters."""
    assert _mk_location("Riyadh")["country"] == "SA"
    assert _mk_location("alkhubar")["country"] == "SA"


def test_city_aliases_tolerate_real_world_spelling_variants():
    """ATS feeds drop spaces and swap Latin transliterations, and both must still reach one city."""
    for spelling, key in [("alkhubar", "khobar"), ("AL KHUBAR", "khobar"), ("Al Khobar", "khobar"),
                          ("Buraydah", "buraidah"), ("Mecca", "makkah"), ("Medina", "madinah")]:
        assert S.normalize_city(spelling) == key, f"{spelling!r} did not resolve to {key!r}"


def test_country_names_do_not_become_cities():
    """Boards that put a country in the city slot must not invent a city no filter can offer."""
    for value in ["Saudi Arabia", "Saudi Arabia (KSA)", "Remote", "Worldwide", "KSA"]:
        assert S.normalize_city(value) == "", f"{value!r} was turned into a city key"


def test_city_named_after_its_country_still_resolves():
    """Guards the not-a-city check against cities that share a country's name.

    "kuwait" is both the country and the alias for Kuwait City; treating it as a country name made
    the city unfindable, which validate_cities.py caught after the not-a-city rule was added.
    """
    assert S.normalize_city("Kuwait") == "kuwait-city"
    assert _mk_location("Kuwait City, Kuwait")["country"] == "KW"


def test_no_city_alias_mixes_arabic_and_latin_scripts():
    """Mixed aliases shipped to the city picker as names like "الbudaiya" and "السalt"."""
    arabic = re.compile(r"[؀-ۿݐ-ݿ]")
    latin = re.compile(r"[A-Za-z]")
    mixed = re.compile(r"[؀-ۿݐ-ݿ].*[A-Za-z]|[A-Za-z].*[؀-ۿݐ-ݿ]")
    offenders = [a for aliases in S.CITY_INDEX.values() for a in aliases
                 if arabic.search(a) and latin.search(a) and mixed.search(a)]
    assert not offenders, f"mixed-script city aliases: {offenders}"
