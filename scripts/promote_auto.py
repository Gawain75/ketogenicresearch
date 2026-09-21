#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

from pubmed_record_guard import fetch_pubmed_records, norm_doi, norm_title, verified_record

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "review-queue.json"
LIBRARY = ROOT / "library.html"
INDEX = ROOT / "index.html"
SCRIPT = ROOT / "script.js"


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default



def unique_publication_count(soup: BeautifulSoup) -> int:
    keys = set()
    for card in soup.select("article.folder-paper"):
        h4 = card.find("h4")
        title = norm_title(
            (h4.get("data-en") if h4 else "")
            or (h4.get_text(" ", strip=True) if h4 else "")
        )
        pmid = str(card.get("data-pmid") or "").strip()
        doi = norm_doi(str(card.get("data-doi") or ""))
        if title:
            keys.add("title:" + title)
        elif pmid:
            keys.add("pmid:" + pmid)
        elif doi:
            keys.add("doi:" + doi)
    return len(keys)

def main() -> None:
    queue = load_json(QUEUE, {"records": []})
    candidates = [
        r for r in queue.get("records", [])
        if r.get("auto_eligible") and r.get("pmid")
    ]

    pubmed_map = fetch_pubmed_records(
        [str(r.get("pmid")) for r in candidates]
    )

    soup = BeautifulSoup(LIBRARY.read_text(encoding="utf-8"), "html.parser")

    sections = {}
    for details in soup.select("details.library-folder"):
        strong = details.select_one("summary strong")
        if strong:
            title = strong.get("data-en") or strong.get_text(" ", strip=True)
            sections[title] = details

    existing_titles = {
        norm_title(h.get("data-en") or h.get_text(" ", strip=True))
        for h in soup.select("article.folder-paper h4")
    }
    existing_pmids = {
        str(a.get("data-pmid") or "").strip()
        for a in soup.select("article.folder-paper")
        if a.get("data-pmid")
    }
    existing_dois = {
        norm_doi(a.get("data-doi") or "")
        for a in soup.select("article.folder-paper")
        if a.get("data-doi")
    }

    promoted = 0
    cards_added = 0

    for raw in candidates:
        record = verified_record(raw, pubmed_map)
        if not record:
            continue

        pmid = record["pmid"]
        doi = norm_doi(record.get("doi") or "")
        title = record.get("title") or ""
        title_key = norm_title(title)

        if (
            title_key in existing_titles
            or pmid in existing_pmids
            or (doi and doi in existing_dois)
        ):
            continue

        valid_areas = [
            a for a in (record.get("areas") or [])
            if a in sections
        ]
        if not valid_areas:
            print(f"Skipping PMID {pmid}: no valid curated area.")
            continue

        for area in valid_areas:
            details = sections[area]
            wrap = details.select_one(".folder-curated")
            if not wrap:
                continue

            current = len(details.select("article.folder-paper"))
            art = soup.new_tag("article", attrs={"class": "folder-paper"})
            art["data-pmid"] = pmid
            if doi:
                art["data-doi"] = doi
            art["data-evidence"] = (
                record.get("evidence_type") or "Other"
            ).lower().replace(" ", "-")
            art["data-year"] = str((record.get("date") or "")[:4] or "unknown")
            art["data-search"] = (
                f"{title} {area} {record.get('journal','')} "
                f"{' '.join(record.get('authors') or [])}"
            ).lower()

            level = soup.new_tag("div", attrs={"class": "evidence-level"})
            level["data-en"] = record.get("evidence_type") or "Other"
            level["data-it"] = (
                record.get("evidence_type_it")
                or record.get("evidence_type")
                or "Altro"
            )
            level.string = level["data-en"]
            art.append(level)

            h4 = soup.new_tag("h4")
            h4["data-en"] = f"{current + 1}. {title}"
            h4["data-it"] = f"{current + 1}. {title}"
            h4.string = h4["data-en"]
            art.append(h4)

            meta = soup.new_tag("p")
            authors = ", ".join(record.get("authors") or [])
            journal = record.get("journal") or ""
            date = record.get("date") or ""
            meta.string = " · ".join(x for x in [authors, journal, date] if x)
            art.append(meta)

            links = soup.new_tag("div", attrs={"class": "paper-links"})

            a = soup.new_tag(
                "a",
                href=record["pubmed_url"],
                target="_blank",
                rel="noopener",
            )
            a["data-en"] = a["data-it"] = "PubMed ↗"
            a.string = "PubMed ↗"
            links.append(a)

            if record.get("doi_url"):
                a = soup.new_tag(
                    "a",
                    href=record["doi_url"],
                    target="_blank",
                    rel="noopener",
                )
                a["data-en"] = a["data-it"] = "DOI ↗"
                a.string = "DOI ↗"
                links.append(a)

            if record.get("pmc_url"):
                a = soup.new_tag(
                    "a",
                    href=record["pmc_url"],
                    target="_blank",
                    rel="noopener",
                )
                a["data-en"] = "Full text ↗"
                a["data-it"] = "Testo completo ↗"
                a.string = "Full text ↗"
                links.append(a)

            art.append(links)
            wrap.append(art)
            cards_added += 1

        existing_titles.add(title_key)
        existing_pmids.add(pmid)
        if doi:
            existing_dois.add(doi)
        promoted += 1

    if not promoted:
        print("No new PubMed-verified records to promote.")
        return

    total = unique_publication_count(soup)
    areas_count = len(soup.select("details.library-folder"))

    for item in soup.select(".library-status-item"):
        st = item.find("strong")
        sp = item.find("span")
        if st and sp:
            label = (sp.get("data-en") or "").lower()
            if "publication" in label:
                st["data-publication-count"] = ""
                st.string = str(total)
            elif "clinical areas" in label:
                st["data-clinical-area-count"] = ""
                st.string = str(areas_count)

    LIBRARY.write_text(str(soup), encoding="utf-8")

    home = BeautifulSoup(INDEX.read_text(encoding="utf-8"), "html.parser")
    for item in home.select(".home-metric"):
        st = item.find("strong")
        sp = item.find("span")
        if st and sp:
            label = (sp.get("data-en") or "").lower()
            if "publication" in label:
                st["data-publication-count"] = ""
                st.string = str(total)
            elif "clinical areas" in label:
                st["data-clinical-area-count"] = ""
                st.string = str(areas_count)

    for card in home.select(".update-card"):
        span = card.find("span")
        strong = card.find("strong")
        if span and strong and (span.get("data-en") or "") == "Curated publications":
            strong["data-en"] = str(total)
            strong["data-it"] = str(total)
            strong.string = str(total)

    INDEX.write_text(str(home), encoding="utf-8")

    js = SCRIPT.read_text(encoding="utf-8")
    js = re.sub(
        r"(const KR_LIBRARY_STATS = \{\s*publications:\s*)\d+",
        rf"\g<1>{total}",
        js,
    )
    js = re.sub(r"(clinicalAreas:\s*)\d+", rf"\g<1>{areas_count}", js)
    SCRIPT.write_text(js, encoding="utf-8")

    print(
        f"PubMed-verified promotions: {promoted}; "
        f"cards added: {cards_added}; curated total: {total}"
    )


if __name__ == "__main__":
    main()
