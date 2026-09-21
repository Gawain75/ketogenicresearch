#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECURE_LIBRARY = "https://library.ketogenicresearch.org"

HTML_PATTERNS = (
    (re.compile(r'href=(["\'])library\.html\1', re.I), f'href="{SECURE_LIBRARY}"'),
    (re.compile(r'href=(["\'])/library\.html\1', re.I), f'href="{SECURE_LIBRARY}"'),
    (re.compile(r'href=(["\'])https://ketogenicresearch\.org/library\.html\1', re.I), f'href="{SECURE_LIBRARY}"'),
)

SCRIPT_PATTERNS = (
    (re.compile(r'href=\\"library\.html\\"', re.I), f'href=\\"{SECURE_LIBRARY}\\"'),
    (re.compile(r"href=\\'library\.html\\'", re.I), f"href=\\'{SECURE_LIBRARY}\\'"),
    (re.compile(r'href="library\.html"', re.I), f'href="{SECURE_LIBRARY}"'),
    (re.compile(r"href='library\.html'", re.I), f"href='{SECURE_LIBRARY}'"),
)

def patch_text(path: Path, patterns) -> int:
    text = path.read_text(encoding="utf-8", errors="ignore")
    original = text
    replacements = 0
    for pattern, replacement in patterns:
        text, count = pattern.subn(replacement, text)
        replacements += count
    if text != original:
        path.write_text(text, encoding="utf-8")
    return replacements

def main():
    changed = []

    # Public HTML pages: change every visible link to the protected Library.
    # Keep library.html itself untouched because it remains the source used by
    # the automated Cloudflare build.
    for path in ROOT.rglob("*.html"):
        if ".git" in path.parts:
            continue
        if path.resolve() == (ROOT / "library.html").resolve():
            continue
        count = patch_text(path, HTML_PATTERNS)
        if count:
            changed.append((path.relative_to(ROOT), count))

    # Future-proof scripts/templates that generate navigation or page cards.
    for path in (ROOT / "scripts").glob("*.py"):
        count = patch_text(path, SCRIPT_PATTERNS)
        if count:
            changed.append((path.relative_to(ROOT), count))

    # Also patch JS only where an HTML href literal is embedded.
    script_js = ROOT / "script.js"
    if script_js.exists():
        count = patch_text(script_js, SCRIPT_PATTERNS)
        if count:
            changed.append((script_js.relative_to(ROOT), count))

    print(f"Secure Scientific Library URL: {SECURE_LIBRARY}")
    if not changed:
        print("No link changes required.")
    else:
        for path, count in changed:
            print(f"Updated {path}: {count} link(s)")

    # Verify public homepage and common pages no longer use the old relative URL.
    required_pages = [
        ROOT / "index.html",
        ROOT / "research.html",
        ROOT / "latest.html",
        ROOT / "methodology.html",
        ROOT / "director.html",
        ROOT / "contact.html",
    ]
    for path in required_pages:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if re.search(r'href=(["\'])/?library\.html\1', text, re.I):
            raise SystemExit(f"Old Scientific Library link still present in {path.name}")

    # At least one public page should now expose the protected URL.
    public_hits = 0
    for path in required_pages:
        if path.exists() and SECURE_LIBRARY in path.read_text(encoding="utf-8", errors="ignore"):
            public_hits += 1
    if public_hits == 0:
        raise SystemExit("Protected Library URL was not found on any main public page.")

    print(f"Verification passed on {public_hits} main public page(s).")

if __name__ == "__main__":
    main()
