"""List every registered API route, grouped by module, for documentation.

Docs that list endpoints by hand go stale, so the route table in the README is generated from the
app itself and can be re-checked with this script.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core  # noqa: E402,F401
import server  # noqa: E402

rows = []
for r in server.app.routes:
    path = getattr(r, "path", "")
    methods = getattr(r, "methods", None) or set()
    if not path.startswith("/api"):
        continue
    for m in sorted(methods - {"HEAD", "OPTIONS"}):
        rows.append((m, path))

print(f"{len(rows)} API routes\n")
by_prefix = {}
for m, p in rows:
    seg = p.split("/")[2] if len(p.split("/")) > 2 else "misc"
    by_prefix.setdefault(seg, []).append((m, p))

for seg in sorted(by_prefix):
    print(f"--- /api/{seg} ---")
    for m, p in by_prefix[seg]:
        print(f"  {m:<6} {p}")
    print()
