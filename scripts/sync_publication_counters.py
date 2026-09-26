#!/usr/bin/env python3
from pathlib import Path
import re
import unicodedata
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "library.html"
HOME = ROOT / "index.html"
SCRIPT = ROOT / "script.js"

def publication_key(card):
    h4 = card.find("h4")
    title = (h4.get("data-en") if h4 else "") or (h4.get_text(" ", strip=True) if h4 else "")
    title = re.sub(r"^\s*\d+\.\s*", "", title)
    title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().lower()
    title = re.sub(r"[^a-z0-9]+", "", title)
    if title:
        return "title:" + title
    pmid = (card.get("data-pmid") or "").strip()
    if pmid:
        return "pmid:" + pmid
    doi = (card.get("data-doi") or "").strip().lower()
    if doi:
        return "doi:" + doi
    return None

def library_stats():
    soup = BeautifulSoup(LIBRARY.read_text(encoding="utf-8"), "html.parser")
    keys = {k for card in soup.select("article.folder-paper") if (k := publication_key(card))}
    areas = len(soup.select("details.library-folder"))
    if not keys:
        raise RuntimeError("Unable to identify Scientific Library publication records.")
    return len(keys), areas

def update_html(path: Path, publications: int, areas: int):
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    for el in soup.select("[data-publication-count]"):
        el.string = str(publications)
    for el in soup.select("[data-clinical-area-count]"):
        el.string = str(areas)

    # Homepage update card is intentionally not a data-publication-count element.
    for card in soup.select(".update-card"):
        label = card.find("span")
        strong = card.find("strong")
        if label and strong and (label.get("data-en") or "").strip() == "Curated publications":
            strong["data-en"] = str(publications)
            strong["data-it"] = str(publications)
            strong.string = str(publications)

    path.write_text(str(soup), encoding="utf-8")
    print(f"Updated {path.name}: {publications} unique publications; {areas} clinical areas")

def update_script(publications: int, areas: int):
    js = SCRIPT.read_text(encoding="utf-8")
    js = re.sub(r"(const KR_LIBRARY_STATS = \{\s*publications:\s*)\d+", rf"\g<1>{publications}", js)
    js = re.sub(r"(clinicalAreas:\s*)\d+", rf"\g<1>{areas}", js, count=1)
    SCRIPT.write_text(js, encoding="utf-8")

def main():
    publications, areas = library_stats()
    update_html(LIBRARY, publications, areas)
    update_html(HOME, publications, areas)
    update_script(publications, areas)

if __name__ == "__main__":
    main()
