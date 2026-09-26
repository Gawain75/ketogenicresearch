#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "library.html"
QUEUE = ROOT / "review-queue.json"
STATE = ROOT / "library-backfill-state.json"
REPORT = ROOT / "library-v5-report.json"
UPDATE_LATEST = ROOT / "scripts" / "update_latest.py"

BACKFILL_YEARS_PER_RUN = max(1, int(os.getenv("BACKFILL_YEARS_PER_RUN", "3")))
BACKFILL_START_YEAR = int(os.getenv("BACKFILL_START_YEAR", "2024"))
BACKFILL_MIN_YEAR = int(os.getenv("BACKFILL_MIN_YEAR", "1970"))
BACKFILL_MAX_RECORDS = max(100, int(os.getenv("BACKFILL_MAX_RECORDS", "3000")))
RECONCILE_MAX = max(0, int(os.getenv("RECONCILE_MAX", "50")))
PROMOTION_BATCH_MAX = max(1, int(os.getenv("PROMOTION_BATCH_MAX", "400")))
FETCH_BATCH = 200


def load_update():
    spec = importlib.util.spec_from_file_location("kr_update_latest", UPDATE_LATEST)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load scripts/update_latest.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


U = load_update()


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


def article_title(card) -> str:
    h4 = card.find("h4")
    if not h4:
        return ""
    value = h4.get("data-en") or h4.get_text(" ", strip=True)
    return re.sub(r"^\s*\d+\.\s*", "", value).strip()


def fetch_pubmed_records(ids: list[str]) -> list[ET.Element]:
    result = []
    for i in range(0, len(ids), FETCH_BATCH):
        batch = ids[i:i + FETCH_BATCH]
        root = ET.fromstring(
            U.api(
                "efetch.fcgi",
                {
                    "db": "pubmed",
                    "id": ",".join(batch),
                    "retmode": "xml",
                },
            )
        )
        result.extend(root.findall(".//PubmedArticle"))
    return result


def record_from_item(item: ET.Element) -> dict | None:
    citation = item.find("MedlineCitation")
    article = citation.find("Article") if citation is not None else None
    if citation is None or article is None:
        return None

    pmid = U.text(citation.find("PMID"))
    title = U.text(article.find("ArticleTitle"))
    abstract = " ".join(U.text(n) for n in article.findall("Abstract/AbstractText"))
    journal = U.text(article.find("Journal/Title"))

    authors = []
    for author in article.findall("AuthorList/Author"):
        collective = U.text(author.find("CollectiveName"))
        if collective:
            authors.append(collective)
            continue
        name = " ".join(
            x for x in [
                U.text(author.find("LastName")),
                U.text(author.find("Initials")),
            ] if x
        )
        if name:
            authors.append(name)

    doi = ""
    pmc = ""
    for article_id in item.findall("./PubmedData/ArticleIdList/ArticleId"):
        kind = (article_id.attrib.get("IdType") or "").lower()
        if kind == "doi":
            doi = U.text(article_id)
        elif kind == "pmc":
            pmc = U.text(article_id)

    mesh = [
        U.text(n)
        for n in citation.findall(".//MeshHeading/DescriptorName")
        if U.text(n)
    ]

    date_value, precision = U.pubdate(item)
    if not date_value:
        # Some older PubMed records only expose a MedlineDate.
        medline = U.text(article.find("Journal/JournalIssue/PubDate/MedlineDate"))
        m = re.search(r"\b(19|20)\d{2}\b", medline)
        if m:
            date_value = dt.date(int(m.group(0)), 1, 1)
            precision = "year"

    if not date_value:
        return None

    areas, confidence = U.classify(title, abstract, mesh)
    evidence_type = U.evidence(item, title, abstract, mesh)

    if precision == "day":
        date_string = date_value.isoformat()
    elif precision == "month":
        date_string = date_value.strftime("%Y-%m")
    else:
        date_string = str(date_value.year)

    return {
        "pmid": pmid,
        "title": title,
        "authors": authors,
        "journal": journal,
        "date": date_string,
        "date_precision": precision,
        "year": date_value.year,
        "doi": doi,
        "pmc": pmc,
        "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
        "doi_url": f"https://doi.org/{doi}" if doi else "",
        "pmc_url": f"https://pmc.ncbi.nlm.nih.gov/articles/{pmc}/" if pmc else "",
        "areas": areas,
        "category_confidence": confidence,
        "evidence_type": evidence_type,
        "evidence_type_it": U.IT.get(evidence_type, evidence_type),
        "source": "PubMed",
        "first_seen": dt.date.today().isoformat(),
        "status": "historical-index",
    }


def exact_title_lookup(title: str) -> dict | None:
    # Use a title-field search, then accept ONLY an exact normalized title match.
    term = f'"{title}"[Title]'
    data = json.loads(
        U.api(
            "esearch.fcgi",
            {
                "db": "pubmed",
                "term": term,
                "retmode": "json",
                "retmax": "8",
            },
        ).decode("utf-8")
    )
    ids = data.get("esearchresult", {}).get("idlist", [])
    if not ids:
        return None

    target = U.norm_title(title)
    for item in fetch_pubmed_records(ids):
        rec = record_from_item(item)
        if rec and U.norm_title(rec["title"]) == target:
            return rec
    return None


def reconcile_existing_cards(soup: BeautifulSoup) -> int:
    changed = 0
    candidates = []

    for card in soup.select("article.folder-paper"):
        if card.get("data-pmid"):
            continue
        title = article_title(card)
        if not title:
            continue
        candidates.append((card, title))

    for card, title in candidates[:RECONCILE_MAX]:
        rec = exact_title_lookup(title)
        if not rec:
            print(f"Legacy reconcile: no exact PubMed match: {title[:90]}")
            continue

        pmid = str(rec.get("pmid") or "")
        doi = U.norm_doi(rec.get("doi") or "")
        card["data-pmid"] = pmid
        if doi:
            card["data-doi"] = doi
        card["data-year"] = str(rec.get("year") or "unknown")

        # Replace title-search links with direct bibliographic links.
        links = card.select_one(".paper-links")
        if links:
            links.clear()

            a = soup.new_tag(
                "a",
                href=rec["pubmed_url"],
                target="_blank",
                rel="noopener",
            )
            a["data-en"] = "PubMed ↗"
            a["data-it"] = "PubMed ↗"
            a.string = "PubMed ↗"
            links.append(a)

            if rec.get("doi_url"):
                a = soup.new_tag(
                    "a",
                    href=rec["doi_url"],
                    target="_blank",
                    rel="noopener",
                )
                a["data-en"] = "DOI ↗"
                a["data-it"] = "DOI ↗"
                a.string = "DOI ↗"
                links.append(a)

            if rec.get("pmc_url"):
                a = soup.new_tag(
                    "a",
                    href=rec["pmc_url"],
                    target="_blank",
                    rel="noopener",
                )
                a["data-en"] = "Full text ↗"
                a["data-it"] = "Testo completo ↗"
                a.string = "Full text ↗"
                links.append(a)

        changed += 1
        print(f"Legacy reconcile: matched PMID {pmid}: {title[:90]}")

    return changed


def existing_keys(soup: BeautifulSoup):
    titles, pmids, dois = set(), set(), set()

    for card in soup.select("article.folder-paper"):
        title = article_title(card)
        if title:
            titles.add(U.norm_title(title))

        pmid = str(card.get("data-pmid") or "").strip()
        doi = U.norm_doi(card.get("data-doi") or "")
        if pmid:
            pmids.add(pmid)
        if doi:
            dois.add(doi)

        for link in card.find_all("a", href=True):
            href = link["href"]
            m = re.search(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)/", href, re.I)
            if m:
                pmids.add(m.group(1))
            m = re.search(r"https?://(?:dx\.)?doi\.org/(.+)$", href, re.I)
            if m:
                dois.add(U.norm_doi(m.group(1)))

    return titles, pmids, dois


def search_backfill_ids(start_year: int, end_year: int) -> tuple[list[str], int]:
    common = {
        "db": "pubmed",
        "term": U.QUERY,
        "retmode": "json",
        "sort": "pub date",
        "datetype": "pdat",
        "mindate": f"{start_year}/01/01",
        "maxdate": f"{end_year}/12/31",
    }

    first = json.loads(
        U.api(
            "esearch.fcgi",
            {**common, "retmax": "0"},
        ).decode("utf-8")
    )
    count = int(first.get("esearchresult", {}).get("count", "0") or 0)

    ids = []
    page = 500
    for retstart in range(0, min(count, BACKFILL_MAX_RECORDS), page):
        data = json.loads(
            U.api(
                "esearch.fcgi",
                {
                    **common,
                    "retstart": str(retstart),
                    "retmax": str(min(page, BACKFILL_MAX_RECORDS - retstart)),
                },
            ).decode("utf-8")
        )
        ids.extend(data.get("esearchresult", {}).get("idlist", []))

    return list(dict.fromkeys(ids)), count


def merge_queue(new_records: list[dict]) -> int:
    data = load_json(QUEUE, {"records": []})
    records = data.get("records", [])

    by_pmid = {
        str(r.get("pmid")): r
        for r in records
        if r.get("pmid")
    }

    added = 0
    for rec in new_records:
        pmid = str(rec.get("pmid") or "")
        if not pmid or pmid in by_pmid:
            continue
        by_pmid[pmid] = rec
        records.append(rec)
        added += 1

    data["records"] = records
    data["updated"] = dt.datetime.now(dt.timezone.utc).isoformat()
    data["source"] = "PubMed + Library V5"
    save_json(QUEUE, data)
    return added



def historical_promotion_backlog() -> int:
    data = load_json(QUEUE, {"records": []})
    count = 0
    for rec in data.get("records", []):
        if not rec.get("auto_eligible"):
            continue
        if not rec.get("backfill_window"):
            continue
        if rec.get("promotion_status") == "promoted":
            continue
        count += 1
    return count

def main():
    if not LIBRARY.exists():
        raise SystemExit("library.html not found.")

    soup = BeautifulSoup(LIBRARY.read_text(encoding="utf-8"), "html.parser")

    before_cards = len(soup.select("article.folder-paper"))
    reconciled = reconcile_existing_cards(soup)

    # Persist reconciliations before determining duplicate keys.
    if reconciled:
        LIBRARY.write_text(str(soup), encoding="utf-8")

    titles, pmids, dois = existing_keys(soup)

    state = load_json(
        STATE,
        {
            "version": 5.1,
            "next_end_year": BACKFILL_START_YEAR,
            "min_year": BACKFILL_MIN_YEAR,
            "years_per_run": BACKFILL_YEARS_PER_RUN,
            "completed": False,
        },
    )

    end_year = int(state.get("next_end_year", BACKFILL_START_YEAR))
    min_year = int(state.get("min_year", BACKFILL_MIN_YEAR))
    backlog_before = historical_promotion_backlog()

    # V5.1: do not discover another historical window while a large backlog
    # from earlier V5 discovery still awaits controlled promotion.
    if backlog_before >= PROMOTION_BATCH_MAX:
        print(
            f"Historical discovery paused: {backlog_before} eligible V5 records "
            f"are still awaiting promotion."
        )
        start_year = None
        ids = []
        pubmed_count = 0
    elif state.get("completed") or end_year < min_year:
        print("Historical backfill already complete.")
        start_year = None
        ids = []
        pubmed_count = 0
    else:
        start_year = max(min_year, end_year - BACKFILL_YEARS_PER_RUN + 1)
        print(f"Historical backfill window: {start_year}-{end_year}")
        ids, pubmed_count = search_backfill_ids(start_year, end_year)
        print(f"PubMed query count: {pubmed_count}; fetched IDs: {len(ids)}")

    new_records = []
    rejected_irrelevant = 0
    rejected_duplicate = 0
    rejected_low_confidence = 0

    for item in fetch_pubmed_records(ids) if ids else []:
        citation = item.find("MedlineCitation")
        article = citation.find("Article") if citation is not None else None
        if citation is None or article is None or not U.relevant(article):
            rejected_irrelevant += 1
            continue

        rec = record_from_item(item)
        if not rec:
            rejected_irrelevant += 1
            continue

        title_key = U.norm_title(rec["title"])
        doi = U.norm_doi(rec.get("doi") or "")
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

        auto_eligible = bool(valid_areas and rec.get("category_confidence", 0) >= 2)

        if not auto_eligible:
            rejected_low_confidence += 1

        rec["auto_eligible"] = auto_eligible
        rec["curation_status"] = (
            "auto-approved-historical"
            if auto_eligible
            else "excluded-low-confidence"
        )
        rec["promotion_status"] = (
            "pending"
            if auto_eligible
            else "not-eligible"
        )
        rec["backfill_window"] = (
            f"{start_year}-{end_year}"
            if start_year is not None
            else ""
        )
        new_records.append(rec)

        # Prevent duplicates within this same V5 run.
        titles.add(title_key)
        if pmid:
            pmids.add(pmid)
        if doi:
            dois.add(doi)

    queued = merge_queue(new_records)

    if start_year is not None:
        next_end = start_year - 1
        state.update(
            {
                "version": 5.1,
                "last_completed_window": f"{start_year}-{end_year}",
                "last_run": dt.datetime.now(dt.timezone.utc).isoformat(),
                "next_end_year": next_end,
                "completed": next_end < min_year,
                "min_year": min_year,
                "years_per_run": BACKFILL_YEARS_PER_RUN,
            }
        )
        save_json(STATE, state)

    report = {
        "version": 5.1,
        "run_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "library_cards_before_promotion": before_cards,
        "legacy_cards_reconciled": reconciled,
        "backfill_window": (
            f"{start_year}-{end_year}"
            if start_year is not None
            else None
        ),
        "pubmed_query_count": pubmed_count,
        "pubmed_ids_fetched": len(ids),
        "new_queue_records": queued,
        "auto_eligible_records": sum(1 for x in new_records if x.get("auto_eligible")),
        "low_confidence_records": rejected_low_confidence,
        "duplicates_skipped": rejected_duplicate,
        "irrelevant_or_unusable_skipped": rejected_irrelevant,
        "next_end_year": state.get("next_end_year"),
        "backfill_completed": state.get("completed", False),
        "promotion_backlog_before": backlog_before,
        "promotion_batch_max": PROMOTION_BATCH_MAX,
    }
    save_json(REPORT, report)

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
