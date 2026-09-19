#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TARGETS = [
    "index.html",
    "research.html",
    "library.html",
    "latest.html",
    "methodology.html",
    "director.html",
    "contact.html",
]

ARTICLES_LINK = '''
      <a
        data-en="Articles"
        data-it="Articoli"
        href="articles.html"
      >
        Articles
      </a>
'''.rstrip()

def add_articles_link(path: Path) -> bool:
    if not path.exists():
        print(f"Skip missing file: {path.name}")
        return False

    text = path.read_text(encoding="utf-8")

    if re.search(r"href=[\"']articles\.html[\"']", text):
        print(f"Already present: {path.name}")
        return False

    pattern = re.compile(
        r"(<a\b[^>]*href=[\"']latest\.html[\"'][^>]*>.*?</a>)",
        re.IGNORECASE | re.DOTALL
    )
    match = pattern.search(text)

    if not match:
        raise RuntimeError(
            f"Could not find latest.html navigation link in {path.name}"
        )

    insertion = match.group(1) + "\n\n" + ARTICLES_LINK
    text = text[:match.start()] + insertion + text[match.end():]

    path.write_text(text, encoding="utf-8")
    print(f"Updated: {path.name}")
    return True

def main() -> None:
    changed = 0

    for name in TARGETS:
        if add_articles_link(ROOT / name):
            changed += 1

    print(f"Articles menu update complete. Files changed: {changed}")

if __name__ == "__main__":
    main()
