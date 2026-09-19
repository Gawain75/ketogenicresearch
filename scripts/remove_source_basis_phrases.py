#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
DRAFTS = ROOT / "articles-drafts"

PATTERNS = [
    r"(?i)\bThis note is based on the PubMed abstract\.\s*",
    r"(?i)\bInterpretation is based on the PubMed abstract; the full text was not available\.\s*",
    r"(?i)\bInterpretation is based on the PubMed abstract; the full text was not available to this automated workflow\.\s*",
    r"(?i)\bQuesta nota si basa sull['’]abstract di PubMed\.\s*",
    r"(?i)\bL['’]interpretazione si basa sull['’]abstract di PubMed; il testo completo non era disponibile\.\s*",
    r"(?i)\bL['’]interpretazione si basa sull['’]abstract di PubMed; il testo completo non era disponibile per questo flusso di lavoro automatizzato\.\s*",
]

def main():
    changed = 0
    for path in sorted(DRAFTS.glob("*.md")):
        old = path.read_text(encoding="utf-8")
        new = old
        for pattern in PATTERNS:
            new = re.sub(pattern, "", new)
        new = re.sub(r"\n{3,}", "\n\n", new)
        if new != old:
            path.write_text(new, encoding="utf-8")
            changed += 1
            print(f"Cleaned: {path.name}")
    print(f"Drafts cleaned: {changed}")

if __name__ == "__main__":
    main()
