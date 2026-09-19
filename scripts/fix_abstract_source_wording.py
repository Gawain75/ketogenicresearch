#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DRAFTS = ROOT / "articles-drafts"

REPLACEMENTS = {
    "Interpretation is based on the PubMed abstract; the full text was not available.":
        "This note is based on the PubMed abstract.",
    "L'interpretazione si basa sull'abstract di PubMed; il testo completo non era disponibile.":
        "Questa nota si basa sull'abstract di PubMed.",
    "L’interpretazione si basa sull’abstract di PubMed; il testo completo non era disponibile.":
        "Questa nota si basa sull’abstract di PubMed.",
}

def main():
    changed = 0

    for path in sorted(DRAFTS.glob("*.md")):
        old = path.read_text(encoding="utf-8")
        new = old

        for source, replacement in REPLACEMENTS.items():
            new = new.replace(source, replacement)

        if new != old:
            path.write_text(new, encoding="utf-8")
            changed += 1
            print(f"Updated: {path.name}")

    print(f"Articles updated: {changed}")

if __name__ == "__main__":
    main()
