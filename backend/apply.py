"""Automated job application submission.

Each ATS renders its form differently and none of them offer a public "submit application" API, so
this drives a real browser (Playwright/Chromium) against the employer's form and fills it in.

Design rules, because this writes to a third party on the user's behalf:
  * Never guess silently. Every run returns a structured status and records why it stopped.
  * A CAPTCHA or bot challenge stops the run and reports `needs_human`. We do not attempt to
    solve, bypass, or evade bot protection.
  * Required fields we cannot confidently fill stop the run the same way, rather than submitting
    a form full of blanks.
  * Every run keeps a screenshot + final URL as evidence of what was actually submitted.
"""
import asyncio
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from core import logger

# Playwright's sync API cannot run inside the asyncio loop this server uses, so every entry point
# here is sync and the router calls it through asyncio.to_thread.
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# Pages we are willing to drive. Anything else (an ATS we do not model, or an arbitrary domain a
# scraped job happened to point at) is not auto-submitted.
ALLOWED_HOSTS = (
    "boards.greenhouse.io", "job-boards.greenhouse.io", "greenhouse.io",
    "jobs.lever.co", "lever.co",
    "jobs.ashbyhq.com", "ashbyhq.com",
    "apply.workable.com", "workable.com",
    "jobs.smartrecruiters.com", "smartrecruiters.com",
)

# Pages that mean "a human must take over", not "it failed".
CAPTCHA_HOSTS = ("recaptcha", "hcaptcha", "turnstile", "challenges.cloudflare", "/cdn-cgi/challenge")
BOT_MARKERS = ("cf-challenge", "cf-browser-verification", "px-captcha", "captcha-container",
               "datadome", "perimeterx", "akamai bot")

SUCCESS_RE = re.compile(
    r"(thank you for applying|thanks for applying|application (has been |was )?(received|submitted)|"
    r"we(?:'ve| have) received your application|we received your application|"
    r"application complete|you('re| have) applied|submitted successfully|"
    r"تم استلام طلبك|شكرا.*تقديم|تم إرسال طلبك)", re.I)

# Field intents, most specific first. `any` matches the element's accessible description, `must`
# rejects it outright. Scoring is heuristic on purpose: no two ATSes use the same markup.
FIELD_SPECS = [
    ("email",       {"any": [r"e-?mail"], "types": ["email"], "prefer": [r"e-?mail"]}),
    ("first_name",  {"any": [r"first.?name", r"given.?name", r"الاسم.?الأول", r"firstname"]}),
    ("last_name",   {"any": [r"last.?name", r"surname", r"family.?name", r"اسم.?العائلة"]}),
    ("full_name",   {"any": [r"full.?name", r"your.?name", r"candidate.?name", r"^name$", r"الاسم"]}),
    ("phone",       {"any": [r"phone", r"mobile", r"telephone", r"contact.?number", r"هاتف", r"جوال"]}),
    ("linkedin",    {"any": [r"linkedin"]}),
    ("website",     {"any": [r"(personal|portfolio|web)?site.?url", r"portfolio", r"github"]}),
    ("location",    {"any": [r"(current )?location", r"city", r"country"]}),
    ("cover_letter", {"any": [r"cover.?letter", r"why.{0,12}(you|interested)", r"tell us about",
                              r"motivat", r"about yourself", r"خطاب.?التقديم", r"لماذا"], "types": ["textarea"]}),
]

SUBMIT_RE = re.compile(
    r"^(submit|send|apply|submit application|send application|apply now|submit my application|"
    r"تقديم|إرسال|قدّم الآن)\s*$", re.I)

# Runs are bounded: a form that has not settled by now is treated as needing a human.
NAV_TIMEOUT_MS = 45000
STEP_TIMEOUT_MS = 12000

# Maps a form input to one of our intents. Executed in the page, so it must be self-contained JS.
_MAP_FIELDS_JS = """
(opts) => {
  const nodes = Array.from(document.querySelectorAll(
    'input:not([type=hidden]):not([type=submit]):not([type=button]):not([type=file]), textarea'));
  const used = new Set();
  const desc = (el) => {
    const bits = [el.name, el.id, el.placeholder, el.getAttribute('aria-label'),
                  el.getAttribute('data-field'), el.autocomplete, el.type, el.className];
    if (el.labels && el.labels.length) {
      for (const l of el.labels) { bits.push(l.innerText || l.textContent); }
    }
    const wrap = el.closest('div, td, li, p, label, fieldset');
    if (wrap) { bits.push((wrap.innerText || '').slice(0, 160)); }
    return bits.filter(Boolean).join(' | ').toLowerCase();
  };
  const out = {};
  for (const [intent, cfg] of opts) {
    let best = -1, bestScore = 0;
    nodes.forEach((el, i) => {
      if (used.has(i)) { return; }
      const d = desc(el);
      let hit = false;
      for (const p of cfg.any) { if (new RegExp(p, 'i').test(d)) { hit = true; break; } }
      if (!hit) { return; }
      let score = 10;
      for (const p of cfg.prefer || []) { if (new RegExp(p, 'i').test(d)) { score += 5; } }
      if (cfg.types && cfg.types.indexOf((el.type || '').toLowerCase()) >= 0) { score += 4; }
      if (el.required) { score += 2; }
      if (score > bestScore) { bestScore = score; best = i; }
    });
    if (best >= 0) { used.add(best); out[intent] = best; }
  }
  return { mapping: out, total: nodes.length };
}
"""

# A file input for the CV, if the form has one.
_FIND_FILE_JS = """
() => {
  const inputs = Array.from(document.querySelectorAll('input[type=file]'));
  if (!inputs.length) { return -1; }
  let best = 0;
  inputs.forEach((el, i) => {
    const d = ((el.name||'') + ' ' + (el.id||'') + ' ' + (el.accept||'') + ' ' +
               (el.getAttribute('aria-label')||'')).toLowerCase();
    if (/resume|cv|curriculum|cover.?doc|ب.?سيرة/.test(d)) { best = i; }
  });
  return best;
}
"""

# Text that proves a challenge is in the way.
_DETECT_BLOCK_JS = """
() => {
  const out = { captcha: false, markers: [] };
  for (const f of document.querySelectorAll('iframe[src]')) {
    const s = (f.getAttribute('src') || '').toLowerCase();
    if (/recaptcha|hcaptcha|turnstile|challenges\\.cloudflare/.test(s)) { out.captcha = true; out.markers.push(s); }
  }
  const t = ((document.title || '') + ' ' + (document.body ? document.body.innerText.slice(0, 800) : '')).toLowerCase();
  if (/just a moment|checking your browser|verify you are human|are you a robot|attention required/.test(t)) {
    out.captcha = true;
  }
  for (const el of document.querySelectorAll('[class*=captcha i], [id*=captcha i], [data-sitekey]')) {
    out.captcha = true; out.markers.push((el.className || el.id || 'captcha').toString().slice(0, 60));
  }
  out.title = document.title;
  return out;
}
"""

# Required inputs still empty after filling, so a submit is not attempted on a half-empty form.
_UNFILLED_JS = """
() => {
  const out = [];
  const nodes = Array.from(document.querySelectorAll(
    'input:not([type=hidden]):not([type=submit]):not([type=button]):not([type=file]), textarea, select'));
  for (const el of nodes) {
    if (!el.required) { continue; }
    const v = (el.value || '').trim();
    if (v) { continue; }
    if (el.tagName === 'SELECT') {
      const sel = el.selectedIndex;
      if (sel > 0 && (el.options[sel].value || '').trim()) { continue; }
    }
    let label = '';
    if (el.labels && el.labels.length) { label = el.labels[0].innerText || ''; }
    out.push(((label || el.name || el.placeholder || el.type) || 'field').trim().slice(0, 60));
  }
  return out;
}
"""


def _ok(status, message, **extra):
    """Build the structured result every code path returns, so callers never guess the outcome."""
    out = {"status": status, "message": message, "filled": [], "submitted": False,
           "final_url": "", "screenshot": None, "blockers": []}
    out.update(extra)
    return out


def _allowed_hosts():
    """The modelled ATS hosts, plus any explicitly configured extras (self-hosted ATS, tests)."""
    extra = (os.environ.get("JOBPILOT_APPLY_EXTRA_HOSTS") or "").strip()
    return ALLOWED_HOSTS + tuple(h.strip().lower() for h in extra.split(",") if h.strip())


def _host_ok(url):
    if not url or not url.startswith(("http://", "https://")):
        return False
    # urlparse, not url.split("/")[2]: a split leaves the ":port" attached, so any URL with an
    # explicit port would silently fail the allowlist.
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False
    return any(host == h or host.endswith("." + h) for h in _allowed_hosts())


def _split_name(full):
    """ATS forms usually want first/last separately; fall back to a single field if unclear."""
    parts = [p for p in (full or "").split() if p]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def _cv_temp(profile_cv, suffix=".pdf"):
    """Materialise the stored CV on disk so the browser can upload it, then clean it up."""
    if not profile_cv:
        return None
    data, doc = profile_cv
    if not data:
        return None
    name = doc.get("filename") or "cv.pdf"
    ext = Path(name).suffix or suffix
    fd, path = tempfile.mkstemp(suffix=ext, prefix="jp-apply-")
    with open(fd, "wb") as fh:
        fh.write(data)
    return path


def _find_submit(page):
    """Prefer a real submit button; fall back to anything that looks like one."""
    btn = page.locator("button[type=submit], input[type=submit]").first
    try:
        if btn.count() and btn.is_visible() and btn.is_enabled():
            if SUBMIT_RE.search((btn.inner_text() or btn.get_attribute("value") or "").strip()):
                return btn
    except PWTimeout:
        pass
    for el in page.locator("button, input[type=button], a[role=button]").all()[:60]:
        try:
            if not el.is_visible() or not el.is_enabled():
                continue
            if SUBMIT_RE.search((el.inner_text() or el.get_attribute("value") or "").strip()):
                return el
        except PWTimeout:
            continue
    return None


def run_apply(apply_url, profile, cv=None, headless=True, submit=True):
    """Fill and (optionally) submit one application. Returns a structured result; never raises.

    `profile` supplies first_name/last_name/email/phone/linkedin/website/location/cover_letter.
    `cv` is a (bytes, doc) tuple from core.get_file, or None.
    """
    if not _host_ok(apply_url):
        return _ok("unsupported",
                   "This job's application form is on a site we do not automate. Open it manually.",
                   blockers=["unrecognised_ats_host"])

    cv_path = None
    try:
        cv_path = _cv_temp(cv)
    except Exception as e:  # a bad CV must not abort the whole run
        logger.warning("apply: could not stage CV: %s", e)
        cv_path = None

    evidence = {}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=headless, args=["--disable-blink-features=AutomationControlled"])
            ctx = browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                            "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"),
                locale="en-US")
            page = ctx.new_page()
            try:
                page.goto(apply_url, timeout=NAV_TIMEOUT_MS, wait_until="domcontentloaded")
                # ATS forms are often rendered by JS after the shell loads.
                try:
                    page.wait_for_load_state("networkidle", timeout=STEP_TIMEOUT_MS)
                except PWTimeout:
                    pass

                blocked = page.evaluate(_DETECT_BLOCK_JS)
                if blocked.get("captcha"):
                    return _ok("needs_human",
                               "This employer uses a CAPTCHA or bot check that we will not bypass.",
                               blockers=["captcha"] + list(blocked.get("markers") or [])[:5],
                               final_url=page.url, screenshot=_shot(page, evidence))

                found = page.evaluate(_MAP_FIELDS_JS, [list(x) for x in FIELD_SPECS])
                mapping, filled, failed = found.get("mapping", {}), [], {}

                for intent, idx in mapping.items():
                    val = profile.get(intent)
                    if not val:
                        continue
                    loc = page.locator(
                        "input:not([type=hidden]):not([type=submit]):not([type=button]):not([type=file]), textarea"
                    ).nth(idx)
                    try:
                        loc.scroll_into_view_if_needed(timeout=STEP_TIMEOUT_MS)
                        loc.fill(str(val), timeout=STEP_TIMEOUT_MS)
                        filled.append(intent)
                    except Exception as e:
                        failed[intent] = str(e)[:120]

                if cv_path:
                    fi = page.evaluate(_FIND_FILE_JS)
                    if fi is not None and int(fi) >= 0:
                        try:
                            page.locator("input[type=file]").nth(int(fi)).set_input_files(cv_path, timeout=STEP_TIMEOUT_MS)
                            filled.append("cv")
                        except Exception as e:
                            failed["cv"] = str(e)[:120]

                gaps = page.evaluate(_UNFILLED_JS)
                target = _find_submit(page)

                if gaps and not target:
                    return _ok("needs_human",
                               "The form asks for details we could not fill in from your profile.",
                               blockers=["missing_fields:" + ", ".join(gaps[:6])],
                               filled=filled, final_url=page.url, screenshot=_shot(page, evidence))

                if not submit:
                    return _ok("filled",
                               "Form filled in preview mode. Nothing was submitted.",
                               filled=filled, final_url=page.url, screenshot=_shot(page, evidence),
                               blockers=["dry_run"])

                if gaps and target:
                    # A submit with known-blank required fields is a bad application; let the
                    # user finish it rather than sending something incomplete.
                    return _ok("needs_human",
                               "Some required fields need your input before this can be submitted.",
                               blockers=["missing_fields:" + ", ".join(gaps[:6])],
                               filled=filled, final_url=page.url, screenshot=_shot(page, evidence))

                if not target:
                    return _ok("needs_human",
                               "Could not find a submit button on this form.",
                               blockers=["no_submit_button"], filled=filled,
                               final_url=page.url, screenshot=_shot(page, evidence))

                before = page.url
                target.click(timeout=STEP_TIMEOUT_MS)
                try:
                    page.wait_for_load_state("networkidle", timeout=STEP_TIMEOUT_MS)
                except PWTimeout:
                    pass
                page.wait_for_timeout(1200)

                blocked = page.evaluate(_DETECT_BLOCK_JS)
                shot = _shot(page, evidence)
                text = ""
                try:
                    text = page.inner_text("body")[:3000]
                except Exception:
                    pass

                if blocked.get("captcha"):
                    return _ok("needs_human",
                               "The employer showed a CAPTCHA after submitting. Finish it yourself.",
                               blockers=["captcha_after_submit"], filled=filled,
                               final_url=page.url, screenshot=shot)

                if SUCCESS_RE.search(text) or page.url != before:
                    return _ok("submitted", "Application submitted.", filled=filled, submitted=True,
                               final_url=page.url, screenshot=shot)

                return _ok("unknown",
                           "Submitted, but the confirmation could not be verified. Check with the employer.",
                           filled=filled, submitted=True, final_url=page.url, screenshot=shot)
            finally:
                try:
                    ctx.close()
                    browser.close()
                except Exception:
                    pass
    except PWTimeout as e:
        return _ok("failed", f"The application page timed out: {str(e)[:120]}", screenshot=evidence.get("path"))
    except Exception as e:
        logger.exception("apply: run failed")
        return _ok("failed", f"Automation failed: {str(e)[:160]}", screenshot=evidence.get("path"))
    finally:
        if cv_path:
            try:
                Path(cv_path).unlink()
            except OSError:
                pass


def _shot(page, evidence):
    """Best-effort screenshot, written to a temp file for the caller to persist."""
    try:
        fd, path = tempfile.mkstemp(suffix=".png", prefix="jp-apply-evidence-")
        # Close the descriptor immediately: on Windows an open handle keeps the file locked and
        # the caller could never read or delete the evidence afterwards.
        os.close(fd)
        page.screenshot(path=path, full_page=False)
        evidence["path"] = path
        return path
    except Exception:
        return None


async def run_apply_async(*args, **kwargs):
    """Run the blocking browser work off the event loop."""
    return await asyncio.to_thread(run_apply, *args, **kwargs)
