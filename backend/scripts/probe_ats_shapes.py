"""Pin down the exact request/response shape for the additional ATS platforms worth adding.

The first probe only proved the endpoints exist (JSON 404). This sends the documented request
shape so the response body can be mapped onto the fields sources.py already understands, and so a
fetcher can be written against a known contract instead of a guess.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

UA = {"User-Agent": "JobPilot/1.0 (+jobs aggregator)"}


async def show(c, label, coro):
    try:
        r = await coro
    except Exception as e:
        print(f"\n--- {label}\n  ERROR {type(e).__name__}: {str(e)[:100]}")
        return
    ct = r.headers.get("content-type", "")
    print(f"\n--- {label}\n  {r.status_code}  {ct[:40]}")
    if "json" in ct:
        try:
            d = r.json()
        except Exception:
            print("  <unparseable>")
            return
        if isinstance(d, dict):
            print("  top keys:", list(d)[:8])
            for k in ("jobs", "content", "offers", "requisitions", "results", "jobPostings"):
                v = d.get(k)
                if isinstance(v, list) and v:
                    print(f"  {k}[0] keys:", list(v[0])[:22])
                    print("  sample:", json.dumps(v[0], ensure_ascii=False)[:600])
                    return
            print("  body:", json.dumps(d, ensure_ascii=False)[:400])
        else:
            print(f"  list[{len(d)}] first:", json.dumps(d[0], ensure_ascii=False)[:400] if d else "empty")
    else:
        print("  " + r.text[:200].replace("\n", " "))


async def main():
    async with httpx.AsyncClient(timeout=35, follow_redirects=True, headers=UA) as c:
        # Recruitee: public, keyless, no auth.
        await show(c, "recruitee  GET /api/offers/  (token 'visee')",
                   c.get("https://visee.recruitee.com/api/offers/"))
        # Recruitee global domain form.
        await show(c, "recruitee  GET recruitee.com/api/offers  (query)",
                   c.get("https://recruitee.com/api/offers/", params={"limit": 2}))

        # Personio: public job board feed is XML at /xml on the jobs subdomain.
        await show(c, "personio   GET /xml  (treatwell)",
                   c.get("https://treatwell.jobs.personio.de/xml"))
        await show(c, "personio   GET personio.com/xml?language=en",
                   c.get("https://www.personio.com/xml", params={"language": "en"}))

        # Workday CXS: public POST search endpoint.
        body = {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""}
        await show(c, "workday    POST /wday/cxs/{t}/jobs  (tenant 'nike')",
                   c.post("https://nike.wd5.myworkdayjobs.com/wday/cxs/nike/jobs", json=body,
                          headers={**UA, "Content-Type": "application/json"}))

        # BambooHR: public per-board feed.
        await show(c, "bamboohr   GET /jobs/feed  (gitlab)",
                   c.get("https://gitlab.bamboohr.com/jobs/feed"))
        await show(c, "bamboohr   GET /jobs (html?)",
                   c.get("https://gitlab.bamboohr.com/jobs"))


asyncio.run(main())
