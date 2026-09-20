#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import library_v5 as V

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "library-1921-1970-backfill-report.json"

START_YEAR = 1921
END_YEAR = 1970
WINDOW_YEARS = 5


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

    totals = {
        "pubmed_query_count": 0,
        "pubmed_ids_fetched": 0,
        "new_records_found": 0,
        "auto_eligible_records": 0,
        "low_confidence_records": 0,
        "duplicates_skipped": 0,
        "irrelevant_or_unusable_skipped": 0,
    }
    windows = []
    all_new_records = []

    year = START_YEAR
    while year <= END_YEAR:
        window_start = year
        window_end = min(year + WINDOW_YEARS - 1, END_YEAR)

        print(f"\n=== Backfill {window_start}-{window_end} ===")
        ids, pubmed_count = V.search_backfill_ids(window_start, window_end)

        window_stats = {
            "window": f"{window_start}-{window_end}",
            "pubmed_query_count": pubmed_count,
            "pubmed_ids_fetched": len(ids),
            "new_records": 0,
            "auto_eligible": 0,
            "low_confidence": 0,
            "duplicates_skipped": 0,
            "irrelevant_or_unusable_skipped": 0,
        }

        totals["pubmed_query_count"] += pubmed_count
        totals["pubmed_ids_fetched"] += len(ids)

        for item in V.fetch_pubmed_records(ids):
            citation = item.find("MedlineCitation")
            article = citation.find("Article") if citation is not None else None

            if citation is None or article is None or not V.U.relevant(article):
                window_stats["irrelevant_or_unusable_skipped"] += 1
                totals["irrelevant_or_unusable_skipped"] += 1
                continue

            rec = V.record_from_item(item)
            if not rec:
                window_stats["irrelevant_or_unusable_skipped"] += 1
                totals["irrelevant_or_unusable_skipped"] += 1
                continue

            rec_year = int(rec.get("year") or 0)
            if rec_year < window_start or rec_year > window_end:
                window_stats["irrelevant_or_unusable_skipped"] += 1
                totals["irrelevant_or_unusable_skipped"] += 1
                continue

            title_key = V.U.norm_title(rec["title"])
            doi = V.U.norm_doi(rec.get("doi") or "")
            pmid = str(rec.get("pmid") or "")

            if (
                (pmid and pmid in pmids)
                or (doi and doi in dois)
                or title_key in titles
            ):
                window_stats["duplicates_skipped"] += 1
                totals["duplicates_skipped"] += 1
                continue

            valid_areas = [
                area for area in rec.get("areas", [])
                if area != "Other / General"
            ]
            auto_eligible = bool(
                valid_areas and rec.get("category_confidence", 0) >= 2
            )

            rec["auto_eligible"] = auto_eligible
            rec["curation_status"] = (
                "auto-approved-1921-1970-backfill"
                if auto_eligible
                else "excluded-low-confidence"
            )
            rec["promotion_status"] = (
                "pending" if auto_eligible else "not-eligible"
            )
            rec["backfill_window"] = f"{window_start}-{window_end}"
            rec["status"] = "1921-1970-targeted-backfill"

            all_new_records.append(rec)
            window_stats["new_records"] += 1
            totals["new_records_found"] += 1

            if auto_eligible:
                window_stats["auto_eligible"] += 1
                totals["auto_eligible_records"] += 1
            else:
                window_stats["low_confidence"] += 1
                totals["low_confidence_records"] += 1

            # Avoid duplicates across the historical windows in this same run.
            titles.add(title_key)
            if pmid:
                pmids.add(pmid)
            if doi:
                dois.add(doi)

        windows.append(window_stats)
        print(json.dumps(window_stats, ensure_ascii=False, indent=2))
        year = window_end + 1

    queued = V.merge_queue(all_new_records)

    report = {
        "version": "1921-1970-targeted-backfill-v1",
        "run_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "target_range": [START_YEAR, END_YEAR],
        "window_years": WINDOW_YEARS,
        "new_queue_records": queued,
        **totals,
        "windows": windows,
    }
    save_json(REPORT, report)

    print("\n=== FINAL REPORT ===")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
