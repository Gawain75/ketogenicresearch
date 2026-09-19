#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "review-queue.json"
LIBRARY = ROOT / "library.html"
INDEX = ROOT / "index.html"
SCRIPT = ROOT / "script.js"
REPORT = ROOT / "library-v5-report.json"

MAX_PROMOTIONS = max(1, int(os.getenv("PROMOTION_BATCH_MAX", "400")))


def norm(value: str) -> str:
    value = re.sub(r"^\s*\d+\.\s*", "", value or "")
    value = re.sub(r"\s+", " ", value).strip().lower()
    return re.sub(r"[^a-z0-9β]+", " ", value)


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data):
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main():
    queue = load_json(QUEUE, {"records": []})
    soup = BeautifulSoup(LIBRARY.read_text(encoding="utf-8"), "html.parser")

    sections = {}
    for details in soup.select("details.library-folder"):
        strong = details.select_one("summary strong")
        if strong:
            title = strong.get("data-en") or strong.get_text(" ", strip=True)
            sections[title] = details

    existing_titles = {
        norm(h.get("data-en") or h.get_text(" ", strip=True))
        for h in soup.select("article.folder-paper h4")
    }
    existing_pmids = {
        str(a.get("data-pmid") or "").strip()
        for a in soup.select("article.folder-paper")
        if a.get("data-pmid")
    }
    existing_dois = {
        str(a.get("data-doi") or "").strip().lower()
        for a in soup.select("article.folder-paper")
        if a.get("data-doi")
    }

    candidates = []
    for rec in queue.get("records", []):
        if not rec.get("auto_eligible"):
            continue
        if not rec.get("backfill_window"):
            continue
        if rec.get("promotion_status") == "promoted":
            continue
        candidates.append(rec)

    # Prefer older pending records first; queue order is stable.
    candidates = candidates[:MAX_PROMOTIONS]

    promoted_records = 0
    cards_added = 0

    for record in candidates:
        pmid = str(record.get("pmid") or "").strip()
        doi = str(record.get("doi") or "").strip().lower()
        title = record.get("title") or ""
        title_key = norm(title)

        if (
            not title
            or title_key in existing_titles
            or (pmid and pmid in existing_pmids)
            or (doi and doi in existing_dois)
        ):
            record["promotion_status"] = "promoted"
            record["promotion_note"] = "Already represented in library"
            continue

        valid_areas = [a for a in (record.get("areas") or []) if a in sections]
        if not valid_areas:
            record["promotion_status"] = "blocked-no-valid-area"
            continue

        for area in valid_areas:
            details = sections[area]
            wrap = details.select_one(".folder-curated")
            if not wrap:
                continue

            current = len(details.select("article.folder-paper"))
            art = soup.new_tag("article", attrs={"class": "folder-paper"})
            if pmid:
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
            if record.get("pubmed_url"):
                a = soup.new_tag(
                    "a",
                    href=record["pubmed_url"],
                    target="_blank",
                    rel="noopener",
                )
                a["data-en"] = "PubMed ↗"
                a["data-it"] = "PubMed ↗"
                a.string = "PubMed ↗"
                links.append(a)

            if record.get("doi_url"):
                a = soup.new_tag(
                    "a",
                    href=record["doi_url"],
                    target="_blank",
                    rel="noopener",
                )
                a["data-en"] = "DOI ↗"
                a["data-it"] = "DOI ↗"
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

        record["promotion_status"] = "promoted"
        record["promotion_note"] = "Published by controlled V5.1 batch"
        promoted_records += 1
        existing_titles.add(title_key)
        if pmid:
            existing_pmids.add(pmid)
        if doi:
            existing_dois.add(doi)

    total = len(soup.select("article.folder-paper"))
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

    queue["records"] = queue.get("records", [])
    save_json(QUEUE, queue)

    remaining = sum(
        1
        for r in queue["records"]
        if r.get("auto_eligible")
        and r.get("backfill_window")
        and r.get("promotion_status") != "promoted"
    )

    report = load_json(REPORT, {})
    report["controlled_promotions_this_run"] = promoted_records
    report["library_cards_added_this_run"] = cards_added
    report["promotion_backlog_after"] = remaining
    report["curated_total_after_promotion"] = total
    save_json(REPORT, report)

    print(f"Controlled V5.1 promotions: {promoted_records}")
    print(f"Library cards added: {cards_added}")
    print(f"Historical promotion backlog remaining: {remaining}")
    print(f"Curated total: {total}")


if __name__ == "__main__":
    main()
