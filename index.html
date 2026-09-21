#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
DRAFTS = ROOT / "articles-drafts"

def clean(text: str) -> str:
    # Keep source-note prose, but remove repeated standalone identifier lines.
    text = re.sub(r'(?m)^PMID:\s*\S+\s{0,2}$', '', text)
    text = re.sub(r'(?m)^DOI:\s*\S+\s{0,2}$', '', text)
    text = re.sub(r'(?m)^PMCID:\s*(?:Not available|Non disponibile|\S+)\s*$', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip() + '\n'

def main():
    changed = 0
    for path in DRAFTS.glob("*.md"):
        old = path.read_text(encoding="utf-8")
        new = clean(old)
        if new != old:
            path.write_text(new, encoding="utf-8")
            changed += 1
            print(f"Cleaned {path.name}")
    print(f"Drafts cleaned: {changed}")

if __name__ == "__main__":
    main()
