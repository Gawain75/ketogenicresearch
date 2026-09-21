#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
CANONICAL = "https://library.ketogenicresearch.org/library"

if not INDEX.exists():
    raise SystemExit("index.html not found")

html = INDEX.read_text(encoding="utf-8", errors="replace")

# Normalize every Scientific Library href on the homepage, including malformed
# repetitions such as /library/librarylibrary.
patterns = [
    r'href=(["\'])https://library\.ketogenicresearch\.org(?:/library[^"\']*)?/?\1',
    r'href=(["\'])https://ketogenicresearch\.org/library(?:\.html)?\1',
    r'href=(["\'])(?:\./)?library\.html\1',
    r'href=(["\'])/library(?:\.html)?\1',
]

for pattern in patterns:
    html = re.sub(pattern, f'href="{CANONICAL}"', html, flags=re.I)

# Extra guard for the exact malformed URL currently seen on Home.
html = html.replace(
    "https://library.ketogenicresearch.org/library/librarylibrary",
    CANONICAL
)

INDEX.write_text(html, encoding="utf-8")

# Verification
bad = [
    "library/librarylibrary",
    "https://ketogenicresearch.org/library.html",
    'href="library.html"',
]
for item in bad:
    if item in html:
        raise SystemExit(f"Legacy/malformed Library link remains: {item}")

if CANONICAL not in html:
    raise SystemExit("Canonical Scientific Library link missing from index.html")

print("Homepage Scientific Library link normalized to:")
print(CANONICAL)
