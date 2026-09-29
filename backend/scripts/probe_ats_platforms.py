"""Probe which additional ATS platforms expose a usable public, keyless jobs API.

Only platforms whose API is publicly documented for job boards are worth adding: the collector
must not need a commercial key, and must not scrape an HTML page. This checks the endpoint shape
is real (a JSON 404 means the endpoint exists and the token is wrong; a connection error or HTML
means the endpoint is not usable).

Candidates use well-known public accounts purely to learn the response shape -- a 404 here still
proves the endpoint and path are correct.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

UA = {"User-Agent": "JobPilot/1.0 (+jobs aggregator)"}

# ats -> (list_url, sample_token)
PROBES = {
    "bamboohr":      ("https://api.bamboohr.com/api/gateway.php/{t}/v1/requests", "gitlab"),
    "recruitee":     ("https://{t}.recruitee.com/api/offers/", "visee"),
    "teamtailor":    ("https://api.teamtailor.com/api/v1/companies/{t}/jobs", "atlassian"),
    "personio":      ("https://api.personio.de/v1/companies/{t}/jobs", "treatwell"),
    "jobvite":       ("https://api.jobvite.com/api/careers/{t}", "mongodb"),
    "recruit":       ("https://{t}.recruit.io/api/v1/requisitions", "axosoft"),
    "smartrecruiters": ("https://api.smartrecruiters.com/v1/companies/{t}/postings", "namshi"),
    "workable":      ("https://apply.workable.com/api/v1/widget/accounts/{t}", "foodics"),
    "greenhouse":    ("https://boards-api.greenhouse.io/v1/boards/{t}/jobs", "careem"),
    "lever":         ("https://api.lever.co/v0/postings/{t}", "netflix"),
    "ashby":         ("https://api.ashbyhq.com/posting-api/job-board/{t}", "ashby"),
    "jazzhr":        ("https://{t}.applytojob.com/api/v2/board/jobs", "acme"),
    "workday":       ("https://{t}.wd5.myworkdayjobs.com/wday/cxs/{t}/jobs", "acme"),
    "icims":         ("https://careers.{t}.icims.com/jobs/api/v1/search", "ibm"),
    "taleo":         ("https://{t}.taleo.net/api/non-axe/v1/shield/{t}/", "boeing"),
    "onlyfy":        ("https://recruitee.com/api/v1/requisitions", "visee"),
    "pinpointhq":    ("https://job.pinpointhq.com/api/v1/boards/{t}/jobs", "stripe"),
    "jazzhr2":       ("https://api.jazzhr.com/v1/companies/{t}/jobs", "acme"),
    "ashby2":        ("https://api.ashbyhq.com/posting-api/job-board/{t}?includeCompensation=true", "ashby"),
    "workable2":     ("https://apply.workable.com/api/v1/accounts/{t}/jobs", "foodics"),
}


async def main():
    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=UA) as c:
        async def one(ats, url, tok):
            real = url.replace("{t}", tok)
            try:
                r = await c.get(real)
            except Exception as e:
                return ats, real, 0, type(e).__name__
            ct = r.headers.get("content-type", "")
            kind = "json" if "json" in ct else ("html" if "html" in ct else ct[:20])
            n = ""
            if kind == "json":
                try:
                    d = r.json()
                    n = f" keys={list(d)[:4]}" if isinstance(d, dict) else f" list[{len(d)}]"
                except Exception:
                    n = " unparseable"
            return ats, real, r.status_code, f"{kind}{n}"

        rows = await asyncio.gather(*(one(a, u, t) for a, (u, t) in PROBES.items()))
        print(f"{'ats':<16} {'code':<5} shape")
        for ats, url, code, info in sorted(rows, key=lambda r: -r[2]):
            mark = ""
            if code == 200 and info.startswith("json"):
                mark = "  <-- USABLE"
            elif code == 404:
                mark = "  (endpoint exists, token wrong)"
            elif "html" in info:
                mark = "  <-- html, not an API"
            print(f"{ats:<16} {code:<5} {info}{mark}")
            if code in (0, 403, 401):
                print(f"{'':<16}       {url}")


asyncio.run(main())
