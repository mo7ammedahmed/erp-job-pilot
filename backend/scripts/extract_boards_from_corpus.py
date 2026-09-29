"""Extract real ATS board tokens from URLs we already hold, instead of guessing slugs.

Guessing produced a 2% hit rate. Every ATS job URL embeds its board token in the path, so any
posting we have already ingested -- or any Saudi posting found on an open feed -- names a board
that is known to be live and known to post here. Those are free candidates.
"""
import asyncio
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

import sources  # noqa: E402
from core import db  # noqa: E402

# ats -> regexes that pull the board token out of a job URL
PATTERNS = {
    "greenhouse": [r"boards-api\.greenhouse\.io/v1/boards/([\w\-]+)",
                   r"(?:job-)?boards\.greenhouse\.io/([\w\-]+)"],
    "lever": [r"api\.lever\.co/v0/postings/([\w\-]+)", r"jobs\.lever\.co/([\w\-]+)"],
    "ashby": [r"api\.ashbyhq\.com/posting-api/job-board/([\w\-]+)", r"jobs\.ashbyhq\.com/([\w\-]+)"],
    "workable": [r"apply\.workable\.com/api/v1/widget/accounts/([\w\-]+)",
                 # Only the account segment. A looser pattern here also matches the literal "j" in
                 # /j/<CODE>/, which then looks like a real board token.
                 r"apply\.workable\.com/([\w\-]+)/(?:j|o)/"],
    "smartrecruiters": [r"api\.smartrecruiters\.com/v1/companies/([\w\-]+)", r"jobs\.smartrecruiters\.com/([\w\-]+)"],
    # Not yet supported by sources.py, but worth seeing what the corpus is full of.
    "recruitee": [r"([\w\-]+)\.recruitee\.com"],
    "teamtailor": [r"([\w\-]+)\.teamtailor\.com"],
    "personio": [r"([\w\-]+)\.jobs\.personio\.[a-z]+"],
    "recruit": [r"([\w\-]+)\.recruit\.(?:software|io)"],
    "bamboohr": [r"([\w\-]+)\.bamboohr\.com"],
    "dayforce": [r"([\w\-]+)\.dayforce\.com", r"jobs\.dayforce\.com/([\w\-]+)"],
    "icims": [r"([\w\-]+)\.icims\.com"],
    "taleo": [r"([\w\-]+)\.taleo\.net"],
}


def tokens_from(url):
    out = {}
    if not url:
        return out
    for ats, pats in PATTERNS.items():
        for p in pats:
            m = re.search(p, url)
            if m:
                out[ats] = m.group(1)
                break
    return out


async def main():
    seen = defaultdict(set)
    async for j in db.jobs.find({}, {"url": 1, "country": 1, "source": 1, "_id": 0}):
        for ats, tok in tokens_from(j.get("url")).items():
            seen[ats].add(tok)
    print("=== tokens found in the local job corpus (by url) ===")
    for ats, toks in sorted(seen.items()):
        print(f"  {ats:<16} {len(toks):<4} {sorted(toks)[:25]}")
    if not seen:
        print("  (none)")

    # Cross-check the Saudi-relevant ones through the real fetchers.
    supported = set(sources.FETCHERS)
    print("\n=== validating against the production fetchers ===")
    sem = asyncio.Semaphore(6)

    async with httpx.AsyncClient(timeout=40, follow_redirects=True,
                                 headers={"User-Agent": "JobPilot/1.0 (+jobs aggregator)"}) as c:
        for ats in sorted(seen):
            if ats not in supported:
                print(f"  {ats}: SKIPPED (no fetcher implemented)")
                continue
            fn = sources.FETCHERS[ats]

            async def one(b):
                async with sem:
                    try:
                        return b, await fn(c, [], {"boards": [b]})
                    except Exception:
                        return b, []

            for b, jobs in await asyncio.gather(*(one(b) for b in sorted(seen[ats]))):
                if not jobs:
                    continue
                sa = [j for j in jobs if sources.detect_country(
                    " ".join(str(j.get(k) or "") for k in ("location", "title", "description"))) == "SA"]
                flag = "SA" if sa else "--"
                print(f"  {ats:<16} {b:<22} jobs={len(jobs):<4} {flag}={len(sa)}")


asyncio.run(main())
