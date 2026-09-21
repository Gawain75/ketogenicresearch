#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = "https://library.ketogenicresearch.org/library"

targets = [ROOT / "articles.html"]
articles_dir = ROOT / "articles"
if articles_dir.exists():
    targets += list(articles_dir.glob("*.html"))

changed = []
for path in targets:
    if not path.exists():
        continue
    text = path.read_text(encoding="utf-8", errors="replace")
    new = text

    # Every legacy/public Library link becomes the canonical protected route.
    new = re.sub(
        r'href=(["\'])(?:\.\./)?library\.html\1',
        f'href="{CANONICAL}"',
        new,
        flags=re.I,
    )
    new = re.sub(
        r'href=(["\'])https://ketogenicresearch\.org/library\.html\1',
        f'href="{CANONICAL}"',
        new,
        flags=re.I,
    )
    new = re.sub(
        r'href=(["\'])https://library\.ketogenicresearch\.org/library\.html\1',
        f'href="{CANONICAL}"',
        new,
        flags=re.I,
    )

    if new != text:
        path.write_text(new, encoding="utf-8")
        changed.append(path.relative_to(ROOT).as_posix())

# Also future-proof the generator.
renderer = ROOT / "scripts" / "render_articles.py"
if renderer.exists():
    text = renderer.read_text(encoding="utf-8", errors="replace")
    new = re.sub(
        r'href=(["\'])(?:\.\./)?library\.html\1',
        f'href="{CANONICAL}"',
        text,
        flags=re.I,
    )
    if new != text:
        renderer.write_text(new, encoding="utf-8")
        changed.append("scripts/render_articles.py")

# Verify current Articles index specifically.
idx = ROOT / "articles.html"
if idx.exists():
    text = idx.read_text(encoding="utf-8", errors="replace")
    if 'https://ketogenicresearch.org/library.html' in text or re.search(r'href=(["\'])library\.html\1', text, re.I):
        raise SystemExit("articles.html still contains a legacy Scientific Library link")

print("Updated:")
for item in changed:
    print(" -", item)
