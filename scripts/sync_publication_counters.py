#!/usr/bin/env python3
from pathlib import Path
import re
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "library.html"
HOME = ROOT / "index.html"

LABELS = ("Pubblicazioni selezionate", "Selected publications")

def count_library_records():
    html = LIBRARY.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("article.folder-paper")
    if cards:
        return len(cards)

    pmids = {
        (el.get("data-pmid") or "").strip()
        for el in soup.select("[data-pmid]")
        if (el.get("data-pmid") or "").strip()
    }
    if pmids:
        return len(pmids)

    raise RuntimeError("Unable to identify Scientific Library publication records.")

def replace_counter(path, total):
    html = path.read_text(encoding="utf-8")

    for label in LABELS:
        # Match a number in the same nearby stat block before the label.
        pattern = re.compile(
            rf'(?P<before><(?:div|span|strong|p|h[1-6])[^>]*>\s*)'
            rf'\d{{1,8}}'
            rf'(?P<after>\s*</(?:div|span|strong|p|h[1-6])>[\s\S]{{0,220}}?{re.escape(label)})',
            re.I,
        )
        updated, n = pattern.subn(
            lambda m: f'{m.group("before")}{total}{m.group("after")}',
            html,
            count=1,
        )
        if n:
            path.write_text(updated, encoding="utf-8")
            print(f"Updated {path.name}: {total}")
            return

    raise RuntimeError(f"Publication counter not found in {path.name}")

def main():
    total = count_library_records()
    print(f"Scientific Library records: {total}")
    replace_counter(LIBRARY, total)
    replace_counter(HOME, total)

if __name__ == "__main__":
    main()
