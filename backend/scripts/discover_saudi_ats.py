"""Discover which ATS each Saudi employer uses, and extract its real board token.

Guessing board slugs does not work (nearly all 404). This fetches each employer's careers page
and looks for the fingerprint of the recruiting platform, then pulls the board/account token out
of the URLs on that page. Output can be pasted straight into the `boards` config in sources.py.
"""
import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

# Saudi employers: name -> careers page to inspect
CAREERS = {
    "stc": "https://www.stc.com.sa/en/careers",
    "mobily": "https://www.mobily.com.sa/en/careers",
    "zain_ksa": "https://www.zain.com/en/careers/",
    "sabic": "https://www.sabic.com/en/careers/",
    "aramco": "https://www.aramco.com/en/careers",
    "maaden": "https://www.maaden.com/en/careers",
    "pif": "https://www.pif.gov.sa/en/Pages/Careers.aspx",
    "neom": "https://www.neom.com/en/careers",
    "red_sea": "https://www.redseaglobal.com/careers",
    "qiddiya": "https://www.qiddiya.com/en/careers",
    "riyadh_air": "https://careers.riyadhair.com/",
    "flynas": "https://www.flynas.com/en/careers",
    "sparc": "https://www.sparc.com.sa/en/careers",
    "namshi": "https://careers.namshi.com/",
    "salla": "https://salla.com/careers",
    "noon": "https://careers.noon.com/",
    "jahez": "https://careers.jahez.net/",
    "mada": "https://careers.mada.com.sa/",
    "paytabs": "https://careers.paytabs.com/",
    "tap": "https://careers.tap.company/",
    "moyasar": "https://careers.moyasar.com/",
    "foodics": "https://careers.foodics.com/",
    "fetchr": "https://careers.fetchr.com/",
    "lucidya": "https://careers.lucidya.com/",
    "wamda": "https://careers.wamda.com/",
    "sarwa": "https://careers.sarwa.com/",
    "balad": "https://careers.balad.com/",
    "riyad_bank": "https://www.riyadbank.com.sa/en/careers",
    "alrajhi": "https://www.alrajhibank.com.sa/en/careers",
    "alinma": "https://www.alinma.com/en/careers",
    "aljazira_bank": "https://www.aljazirabank.com.sa/en/careers",
    "sdaia": "https://sdaia.gov.sa/en/Careers",
    "diriyah": "https://careers.dgda.gov.sa/",
    "careem": "https://www.careem.com/careers",
    "mrsool": "https://careers.mrsool.com/",
    "dosta": "https://careers.dosta.com/",
    "opco": "https://careers.opco.sa/",
    "budouq": "https://careers.budouq.com/",
    "nxc": "https://careers.nxc.sa/",
    "effatah": "https://careers.effatah.com/",
    "mhr": "https://www.mhr.sa/en/careers",
    "sela": "https://sela.sa/careers",
    "hema": "https://www.hemacorp.com/careers",
    "deliverhero": "https://careers.deliveryhero.com/",
    "talabat": "https://careers.talabat.com/",
}

# ATS fingerprint -> regexes that pull the board token out of the page
SIGNATURES = [
    ("greenhouse", [
        r"boards-api\.greenhouse\.io/v1/boards/([a-zA-Z0-9_\-]+)",
        r"job-boards\.greenhouse\.io/([a-zA-Z0-9_\-]+)",
    ]),
    ("lever", [
        r"api\.lever\.co/v0/postings/([a-zA-Z0-9_\-]+)",
        r"jobs\.lever\.co/([a-zA-Z0-9_\-]+)",
    ]),
    ("ashby", [
        r"api\.ashbyhq\.com/posting-api/job-board/([a-zA-Z0-9_\-]+)",
        r"jobs\.ashbyhq\.com/([a-zA-Z0-9_\-]+)",
    ]),
    ("workable", [
        r"apply\.workable\.com/api/v1/widget/accounts/([a-zA-Z0-9_\-]+)",
        r"apply\.workable\.com/[^/]+/j/([A-Z0-9]{6,})",
    ]),
    ("smartrecruiters", [
        r"api\.smartrecruiters\.com/v1/companies/([a-zA-Z0-9_\-]+)",
        r"jobs\.smartrecruiters\.com/([a-zA-Z0-9_\-]+)",
    ]),
    ("recruitee", [r"([a-zA-Z0-9_\-]+)\.recruitee\.com"]),
    ("teamtailor", [r"([a-zA-Z0-9_\-]+)\.teamtailor\.com"]),
    ("recruit", [r"([a-zA-Z0-9_\-]+)\.recruit\.(software|io)"]),
    ("personio", [r"([a-zA-Z0-9_\-]+)\.jobs\.personio\.de"]),
]

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
      "Accept": "text/html,application/xhtml+xml"}


async def main():
    results = {}
    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=UA) as c:
        async def one(name, url):
            try:
                r = await c.get(url)
                return name, url, r.status_code, r.text
            except Exception as e:
                return name, url, 0, str(e)[:80]

        for name, url, status, body in await asyncio.gather(*(one(n, u) for n, u in CAREERS.items())):
            found = []
            for ats, pats in SIGNATURES:
                for p in pats:
                    m = re.findall(p, body)
                    if m:
                        found.append((ats, sorted(set(m))[:3]))
                        break
            results[name] = (status, found)
            tag = ", ".join(f"{a}:{','.join(t)}" for a, t in found) or "-"
            print(f"{name:<14} {status:<4} {tag}")

    print("\n=== detected, grouped by ATS ===")
    grouped = {}
    for name, (status, found) in results.items():
        for ats, tokens in found:
            grouped.setdefault(ats, []).append((name, tokens))
    for ats, rows in sorted(grouped.items()):
        print(f"\n{ats}:")
        for name, tokens in rows:
            print(f"   {name:<14} {tokens}")


asyncio.run(main())
