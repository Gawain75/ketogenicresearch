#!/usr/bin/env python3
from pathlib import Path
import json
import re
from bs4 import BeautifulSoup, Comment, NavigableString

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
    raw = path.read_text(encoding="utf-8")

    # Remove reconciliation markers if they were accidentally written as
    # visible/escaped text instead of a real HTML comment.
    raw = re.sub(
        r"(?:&lt;|<)!--\s*Bibliographic link reconciliation[^\\n<]*(?:--&gt;|-->)",
        "",
        raw,
        flags=re.I,
    )

    soup = BeautifulSoup(raw, "html.parser")

    # Remove any matching real HTML comment too.
    for node in soup.find_all(string=lambda s: isinstance(s, Comment)):
        if "Bibliographic link reconciliation" in str(node):
            node.extract()

    # Remove any legacy plain text node containing the marker.
    for node in soup.find_all(string=True):
        if isinstance(node, Comment):
            continue
        value = str(node)
        if "Bibliographic link reconciliation" in value:
            cleaned = re.sub(
                r"<!--\s*Bibliographic link reconciliation.*?-->",
                "",
                value,
                flags=re.I | re.S,
            )
            cleaned = re.sub(
                r"Bibliographic link reconciliation[^\\n]*",
                "",
                cleaned,
                flags=re.I,
            )
            if cleaned.strip():
                node.replace_with(cleaned)
            else:
                node.extract()

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

    # Force desktop and mobile browsers to fetch the same current script.js.
    # The query string is derived from the current canonical publication count.
    script_version = f"stats-{publications}-{areas}"
    for tag in soup.find_all("script", src=True):
        src = tag.get("src") or ""
        if re.search(r"(?:^|/)script\\.js(?:\\?.*)?$", src):
            base = src.split("?", 1)[0]
            tag["src"] = f"{base}?v={script_version}"

    path.write_text(str(soup), encoding="utf-8")
    print(
        f"Updated {path.name}: {publications} unique publications; "
        f"{areas} clinical areas; cache key {script_version}"
    )

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
