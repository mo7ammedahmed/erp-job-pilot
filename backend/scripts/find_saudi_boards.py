"""Find Saudi employer ATS boards using the real production fetchers.

Earlier probing used hand-written requests, which reported false negatives (Workable omits
`location` unless `details=true`). This calls the actual fetcher functions from sources.py, so a
board is only reported when production code can really read its jobs. Saudi relevance is judged
from location, title and description, because some boards leave the location field empty.

Run with a candidate list, then paste the reported boards into the `boards` config in sources.py.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

import sources  # noqa: E402

CANDIDATES = {
    "greenhouse": [
        "careem", "stc", "stcgroup", "stc-group", "mobily", "zain", "sabic", "sabic-energy",
        "aramco", "maaden", "neom", "redseagLOBAL", "redsea", "qiddiya", "riyadhair", "flynas",
        "noon", "salla", "mada", "tappayments", "paytabs", "lucidya", "wamda", "sarwa", "barwa",
        "balad", "diriyah", "sdaia", "diriyahgate", "vision2030", "mhr", "sela", "hema", "mrsool",
        "dosta", "nxc", "budouq", "effatah", "opco", "namshi", "jahez", "opco-sa", "mostaqbal",
        "riyadbank", "alrajhibank", "alnahdi", "alinma", "qnb", "anb", "aljazirabank", "snb",
        "astor", "mot", "motcompany", "suezcanal", "yamama", "petrofac", "nma", "mabanee",
        "vision2030sa", "hrsd", "mol", "sqrc", "arabian", "gulf", "bapco", "aramcobase", "sabicplast",
    ],
    "lever": [
        "careem", "salla", "namshi", "jahez", "mada", "paytabs", "moyasar", "sarwa", "wamda",
        "lucidya", "barwa", "sdaia", "riyadhair", "flynas", "noon", "stc", "mobily", "zain",
        "sabic", "aramco", "neom", "qiddiya", "diriyah", "tawasol", "foodics", "fetchr",
        "deliverhero", "delivereo", "talabat", "mrsool", "balad", "dosta", "nxc", "budouq",
        "maaden", "astor", "petrofac", "nma", "mabanee", "vision2030", "redseagLOBAL", "qiddiya",
    ],
    "ashby": [
        "salla", "namshi", "jahez", "mada", "paytabs", "moyasar", "lucidya", "wamda", "sarwa",
        "riyadhair", "flynas", "noon", "stc", "sabic", "neom", "qiddiya", "diriyah", "sdaia",
        "talabat", "delivereo", "careem", "foodics", "fetchr", "tawasol", "barwa", "mrsool", "balad",
        "dosta", "nxc", "budouq", "maaden", "vision2030", "redseagLOBAL",
    ],
    "workable": [
        "foodics", "fetchr", "salla", "namshi", "lucidya", "stc", "stcgroup", "mobily", "zain",
        "sabic", "aramco", "maaden", "pif", "neom", "qiddiya", "riyadhair", "flynas", "noon",
        "jahez", "mada", "tappay", "moyasar", "sdaia", "diriyah", "tawasol", "hrsd", "mol",
        "vision2030", "mhr", "sela", "hema", "noun", "mostaqbal", "barwa", "sarwa", "wamda",
        "saleor", "lucerna", "riyadbank", "alrajhibank", "snb", "alinma", "alnahdi", "qnb", "anb",
        "aljazirabank", "petrofac", "nma", "mabanee", "yamama", "suezcanal", "astor", "mot",
        "balad", "dosta", "mrsool", "nxc", "budouq", "opco", "redseagLOBAL", "vision2030sa",
    ],
    "smartrecruiters": [
        "namshi", "stc", "stcgroup", "mobily", "zain", "sabic", "aramco", "maaden", "neom",
        "qiddiya", "riyadhair", "flynas", "noon", "jahez", "mada", "foodics", "salla", "sdaia",
        "diriyah", "tawasol", "hrsd", "vision2030", "riyadbank", "alrajhibank", "snb", "alinma",
        "alnahdi", "qnb", "anb", "aljazirabank", "petrofac", "nma", "yamama", "mabanee", "balad",
        "mrsool", "dosta", "nxc", "opco", "redseagLOBAL", "mot",
    ],
}

SA_TERMS = sources.COUNTRY_HINTS["SA"]


def is_sa(job):
    hay = " ".join(str(job.get(k) or "") for k in ("location", "title", "city", "description")).lower()
    return sources.detect_country(hay) == "SA" or any(t in hay for t in SA_TERMS)


async def main():
    results = {}
    headers = {"User-Agent": "JobPilot/1.0 (+jobs aggregator)"}
    async with httpx.AsyncClient(timeout=40, follow_redirects=True, headers=headers) as c:
        for ats, boards in CANDIDATES.items():
            fn = sources.FETCHERS[ats]
            seen, uniq = set(), []
            for b in boards:
                b = b.strip()
                if b and b not in seen:
                    seen.add(b)
                    uniq.append(b)
            sem = asyncio.Semaphore(6)

            async def one(b):
                async with sem:
                    try:
                        jobs = await fn(c, [], {"boards": [b]})
                    except Exception:
                        return b, []
                    return b, jobs

            for b, jobs in await asyncio.gather(*(one(b) for b in uniq)):
                if not jobs:
                    continue
                sa = [j for j in jobs if is_sa(j)]
                results.setdefault(ats, {})[b] = (len(jobs), len(sa))
                print(f"  {ats:<15} {b:<20} jobs={len(jobs):<4} sa={len(sa)}")

    print("\n=== boards worth enabling ===")
    for ats, rows in sorted(results.items()):
        good = {b: v for b, v in rows.items() if v[1] > 0}
        if good:
            print(f"{ats}: {sorted(good)}")
        else:
            others = {b: v for b, v in rows.items() if v[0] > 0}
            if others:
                print(f"{ats}: (no Saudi detected) responded={sorted(others)}")


asyncio.run(main())
