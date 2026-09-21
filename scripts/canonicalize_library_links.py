#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = "https://library.ketogenicresearch.org/library"

EXCLUDED_HTML = {
    "library.html",          # source used to build the protected library
    "library-access.html",   # legacy/auth page, not public navigation
    "reset-password.html",
}

def patch_text(text: str) -> tuple[str, int]:
    original = text

    # Normalize every known public link form.
    replacements = [
        ("https://library.ketogenicresearch.org/library.html", CANONICAL),
        ("https://library.ketogenicresearch.org/", CANONICAL),
        ("https://library.ketogenicresearch.org", CANONICAL),
        ("https://ketogenicresearch.org/library.html", CANONICAL),
    ]
    for old, new in replacements:
        text = text.replace(old, new)

    # Public relative links.
    text = re.sub(
        r'href=(["\'])(?:\./)?library\.html\1',
        f'href="{CANONICAL}"',
        text,
        flags=re.I,
    )
    text = re.sub(
        r'href=(["\'])/library(?:\.html)?\1',
        f'href="{CANONICAL}"',
        text,
        flags=re.I,
    )

    return text, int(text != original)

changed = []

# Current public pages.
for path in ROOT.glob("*.html"):
    if path.name in EXCLUDED_HTML:
        continue
    text = path.read_text(encoding="utf-8", errors="replace")
    new, did = patch_text(text)
    if did:
        path.write_text(new, encoding="utf-8")
        changed.append(path.relative_to(ROOT).as_posix())

# Fix source scripts/templates that can regenerate public navigation.
for path in (ROOT / "scripts").glob("*.py"):
    text = path.read_text(encoding="utf-8", errors="replace")
    new, did = patch_text(text)

    # Keep the dedicated redirect script future-proof.
    if path.name == "point_to_protected_library.py":
        new = re.sub(
            r'SECURE_LIBRARY\s*=\s*["\'][^"\']+["\']',
            f'SECURE_LIBRARY = "{CANONICAL}"',
            new,
        )
        did = int(new != text)

    if did:
        path.write_text(new, encoding="utf-8")
        changed.append(path.relative_to(ROOT).as_posix())

# Sitemap: if the protected Library is listed, use the canonical route.
sitemap = ROOT / "sitemap.xml"
if sitemap.exists():
    text = sitemap.read_text(encoding="utf-8", errors="replace")
    new, did = patch_text(text)
    if did:
        sitemap.write_text(new, encoding="utf-8")
        changed.append("sitemap.xml")

# Verify no public HTML page still points to the root/login or .html route.
bad = []
for path in ROOT.glob("*.html"):
    if path.name in EXCLUDED_HTML:
        continue
    text = path.read_text(encoding="utf-8", errors="replace")
    if "https://library.ketogenicresearch.org/library.html" in text:
        bad.append(f"{path.name}: library.html")
    # exact root-domain href, with or without trailing slash
    if re.search(r'href=["\']https://library\.ketogenicresearch\.org/?["\']', text, re.I):
        bad.append(f"{path.name}: root domain")

if bad:
    raise SystemExit("Non-canonical Library links remain:\n" + "\n".join(bad))

print("Canonical Scientific Library URL:", CANONICAL)
print("Updated files:")
for name in changed:
    print(" -", name)
