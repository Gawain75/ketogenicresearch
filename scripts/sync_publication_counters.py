#!/usr/bin/env python3
from pathlib import Path
import json
import re
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "library.html"
HOME = ROOT / "index.html"
SCRIPT = ROOT / "script.js"
TRENDS = ROOT / "data" / "evidence-trends.json"

def canonical_stats():
    data = json.loads(TRENDS.read_text(encoding="utf-8"))
    publications = int(data["global"]["total_unique"])
    areas = int(data.get(
        "clinical_area_count",
        sum(1 for a in data.get("areas", []) if a.get("type") != "thematic")
    ))
    if publications <= 0 or areas <= 0:
        raise RuntimeError("Invalid canonical Library statistics.")
    return publications, areas

def update_html(path: Path, publications: int, areas: int):
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")

    for el in soup.select("[data-publication-count]"):
        el.string = str(publications)

    for el in soup.select("[data-clinical-area-count]"):
        el.string = str(areas)

    for card in soup.select(".update-card"):
        label = card.find("span")
        strong = card.find("strong")
        if not (label and strong):
            continue

        if (label.get("data-en") or "").strip() == "Curated publications":
            strong["data-en"] = str(publications)
            strong["data-it"] = str(publications)
            strong.string = str(publications)

            p = card.find("p")
            if p and "clinical areas" in (p.get("data-en") or "").lower():
                en = f"Across {areas} clinical areas in the Scientific Library."
                it = f"In {areas} aree cliniche della Biblioteca Scientifica."
                p["data-en"] = en
                p["data-it"] = it
                p.string = en

    path.write_text(str(soup), encoding="utf-8")
    print(f"Updated {path.name}: {publications} unique publications; {areas} clinical areas")

def update_script(publications: int, areas: int):
    js = SCRIPT.read_text(encoding="utf-8")
    js = re.sub(
        r"(const KR_LIBRARY_STATS = \{\s*publications:\s*)\d+",
        rf"\g<1>{publications}",
        js,
    )
    js = re.sub(
        r"(clinicalAreas:\s*)\d+",
        rf"\g<1>{areas}",
        js,
        count=1,
    )
    SCRIPT.write_text(js, encoding="utf-8")

def main():
    publications, areas = canonical_stats()
    update_html(LIBRARY, publications, areas)
    update_html(HOME, publications, areas)
    update_script(publications, areas)

if __name__ == "__main__":
    main()
