#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from bs4 import BeautifulSoup
from pubmed_record_guard import norm_doi, norm_title

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = ROOT / "historical-gap-candidates.json"
QUEUE = ROOT / "review-queue.json"
LIBRARY = ROOT / "library.html"
REPORT = ROOT / "historical-gap-queue-report.json"


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    candidates_doc = load_json(CANDIDATES, {"records": []})
    queue = load_json(QUEUE, {"records": []})
    soup = BeautifulSoup(LIBRARY.read_text(encoding="utf-8"), "html.parser")

    existing_pmids = {
        str(a.get("data-pmid") or "").strip()
        for a in soup.select("article.folder-paper")
        if str(a.get("data-pmid") or "").strip()
    }
    existing_dois = {
        norm_doi(str(a.get("data-doi") or ""))
        for a in soup.select("article.folder-paper")
        if norm_doi(str(a.get("data-doi") or ""))
    }
    existing_titles = {
        norm_title((h.get("data-en") or h.get_text(" ", strip=True) or ""))
        for h in soup.select("article.folder-paper h4")
    }

    queue_by_pmid = {
        str(r.get("pmid") or "").strip(): r
        for r in queue.get("records", [])
        if str(r.get("pmid") or "").strip()
    }

    considered = 0
    added = 0
    already_present = 0
    already_queued = 0
    existing_queue_activated = 0
    skipped_low_confidence = 0

    for rec in candidates_doc.get("records", []) or []:
        if not rec.get("auto_eligible"):
            skipped_low_confidence += 1
            continue
        considered += 1

        pmid = str(rec.get("pmid") or "").strip()
        doi = norm_doi(str(rec.get("doi") or ""))
        title_key = norm_title(str(rec.get("title") or ""))

        if (
            (pmid and pmid in existing_pmids)
            or (doi and doi in existing_dois)
            or (title_key and title_key in existing_titles)
        ):
            already_present += 1
            continue
        if not pmid:
            continue

        if pmid in queue_by_pmid:
            item = queue_by_pmid[pmid]
            already_queued += 1
            if item.get("promotion_status") != "promoted":
                # Promote the freshly audited PubMed metadata to the queue record.
                for key in (
                    "title", "authors", "journal", "date", "date_precision",
                    "year", "doi", "pmc", "pubmed_url", "doi_url", "pmc_url",
                    "areas", "category_confidence", "evidence_type",
                    "evidence_type_it", "source", "auto_eligible"
                ):
                    if key in rec:
                        item[key] = rec[key]
                item["backfill_window"] = "completeness-audit"
                item["status"] = "historical-completeness-audit"
                item["promotion_status"] = item.get("promotion_status") or "pending"
                item["queued_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
                existing_queue_activated += 1
            continue

        item = dict(rec)
        item["backfill_window"] = "completeness-audit"
        item["status"] = "historical-completeness-audit"
        item["promotion_status"] = item.get("promotion_status") or "pending"
        item["queued_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        queue.setdefault("records", []).append(item)
        queue_by_pmid[pmid] = item
        added += 1

    queue["updated"] = dt.datetime.now(dt.timezone.utc).isoformat()
    queue["source"] = "PubMed + Library V5 + completeness audit"
    save_json(QUEUE, queue)

    report = {
        "run_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "auto_eligible_considered": considered,
        "added_to_review_queue": added,
        "already_present": already_present,
        "already_queued": already_queued,
        "existing_queue_activated": existing_queue_activated,
        "low_confidence_left_for_review": skipped_low_confidence,
    }
    save_json(REPORT, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
