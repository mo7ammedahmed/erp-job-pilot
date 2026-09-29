"""Sanity-check README.md: no replacement characters, balanced code fences, anchors intact.

Replacement characters (U+FFFD) are the signature of text that was corrupted on the way in, and they
are invisible in a diff, so they are worth asserting on.
"""
import pathlib
import re
import sys

README = pathlib.Path(__file__).resolve().parents[2] / "README.md"
text = README.read_text(encoding="utf-8")

bad_chars = text.count(chr(0xFFFD))
fences = text.count("```")
lines = text.splitlines()

# Table rows must have a consistent column count within each table.
issues = []
if bad_chars:
    issues.append(f"{bad_chars} U+FFFD replacement character(s)")
if fences % 2:
    issues.append(f"unbalanced code fences ({fences})")

for a, b in re.findall(r"\[([^\]]+)\]\(#([^)]+)\)", text):
    if f'name="{b}"' not in text and f'id="{b}"' not in text:
        issues.append(f"link target #{b} has no anchor")

table = []
for i, line in enumerate(lines, 1):
    if line.startswith("|"):
        table.append((i, line.count("|")))
    else:
        if table:
            widths = {w for _, w in table}
            if len(widths) > 1:
                issues.append(f"table ending line {table[0][0]}: inconsistent columns {sorted(widths)}")
            table = []

print(f"README: {len(lines)} lines, {fences // 2} code blocks, {bad_chars} corrupt chars")
if issues:
    print("ISSUES:")
    for x in issues:
        print(f"  - {x}")
    sys.exit(1)
print("OK")
