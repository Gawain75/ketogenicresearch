#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import library_v5 as V

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "review-queue.json"
REPORT = ROOT / "library-2025-backfill-report.json"

TARGET_YEAR = 2025


def save_json(path: Path, data):
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main():
    if not V.LIBRARY.exists():
        raise SystemExit("library.html not found.")

    soup = V.BeautifulSoup(
        V.LIBRARY.read_text(encoding="utf-8"),
        "html.parser",
    )

    titles, pmids, dois = V.existing_keys(soup)

    print(f"Dedicated PubMed backfill: {TARGET_YEAR}")
    ids, pubmed_count = V.search_backfill_ids(TARGET_YEAR, TARGET_YEAR)

    print(f"PubMed query count: {pubmed_count}")
    print(f"PubMed IDs fetched: {len(ids)}")

    new_records = []
    rejected_irrelevant = 0
    rejected_duplicate = 0
    rejected_low_confidence = 0

    for item in V.fetch_pubmed_records(ids):
        citation = item.find("MedlineCitation")
        article = citation.find("Article") if citation is not None else None

        if citation is None or article is None or not V.U.relevant(article):
            rejected_irrelevant += 1
            continue

        rec = V.record_from_item(item)
        if not rec:
            rejected_irrelevant += 1
            continue

        # This run is explicitly restricted to publication year 2025.
        if int(rec.get("year") or 0) != TARGET_YEAR:
            rejected_irrelevant += 1
            continue

        title_key = V.U.norm_title(rec["title"])
        doi = V.U.norm_doi(rec.get("doi") or "")
        pmid = str(rec.get("pmid") or "")

        if (
            (pmid and pmid in pmids)
            or (doi and doi in dois)
            or title_key in titles
        ):
            rejected_duplicate += 1
            continue

        valid_areas = [
            area for area in rec.get("areas", [])
            if area != "Other / General"
        ]

        auto_eligible = bool(
            valid_areas and rec.get("category_confidence", 0) >= 2
        )

        if not auto_eligible:
            rejected_low_confidence += 1

        rec["auto_eligible"] = auto_eligible
        rec["curation_status"] = (
            "auto-approved-2025-backfill"
            if auto_eligible
            else "excluded-low-confidence"
        )
        rec["promotion_status"] = (
            "pending" if auto_eligible else "not-eligible"
        )
        rec["backfill_window"] = "2025-2025"
        rec["status"] = "2025-targeted-backfill"

        new_records.append(rec)

        # Prevent duplicates inside this run.
        titles.add(title_key)
        if pmid:
            pmids.add(pmid)
        if doi:
            dois.add(doi)

    queued = V.merge_queue(new_records)

    report = {
        "version": "2025-targeted-backfill-v1",
        "run_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "target_year": TARGET_YEAR,
        "pubmed_query_count": pubmed_count,
        "pubmed_ids_fetched": len(ids),
        "new_queue_records": queued,
        "auto_eligible_records": sum(
            1 for x in new_records if x.get("auto_eligible")
        ),
        "low_confidence_records": rejected_low_confidence,
        "duplicates_skipped": rejected_duplicate,
        "irrelevant_or_unusable_skipped": rejected_irrelevant,
    }
    save_json(REPORT, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
