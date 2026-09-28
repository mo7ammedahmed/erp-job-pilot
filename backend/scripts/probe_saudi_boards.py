"""Probe public ATS boards for Saudi employers and report which ones actually return jobs.

No API keys needed: Greenhouse, Lever, Ashby, Workable and SmartRecruiters all expose public
job-board endpoints. This checks each candidate board token, keeps the ones that respond, and
counts how many of their postings are actually in Saudi Arabia.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from sources import detect_country, COUNTRY_HINTS  # noqa: E402

# Candidate board tokens for large Saudi employers and the ATS they commonly use.
CANDIDATES = {
    "greenhouse": [
        "stc", "stcgroup", "mobily", "zain", "zainksa", "sab ic", "sabic", "aramco", "saudipetro",
        "maaden", "pi f", "pif", "neom", "redseagLOBAL", "redsea", "qiddiya", "riyadhair", "flynas",
        "flyadeal", "flyadeal", "sparc", "sparcx", "namshi", "salla", "sallaapp", "jahez", "noon",
        "noonretail", "mada", "paytabs", "tappay", "moyasar", "lucidya", "saleor", "lucerna", "opal",
        "wamda", "sarwa", "barwa", "amana-capital", "riyadbank", "sabb", "alrajhibank", "alrajhi",
        "snb", "alnahdi", "alinma", "qnb", "anb", "aljazira", "aljazirabank", "waad", "tawasol",
        "sdaia", "diriyahgate", "diriyah", "hema", "noun", "mhr", "sela", "layla", "vision2030",
        "hrsd", "mol", "mostaqbal", "almaq", "suezcanal", "yamama", "arabian", "mabanee", "nma",
        "petrofac", "aramco trading", "astor", "gulf", "bapco", "aramcobase", "mot", "motcompany",
    ],
    "lever": [
        "salla", "salla-app", "namshi", "jahez", "mada", "paytabs", "moyasar", "sarwa", "wamda",
        "lucidya", "barwa", "sdaia", "riyadhair", "flynas", "noon", "stc", "mobily", "zain",
        "sabic", "aramco", "neom", "qiddiya", "diriyah", "tawasol", "mada-payment", "tappay",
        "foodics", "fetchr", "deliveryhero", "delivereo", "careem", "talabat", "noon-retail",
    ],
    "ashby": [
        "salla", "namshi", "jahez", "mada", "paytabs", "moyasar", "lucidya", "wamda", "sarwa",
        "riyadhair", "flynas", "noon", "stc", "sabic", "neom", "qiddiya", "diriyah", "sdaia",
        "talabat", "delivereo", "careem", "foodics", "fetchr", "tawasol", "barwa", "mrsool", "mrsoolhr",
    ],
    "workable": [
        "stc", "stcgroup", "mobily", "zain", "sabic", "aramco", "maaden", "pif", "neom", "qiddiya",
        "riyadhair", "flynas", "noon", "jahez", "mada", "tappay", "moyasar", "foodics", "fetchr",
        "salla", "namshi", "sdaia", "diriyah", "tawasol", "hrsd", "mol", "vision2030", "mhr", "sela",
        "hema", "noun", "mostaqbal", "barwa", "sarwa", "wamda", "lucidya", "saleor", "lucerna",
        "riyadbank", "alrajhibank", "snb", "alinma", "alnahdi", "qnb", "anb", "aljazirabank",
        "petrofac", "aramco-sabian", "nma", "mabanee", "yamama", "suezcanal", "astor", "mot",
    ],
    "smartrecruiters": [
        "stc", "stcgroup", "mobily", "zain", "sabic", "aramco", "maaden", "neom", "qiddiya",
        "riyadhair", "flynas", "noon", "jahez", "mada", "foodics", "salla", "namshi", "sdaia",
        "diriyah", "tawasol", "hrsd", "vision2030", "riyadbank", "alrajhibank", "snb", "alinma",
        "alnahdi", "qnb", "anb", "aljazirabank", "petrofac", "nma", "yamama", "mabanee",
    ],
}

UA = {"User-Agent": "Mozilla/5.0 (compatible; JobPilot/1.0; +jobs aggregator)"}


async def probe_greenhouse(c, b):
    r = await c.get(f"https://boards-api.greenhouse.io/v1/boards/{b}/jobs", params={"content": "false"})
    if r.status_code != 200:
        return None
    return [(j.get("title", ""), (j.get("location") or {}).get("name", "")) for j in r.json().get("jobs", [])]


async def probe_lever(c, b):
    r = await c.get(f"https://api.lever.co/v0/postings/{b}", params={"mode": "json"})
    if r.status_code != 200:
        return None
    data = r.json()
    if not isinstance(data, list):
        return None
    return [((j.get("categories") or {}).get("commitment") or "", (j.get("categories") or {}).get("location", "")) for j in data]


async def probe_ashby(c, b):
    r = await c.get(f"https://api.ashbyhq.com/posting-api/job-board/{b}")
    if r.status_code != 200:
        return None
    return [(j.get("title", ""), j.get("location") or "") for j in r.json().get("jobs", []) if j.get("isListed") is not False]


async def probe_workable(c, b):
    r = await c.get(f"https://apply.workable.com/api/v1/widget/accounts/{b}", params={"details": "false"})
    if r.status_code != 200:
        return None
    return [(j.get("title", ""), j.get("location", {}).get("city", "") if isinstance(j.get("location"), dict) else "") for j in r.json().get("jobs", [])]


async def probe_smartrecruiters(c, b):
    r = await c.get(f"https://api.smartrecruiters.com/v1/companies/{b}/postings", params={"limit": "100"})
    if r.status_code != 200:
        return None
    return [((p.get("name") or ""), ", ".join(x for x in ((p.get("location") or {}).get(k) for k in ("city", "country")) if x)) for p in (r.json() or {}).get("content", [])]


PROBES = {"greenhouse": probe_greenhouse, "lever": probe_lever, "ashby": probe_ashby,
          "workable": probe_workable, "smartrecruiters": probe_smartrecruiters}


def is_sa(loc):
    return detect_country(loc) == "SA" or any(h in (loc or "").lower() for h in COUNTRY_HINTS["SA"])


async def main():
    found = {}
    async with httpx.AsyncClient(timeout=25, follow_redirects=True, headers=UA) as c:
        for ats, boards in CANDIDATES.items():
            fn = PROBES[ats]
            # de-duplicate while preserving order
            seen, uniq = set(), []
            for b in boards:
                b = b.strip()
                if b and b not in seen:
                    seen.add(b)
                    uniq.append(b)
            sem = asyncio.Semaphore(8)

            async def one(b):
                async with sem:
                    try:
                        return b, await fn(c, b)
                    except Exception:
                        return b, None

            for b, rows in await asyncio.gather(*(one(b) for b in uniq)):
                if not rows:
                    continue
                sa = [r for r in rows if is_sa(r[1])]
                found[(ats, b)] = (len(rows), len(sa))
                print(f"  OK {ats:<15} {b:<22} jobs={len(rows):<4} sa={len(sa)}")
    print(f"\nboards that responded: {len(found)}")
    sa = [k for k, v in found.items() if v[1]]
    print(f"boards with Saudi postings: {len(sa)}")
    for k in sorted(sa):
        print(f"   {k[0]:<15} {k[1]:<22} sa={found[k][1]}/{found[k][0]}")


asyncio.run(main())
