#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import library_v5 as V

ROOT = Path(__file__).resolve().parents[1]

STATE = ROOT / "historical-gap-audit-state.json"
REPORT = ROOT / "historical-gap-audit.json"
CANDIDATES = ROOT / "historical-gap-candidates.json"

START_YEAR = int(os.getenv("HISTORICAL_AUDIT_START_YEAR", "2025"))
END_YEAR = int(os.getenv("HISTORICAL_AUDIT_END_YEAR", "1921"))
YEARS_PER_RUN = max(1, int(os.getenv("HISTORICAL_AUDIT_YEARS_PER_RUN", "10")))


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


def record_key(rec: dict) -> str:
    pmid = str(rec.get("pmid") or "").strip()
    if pmid:
        return "pmid:" + pmid
    doi = V.U.norm_doi(rec.get("doi") or "")
    if doi:
        return "doi:" + doi
    return "title:" + V.U.norm_title(rec.get("title") or "")


def main():
    if not V.LIBRARY.exists():
        raise SystemExit("library.html not found.")

    soup = V.BeautifulSoup(
        V.LIBRARY.read_text(encoding="utf-8"),
        "html.parser",
    )

    library_titles, library_pmids, library_dois = V.existing_keys(soup)

    state = load_json(
        STATE,
        {
            "next_year": START_YEAR,
            "start_year": START_YEAR,
            "end_year": END_YEAR,
            "completed": False,
        },
    )

    if (
        int(state.get("start_year", START_YEAR)) != START_YEAR
        or int(state.get("end_year", END_YEAR)) != END_YEAR
    ):
        state = {
            "next_year": START_YEAR,
            "start_year": START_YEAR,
            "end_year": END_YEAR,
            "completed": False,
        }

    next_year = int(state.get("next_year", START_YEAR))
    if state.get("completed"):
        print("Historical gap audit already completed.")
        print(json.dumps(state, indent=2))
        return

    report = load_json(
        REPORT,
        {
            "version": "historical-gap-audit-v1",
            "range": [END_YEAR, START_YEAR],
            "years": [],
        },
    )

    candidates_doc = load_json(
        CANDIDATES,
        {
            "version": "historical-gap-candidates-v1",
            "records": [],
        },
    )

    existing_rows = {
        int(row["year"]): row
        for row in report.get("years", [])
        if "year" in row
    }

    candidate_map = {
        record_key(rec): rec
        for rec in candidates_doc.get("records", [])
        if record_key(rec) != "title:"
    }

    years_done = 0
    year = next_year

    while year >= END_YEAR and years_done < YEARS_PER_RUN:
        print(f"\n=== Auditing {year} ===")

        ids, pubmed_query_count = V.search_backfill_ids(year, year)

        pertinent = 0
        already_present = 0
        missing = 0
        auto_eligible_missing = 0
        low_confidence_missing = 0
        unusable = 0
        seen_this_year = set()

        for item in V.fetch_pubmed_records(ids):
            citation = item.find("MedlineCitation")
            article = citation.find("Article") if citation is not None else None

            if citation is None or article is None:
                unusable += 1
                continue

            if not V.U.relevant(article):
                continue

            rec = V.record_from_item(item)
            if not rec:
                unusable += 1
                continue

            rec_year = int(rec.get("year") or 0)
            if rec_year != year:
                continue

            key = record_key(rec)
            if not key or key == "title:" or key in seen_this_year:
                continue
            seen_this_year.add(key)

            pertinent += 1

            pmid = str(rec.get("pmid") or "").strip()
            doi = V.U.norm_doi(rec.get("doi") or "")
            title_key = V.U.norm_title(rec.get("title") or "")

            is_present = (
                (pmid and pmid in library_pmids)
                or (doi and doi in library_dois)
                or (title_key and title_key in library_titles)
            )

            if is_present:
                already_present += 1
                continue

            missing += 1

            valid_areas = [
                area for area in rec.get("areas", [])
                if area != "Other / General"
            ]
            auto_eligible = bool(
                valid_areas and rec.get("category_confidence", 0) >= 2
            )

            if auto_eligible:
                auto_eligible_missing += 1
            else:
                low_confidence_missing += 1

            rec["audit_year"] = year
            rec["audit_status"] = "missing-from-library"
            rec["auto_eligible"] = auto_eligible
            rec["curation_status"] = (
                "audit-auto-eligible"
                if auto_eligible
                else "audit-review-needed"
            )

            candidate_map[key] = rec

        row = {
            "year": year,
            "pubmed_query_count": pubmed_query_count,
            "pubmed_ids_fetched": len(ids),
            "pertinent_records": pertinent,
            "already_present": already_present,
            "missing_from_library": missing,
            "auto_eligible_missing": auto_eligible_missing,
            "review_needed_missing": low_confidence_missing,
            "unusable_records": unusable,
            "coverage_percent": (
                round((already_present / pertinent) * 100, 1)
                if pertinent else 100.0
            ),
        }

        existing_rows[year] = row
        print(json.dumps(row, ensure_ascii=False, indent=2))

        year -= 1
        years_done += 1

    completed = year < END_YEAR

    rows = sorted(existing_rows.values(), key=lambda x: int(x["year"]), reverse=True)

    report = {
        "version": "historical-gap-audit-v1",
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "range": [END_YEAR, START_YEAR],
        "completed": completed,
        "years_audited": len(rows),
        "totals": {
            "pertinent_records": sum(r["pertinent_records"] for r in rows),
            "already_present": sum(r["already_present"] for r in rows),
            "missing_from_library": sum(r["missing_from_library"] for r in rows),
            "auto_eligible_missing": sum(r["auto_eligible_missing"] for r in rows),
            "review_needed_missing": sum(r["review_needed_missing"] for r in rows),
        },
        "years": rows,
    }

    candidates = sorted(
        candidate_map.values(),
        key=lambda r: (
            -int(r.get("audit_year") or 0),
            (r.get("title") or "").casefold(),
        ),
    )

    candidates_doc = {
        "version": "historical-gap-candidates-v1",
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "count": len(candidates),
        "records": candidates,
    }

    state = {
        "start_year": START_YEAR,
        "end_year": END_YEAR,
        "next_year": END_YEAR if completed else year,
        "completed": completed,
        "years_per_run": YEARS_PER_RUN,
        "last_run_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }

    save_json(REPORT, report)
    save_json(CANDIDATES, candidates_doc)
    save_json(STATE, state)

    print("\n=== AUDIT PROGRESS ===")
    print(json.dumps({
        "years_audited": report["years_audited"],
        "missing_found_so_far": report["totals"]["missing_from_library"],
        "auto_eligible_missing_so_far": report["totals"]["auto_eligible_missing"],
        "next_year": state["next_year"],
        "completed": completed,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
