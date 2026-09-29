"""Check the bilingual layer: duplicate keys, missing Arabic, and unwrapped copy.

Three real defects this catches, all of which fail silently at runtime:

1. A duplicate key in the ar.js object literal. JS keeps the last one and says nothing, so the
   first translation is dead code and nobody finds out.
2. A t("...") key with no Arabic entry. The English string is rendered to an Arabic user, which
   is the single most visible way this app can look broken.
3. User-facing JSX text or a placeholder/aria-label that bypasses t() entirely.

Reports; it does not rewrite, because whether a string is copy or a data value (a plan id, a file
path, a brand name) is a judgement call. Run: .\\.venv\\Scripts\\python.exe -X utf8 scripts\\check_i18n.py
"""
import re
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"
AR_FILE = SRC / "lib" / "ar.js"

KV = re.compile(r'"((?:[^"\\]|\\.)*)"\s*:\s*"((?:[^"\\]|\\.)*)"')
T_CALL = re.compile(r"""\bt\(\s*(?:"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)')""")
# Text sitting directly between tags.
TEXT_NODE = re.compile(r">\s*([A-Za-z][A-Za-z0-9 ,.'’&!?()/\-]{3,})\s*<")
STRING_PROP = re.compile(r'\b(placeholder|title|aria-label|alt)\s*=\s*"([^"]{3,})"')

problems = 0

# ---------- 1. duplicate keys ----------
pairs = KV.findall(AR_FILE.read_text(encoding="utf-8"))
first, dups = {}, []
for k, v in pairs:
    if k in first:
        dups.append((k, first[k], v))
    else:
        first[k] = v
if dups:
    problems += len(dups)
    print(f"[FAIL] {len(dups)} duplicate key(s) in ar.js -- the first is silently overridden")
    for k, a, b in dups:
        print(f"       {k!r}: {a!r} then {b!r}")
else:
    print(f"[PASS] no duplicate keys ({len(pairs)} pairs)")

# ---------- 2. missing Arabic ----------
used = {}
for p in list(SRC.rglob("*.jsx")) + list(SRC.rglob("*.js")):
    if p.name == "ar.js":
        continue
    rel = p.relative_to(SRC).as_posix()
    for m in T_CALL.finditer(p.read_text(encoding="utf-8")):
        used.setdefault(m.group(1) or m.group(2), set()).add(rel)
missing = sorted(k for k in used if k not in first)
if missing:
    problems += len(missing)
    print(f"[FAIL] {len(missing)} t() key(s) with no Arabic translation")
    for k in missing:
        print(f"       {k!r}  [{', '.join(sorted(used[k])[:2])}]")
else:
    print(f"[PASS] every t() key has Arabic ({len(used)} keys)")

# ---------- 3. copy that bypasses t() ----------
# Skipped: brand names, and shadcn/ui internals whose labels are library-owned.
BRAND = {"JobPilot", "Gmail", "WhatsApp", "Careerjet"}
# Deliberately left in Latin script even in the Arabic UI, and why.
#   format hints   -- "name@example.com" and phone masks are conventions, not prose
#   raw data value -- mirrors a stored plan id
#   file path      -- a real path, must match the repo
#   numeric/short  -- scores and units
LANG_NEUTRAL = {
    "you@example.com", "coach@example.com", "+9665XXXXXXXX", "premium",
    "backend/eval/cases.json",
}
unwrapped = []
for p in sorted(SRC.rglob("*.jsx")):
    rel = p.relative_to(SRC).as_posix()
    if rel.startswith("components/ui/"):
        continue  # vendored shadcn primitives
    for i, line in enumerate(p.read_text(encoding="utf-8").split("\n"), 1):
        for rx, kind, gidx in ((TEXT_NODE, "text", 1), (STRING_PROP, "prop", 2)):
            for m in rx.finditer(line):
                s = m.group(gidx).strip()
                if not s or s in BRAND or s in LANG_NEUTRAL or s.isupper() and len(s) <= 4:
                    continue
                # A line that already routes some copy through t() is fine.
                if "t(" in line:
                    continue
                unwrapped.append((rel, i, kind, s))
if unwrapped:
    problems += len(unwrapped)
    print(f"[WARN] {len(unwrapped)} user-facing string(s) not wrapped in t()")
    for rel, i, kind, s in unwrapped:
        print(f"       {rel}:{i}  {kind}: {s!r}")
else:
    print("[PASS] no unwrapped user-facing strings")

print()
print("RESULT:", "PASS" if not problems else f"FAIL ({problems})")
sys.exit(0 if not problems else 1)
