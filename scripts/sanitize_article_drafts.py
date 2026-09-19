#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DRAFTS = ROOT / "articles-drafts"

REPLACEMENTS = {
    "Interpretation is based on the PubMed abstract; the full text was not available to this automated workflow.":
        "Interpretation is based on the PubMed abstract; the full text was not available.",
    "L'interpretazione si basa sull'abstract di PubMed; il testo completo non era disponibile per questo flusso di lavoro automatizzato.":
        "L'interpretazione si basa sull'abstract di PubMed; il testo completo non era disponibile.",
    "L’interpretazione si basa sull’abstract di PubMed; il testo completo non era disponibile per questo flusso di lavoro automatizzato.":
        "L’interpretazione si basa sull’abstract di PubMed; il testo completo non era disponibile.",
}

def main():
    changed = 0
    for path in sorted(DRAFTS.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        new = text
        for old, replacement in REPLACEMENTS.items():
            new = new.replace(old, replacement)
        if new != text:
            path.write_text(new, encoding="utf-8")
            changed += 1
            print(f"Cleaned: {path.name}")
    print(f"Drafts cleaned: {changed}")

if __name__ == "__main__":
    main()
