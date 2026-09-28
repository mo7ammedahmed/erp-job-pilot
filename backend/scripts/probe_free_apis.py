"""Check which free, key-less job APIs are actually usable and how much Saudi content they hold."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from sources import detect_country, COUNTRY_HINTS  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (compatible; JobPilot/1.0; +jobs aggregator)"}

CANDIDATES = {
    "remoteok": ("https://remoteok.com/api", dict(params={})),
    "jobicy": ("https://jobicy.com/api/v2/remote-jobs", dict(params={"count": "50"})),
    "himalayas": ("https://himalayas.app/jobs/api", dict(params={"limit": "50"})),
    "wwr_rss": ("https://weworkremotely.com/remote-jobs.rss", dict(params={})),
    "arbeitnow": ("https://www.arbeitnow.com/api/job-board-api", dict(params={})),
    "remotive": ("https://remotive.com/api/remote-jobs", dict(params={"limit": "50"})),
    "adzuna_try_sa": ("https://api.adzuna.com/v1/api/jobs/sa/search/1", dict(params={"app_id": "x", "app_key": "y", "results_per_page": "5"})),
    "jobdatafeeds": ("https://jobdatafeeds.com", dict(params={})),
}


def sa_score(text):
    t = (text or "").lower()
    hits = [h for h in COUNTRY_HINTS["SA"] if h in t]
    return len(hits)


async def main():
    async with httpx.AsyncClient(timeout=40, follow_redirects=True, headers=UA) as c:
        for name, (url, kw) in CANDIDATES.items():
            try:
                r = await c.get(url, **kw)
            except Exception as e:
                print(f"{name:<16} ERROR {type(e).__name__}: {str(e)[:70]}")
                continue
            ct = r.headers.get("content-type", "")
            if r.status_code != 200:
                print(f"{name:<16} HTTP {r.status_code}  {r.text[:90]}")
                continue
            if "json" in ct:
                data = r.json()
                if isinstance(data, list):
                    rows = data
                else:
                    rows = data.get("jobs") or data.get("data") or data.get("results") or data.get("content") or []
                sa = sum(1 for j in rows if sa_score(f"{j.get('title','')} {j.get('description','')} {j.get('location','')} {j.get('company','')} {j.get('company_name','')}"))
                print(f"{name:<16} OK rows={len(rows):<5} sa_hits={sa}")
            else:
                text = r.text
                items = text.count("<item") or text.count("<entry")
                print(f"{name:<16} OK {ct.split(';')[0]} entries={items} sa_hits={text.lower().count('riyadh')+text.lower().count('saudi')}")


asyncio.run(main())
