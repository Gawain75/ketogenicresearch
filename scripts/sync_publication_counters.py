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
    thematic = int(data.get(
        "thematic_collection_count",
        sum(1 for a in data.get("areas", []) if a.get("type") == "thematic")
    ))
    if publications <= 0 or areas <= 0 or thematic < 0:
        raise RuntimeError("Invalid canonical Library statistics.")
    return publications, areas, thematic

def update_html(path: Path, publications: int, areas: int, thematic: int):
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")

    for el in soup.select("[data-publication-count]"):
        el.string = str(publications)

    for el in soup.select("[data-clinical-area-count]"):
        el.string = str(areas)

    for el in soup.select("[data-thematic-collection-count]"):
        el.string = str(thematic)

    result_count = soup.select_one("#libraryResultCount")
    if result_count:
        en = (
            f"{publications:,} unique publications indexed across "
            f"{areas} clinical areas"
            + (f" + {thematic} thematic collection" if thematic == 1 else
               f" + {thematic} thematic collections" if thematic else "")
        )
        it = (
            f"{publications:,}".replace(",", ".")
            + f" pubblicazioni uniche indicizzate in {areas} aree cliniche"
            + (f" + {thematic} raccolta tematica" if thematic == 1 else
               f" + {thematic} raccolte tematiche" if thematic else "")
        )
        result_count["data-en"] = en
        result_count["data-it"] = it
        result_count.string = en

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
                en = (
                    f"Indexed across {areas} clinical areas"
                    + (f" and {thematic} thematic collection" if thematic == 1 else
                       f" and {thematic} thematic collections" if thematic else "")
                    + " in the Scientific Library."
                )
                it = (
                    f"Indicizzate in {areas} aree cliniche"
                    + (f" e {thematic} raccolta tematica" if thematic == 1 else
                       f" e {thematic} raccolte tematiche" if thematic else "")
                    + " della Biblioteca Scientifica."
                )
                p["data-en"] = en
                p["data-it"] = it
                p.string = en

    path.write_text(str(soup), encoding="utf-8")
    print(f"Updated {path.name}: {publications} unique publications; {areas} clinical areas; {thematic} thematic collections")

def update_script(publications: int, areas: int, thematic: int):
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
    js = re.sub(
        r"(thematicCollections:\s*)\d+",
        rf"\g<1>{thematic}",
        js,
        count=1,
    )
    SCRIPT.write_text(js, encoding="utf-8")

def main():
    publications, areas, thematic = canonical_stats()
    update_html(LIBRARY, publications, areas, thematic)
    update_html(HOME, publications, areas, thematic)
    update_script(publications, areas, thematic)

if __name__ == "__main__":
    main()
