"""Validate candidate ATS board tokens from live-observed URLs against the production fetchers.

A token in a URL proves the board exists, not that it posts Saudi jobs, and it certainly does not
prove the token still resolves. So every candidate is run through the same fetcher sources.py uses
and judged on what actually comes back.

A board is worth enabling when it returns jobs AND at least one is detected as Saudi.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

import sources  # noqa: E402

# Tokens taken from URLs that were actually observed, grouped by platform.
CANDIDATES = {
    "lever": [
        "sar",            # Saudi Railway Company
        "sta",            # Saudi Tourism Authority
        "weloglobal",     # Welo Global (Saudi-linked)
        "tsmg",           # TSMG (Riyadh)
        "trendyol", "lalamove", "fresha", "soum", "jobgether", "Yassir",
        "dlocal", "nium", "aleph", "flowlife", "infinitepl", "visioninvest",
        "biocatch", "extremenetworks", "bluecatnetworks",
    ],
    "ashby": [
        "checkout.com",   # payments, KSA presence
        "alan",           # health insurance
        "leantech",       # SAMA-licensed payments, KSA
        "nash",           # quick-commerce/logistics
        "sarjai",         # Voice AI, Saudi
        "takein",         # food delivery, Dammam
        "lakeora", "cognition", "humanoid", "quartermaster", "redesign health",
    ],
    "greenhouse": [
        "ogilvymena",     # Ogilvy MENA, Riyadh
        "capco",          # financial consulting, KSA
        "hala",           # SME fintech/payments
        "egis", "aecomsaudi",
        "cssmerge",       # construction
        "kitchenpark",    # quick-commerce, KSA
        "jensenhughes", "decimainternational", "nozominetworks", "telnyx54",
        "ebanx", "lucidmotors", "agoda", "gallup", "minio",
    ],
    "workable": [
        "careers-sixflags-and-aquarabia",   # Qiddiya
        "hanmiglobal-saudi",               # NEOM / KFMC projects
        "alomar-holding-company",
        "alkaffary-group",
        "sihamco", "nowlun", "jasarapmc", "qiddiya-investment-company-1",
        "ccds", "awtad", "tajhr", "jeeny", "tawantech", "horizontal-digital",
    ],
    "smartrecruiters": [
        "AccorCorpo",     # hotels Jeddah/Makkah
        "AccorHotel",     # SLS The Red Sea
        "rhg", "RHG",     # Radisson Hotel Group
        "egisgroup", "turnertownsend", "TurnerTownsend",
        "AECOM2", "smithsgroup2", "rolandberger",
        "AbbVie", "sobi", "CheckPointSoftwareTechnologies2",
        "JobsForHumanity",  # King Saud University
    ],
}

SA_HINT_FIELDS = ("location", "title", "city", "description", "company")


def sa_score(job):
    """How strongly this job looks Saudi, using the same detection the app filters on."""
    hay = " ".join(str(job.get(k) or "") for k in SA_HINT_FIELDS)
    return sources.detect_country(hay) == "SA"


async def main():
    headers = {"User-Agent": "JobPilot/1.0 (+jobs aggregator)"}
    keep = {}
    async with httpx.AsyncClient(timeout=40, follow_redirects=True, headers=headers) as c:
        for ats, boards in CANDIDATES.items():
            fn = sources.FETCHERS[ats]
            uniq = list(dict.fromkeys(b.strip() for b in boards if b.strip()))
            sem = asyncio.Semaphore(6)

            async def one(b):
                async with sem:
                    try:
                        # A board that stalls must not hold up the whole sweep.
                        return b, await asyncio.wait_for(fn(c, [], {"boards": [b]}), timeout=45)
                    except Exception:
                        return b, []

            async def report(b, jobs):
                if not jobs:
                    return
                sa = [j for j in jobs if sa_score(j)]
                keep.setdefault(ats, []).append(b) if sa else None
                mark = "SAUDI" if sa else "     "
                print(f"  {b:<34} jobs={len(jobs):<4} {mark}={len(sa)}", flush=True)

            print(f"\n=== {ats} ===", flush=True)
            for fut in asyncio.as_completed([one(x) for x in uniq]):
                b, jobs = await fut
                await report(b, jobs)

    print("\n\n=== boards to enable (have Saudi jobs) ===")
    total = 0
    for ats, boards in sorted(keep.items()):
        print(f'    "{ats}": {boards},')
        total += len(boards)
    print(f"\n{total} boards across {len(keep)} platforms")


asyncio.run(main())
