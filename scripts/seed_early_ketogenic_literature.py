#!/usr/bin/env python3
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from urllib.parse import quote

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "library.html"

RECORDS = [
    {
        "year": 1921,
        "title": "The Effect of Ketonemia on the Course of Epilepsy",
        "authors": "Wilder RM",
        "journal": "Mayo Clinic Bulletin",
        "citation": "1921;2:307-308",
        "doi": "",
    },
    {
        "year": 1921,
        "title": "High Fat Diets in Epilepsy",
        "authors": "Wilder RM",
        "journal": "Mayo Clinic Bulletin",
        "citation": "1921;2:308",
        "doi": "",
    },
    {
        "year": 1924,
        "title": "The Ketogenic Diet in the Treatment of Epilepsy: A Preliminary Report",
        "authors": "Peterman MG",
        "journal": "American Journal of Diseases of Children",
        "citation": "1924;28:28-33",
        "doi": "10.1001/archpedi.1924.04120190031004",
    },
    {
        "year": 1925,
        "title": "The Ketogenic Diet in Epilepsy",
        "authors": "Peterman MG",
        "journal": "JAMA",
        "citation": "1925;84:1979-1983",
        "doi": "10.1001/jama.1925.02660520007003",
    },
    {
        "year": 1926,
        "title": "The Ketogenic Diet in the Treatment of Idiopathic Epilepsy",
        "authors": "Talbot FB, Metcalf K, Moriarty ME",
        "journal": "American Journal of Diseases of Children",
        "citation": "1926;32:316-318",
        "doi": "",
    },
]

def norm(value: str) -> str:
    value = re.sub(r"^\s*\d+\.\s*", "", value or "")
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "", value.lower())

def make_article(soup: BeautifulSoup, rec: dict):
    title = rec["title"]
    search = " ".join([
        title, rec["authors"], rec["journal"], str(rec["year"]),
        "ketogenic diet epilepsy historical classic"
    ]).lower()

    article = soup.new_tag("article")
    article["class"] = ["folder-paper", "historical-paper"]
    article["data-evidence"] = "historical"
    article["data-year"] = str(rec["year"])
    article["data-search"] = search

    h4 = soup.new_tag("h4")
    h4["data-en"] = title
    h4["data-it"] = title
    h4.string = title
    article.append(h4)

    p = soup.new_tag("p")
    p["data-en"] = (
        f'{rec["authors"]}. {rec["journal"]}. {rec["citation"]}. '
        "Historical ketogenic-diet reference."
    )
    p["data-it"] = (
        f'{rec["authors"]}. {rec["journal"]}. {rec["citation"]}. '
        "Riferimento storico sulla dieta chetogenica."
    )
    p.string = p["data-en"]
    article.append(p)

    links = soup.new_tag("div")
    links["class"] = ["paper-links"]

    if rec["doi"]:
        a = soup.new_tag("a", href="https://doi.org/" + rec["doi"])
        a["target"] = "_blank"
        a["rel"] = "noopener"
        a["data-en"] = "DOI ↗"
        a["data-it"] = "DOI ↗"
        a.string = "DOI ↗"
        links.append(a)
    else:
        # No original PMID/DOI is available for these early Mayo Clinic Bulletin
        # records. A Scholar query is supplied only as a discovery aid.
        a = soup.new_tag(
            "a",
            href="https://scholar.google.com/scholar?q=" + quote(
                f'"{title}" {rec["authors"]} {rec["year"]}'
            ),
        )
        a["target"] = "_blank"
        a["rel"] = "noopener"
        a["data-en"] = "Bibliographic search ↗"
        a["data-it"] = "Ricerca bibliografica ↗"
        a.string = "Bibliographic search ↗"
        links.append(a)

    article.append(links)
    return article

def main():
    soup = BeautifulSoup(LIBRARY.read_text(encoding="utf-8"), "html.parser")

    folder = soup.select_one("details#epilepsy")
    if not folder:
        raise RuntimeError("Epilepsy folder not found in library.html")

    curated = folder.select_one(".folder-curated")
    if not curated:
        raise RuntimeError("Epilepsy .folder-curated container not found")

    existing_titles = set()
    for h4 in curated.select("article.folder-paper h4"):
        existing_titles.add(norm(h4.get("data-en") or h4.get_text(" ", strip=True)))

    added = 0
    for rec in reversed(RECORDS):
        if norm(rec["title"]) in existing_titles:
            continue
        curated.insert(0, make_article(soup, rec))
        existing_titles.add(norm(rec["title"]))
        added += 1

    # Keep visible numbering coherent if the library uses numbered cards.
    for i, h4 in enumerate(curated.select("article.folder-paper h4"), 1):
        en = re.sub(r"^\s*\d+\.\s*", "", h4.get("data-en") or h4.get_text(" ", strip=True)).strip()
        it = re.sub(r"^\s*\d+\.\s*", "", h4.get("data-it") or en).strip()
        h4["data-en"] = f"{i}. {en}"
        h4["data-it"] = f"{i}. {it}"
        h4.string = f"{i}. {en}"

    LIBRARY.write_text(str(soup), encoding="utf-8")
    print(f"Historical ketogenic records added: {added}")
    print("Earliest seeded publication year: 1921")

if __name__ == "__main__":
    main()
