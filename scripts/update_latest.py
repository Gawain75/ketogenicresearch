#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import os
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "latest-publications.json"

EMAIL = os.getenv("NCBI_EMAIL", "info@ketogenicresearch.org")
API_KEY = os.getenv("NCBI_API_KEY", "")
WINDOW_DAYS = int(os.getenv("WINDOW_DAYS", "90"))
MAX_RECORDS = int(os.getenv("MAX_RECORDS", "100"))

BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

QUERY = """
(
"ketogenic diet"[Title/Abstract]
OR "ketogenic diets"[Title/Abstract]
OR "ketogenic therapy"[Title/Abstract]
OR "ketogenic metabolic therapy"[Title/Abstract]
OR "nutritional ketosis"[Title/Abstract]
OR "very low calorie ketogenic diet"[Title/Abstract]
OR "very-low-calorie ketogenic diet"[Title/Abstract]
OR "very low energy ketogenic therapy"[Title/Abstract]
OR "modified Atkins diet"[Title/Abstract]
OR VLCKD[Title/Abstract]
OR VLEKT[Title/Abstract]
OR "exogenous ketone"[Title/Abstract]
OR "exogenous ketones"[Title/Abstract]
OR "ketone ester"[Title/Abstract]
OR "ketone esters"[Title/Abstract]
OR "ketone salt"[Title/Abstract]
OR "ketone salts"[Title/Abstract]
OR (
    (
        "beta-hydroxybutyrate"[Title/Abstract]
        OR "β-hydroxybutyrate"[Title/Abstract]
        OR "ketone bodies"[Title/Abstract]
    )
    AND
    (
        ketogenic[Title/Abstract]
        OR "nutritional ketosis"[Title/Abstract]
        OR "ketogenic therapy"[Title/Abstract]
    )
)
)
"""

MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


def api(name: str, params: dict[str, str]) -> bytes:
    params = {**params, "tool": "ketogenicresearch-literature-monitor", "email": EMAIL}
    if API_KEY:
        params["api_key"] = API_KEY
    url = f"{BASE}/{name}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": f"ketogenicresearch-literature-monitor/1.1 ({EMAIL})"},
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        data = response.read()
    time.sleep(0.12 if API_KEY else 0.36)
    return data


def clean_text(node) -> str:
    if node is None:
        return ""
    return "".join(node.itertext()).strip()


CORE_RELEVANCE_TERMS = (
    "ketogenic diet",
    "ketogenic diets",
    "ketogenic therapy",
    "ketogenic metabolic therapy",
    "nutritional ketosis",
    "very low calorie ketogenic diet",
    "very-low-calorie ketogenic diet",
    "very low energy ketogenic therapy",
    "modified atkins diet",
    "vlckd",
    "vlekt",
    "exogenous ketone",
    "exogenous ketones",
    "ketone ester",
    "ketone esters",
    "ketone salt",
    "ketone salts",
)

SECONDARY_KETONE_TERMS = (
    "beta-hydroxybutyrate",
    "β-hydroxybutyrate",
    "ketone bodies",
)

SECONDARY_CONTEXT_TERMS = (
    "ketogenic",
    "nutritional ketosis",
    "ketogenic therapy",
)


def is_relevant_record(article: ET.Element) -> bool:
    title = clean_text(article.find("ArticleTitle"))
    abstract = " ".join(
        clean_text(node)
        for node in article.findall("Abstract/AbstractText")
    )
    text = f"{title} {abstract}".lower()

    if any(term in text for term in CORE_RELEVANCE_TERMS):
        return True

    has_secondary = any(term in text for term in SECONDARY_KETONE_TERMS)
    has_context = any(term in text for term in SECONDARY_CONTEXT_TERMS)
    return has_secondary and has_context


def parse_month(value: str) -> int | None:
    value = (value or "").strip()
    if not value:
        return None
    if value.isdigit():
        month = int(value)
        return month if 1 <= month <= 12 else None
    return MONTHS.get(value.lower())


def make_date(year: int, month: int | None = None, day: int | None = None) -> dict:
    if month is not None and day is not None:
        try:
            full = dt.date(year, month, day)
            return {
                "date": full.isoformat(),
                "date_precision": "day",
                "sort_key": (year, month, day),
            }
        except ValueError:
            pass

    if month is not None:
        return {
            "date": f"{year:04d}-{month:02d}",
            "date_precision": "month",
            "sort_key": (year, month, 0),
        }

    return {
        "date": f"{year:04d}",
        "date_precision": "year",
        "sort_key": (year, 0, 0),
    }


def date_from_node(node) -> dict | None:
    if node is None:
        return None

    year_text = clean_text(node.find("Year"))
    month_text = clean_text(node.find("Month"))
    day_text = clean_text(node.find("Day"))

    if year_text.isdigit():
        year = int(year_text)
        month = parse_month(month_text)
        day = int(day_text) if day_text.isdigit() else None
        return make_date(year, month, day)

    medline = clean_text(node.find("MedlineDate"))
    if medline:
        match = re.search(r"\b(?:19|20)\d{2}\b", medline)
        if match:
            year = int(match.group(0))
            month = None
            lower = medline.lower()
            for name, number in MONTHS.items():
                if re.search(rf"\b{re.escape(name)}\b", lower):
                    month = number
                    break
            return make_date(year, month)

    return None


def publication_date(pubmed_article: ET.Element) -> dict:
    article_dates = []
    for node in pubmed_article.findall(".//Article/ArticleDate"):
        parsed = date_from_node(node)
        if parsed:
            article_dates.append(parsed)

    if article_dates:
        article_dates.sort(key=lambda x: x["sort_key"], reverse=True)
        return article_dates[0]

    preferred_statuses = ("epublish", "ppublish", "pubmed")
    status_candidates = []

    for node in pubmed_article.findall(".//PubmedData/History/PubMedPubDate"):
        status = (node.attrib.get("PubStatus") or "").lower()
        parsed = date_from_node(node)
        if parsed:
            priority = preferred_statuses.index(status) if status in preferred_statuses else 99
            status_candidates.append((priority, parsed))

    preferred = [item for item in status_candidates if item[0] < 99]
    if preferred:
        preferred.sort(key=lambda x: (x[0], tuple(-v for v in x[1]["sort_key"])))
        return preferred[0][1]

    journal_date = date_from_node(
        pubmed_article.find(".//Article/Journal/JournalIssue/PubDate")
    )
    if journal_date:
        return journal_date

    if status_candidates:
        status_candidates.sort(key=lambda x: x[1]["sort_key"], reverse=True)
        return status_candidates[0][1]

    return {
        "date": "",
        "date_precision": "unknown",
        "sort_key": (0, 0, 0),
    }


def load_previous() -> dict[str, dict]:
    if not OUT.exists():
        return {}
    try:
        old = json.loads(OUT.read_text(encoding="utf-8"))
        return {
            p["pmid"]: p
            for p in old.get("publications", [])
            if p.get("pmid")
        }
    except Exception:
        return {}


def main() -> None:
    search = json.loads(
        api(
            "esearch.fcgi",
            {
                "db": "pubmed",
                "term": QUERY,
                "retmode": "json",
                "retmax": str(MAX_RECORDS),
                "sort": "pub date",
                "datetype": "pdat",
                "reldate": str(WINDOW_DAYS),
            },
        ).decode("utf-8")
    )

    ids = search.get("esearchresult", {}).get("idlist", [])
    if not ids:
        raise SystemExit("No PubMed records returned.")

    root = ET.fromstring(
        api(
            "efetch.fcgi",
            {
                "db": "pubmed",
                "id": ",".join(ids),
                "retmode": "xml",
            },
        )
    )

    previous = load_previous()
    today = dt.date.today()
    publications = []

    for item in root.findall(".//PubmedArticle"):
        citation = item.find("MedlineCitation")
        article = citation.find("Article") if citation is not None else None
        if citation is None or article is None:
            continue

        if not is_relevant_record(article):
            continue

        pmid = clean_text(citation.find("PMID"))
        title = clean_text(article.find("ArticleTitle"))
        journal = clean_text(article.find("Journal/Title"))

        authors = []
        for author in article.findall("AuthorList/Author"):
            collective = clean_text(author.find("CollectiveName"))
            if collective:
                authors.append(collective)
                continue

            last = clean_text(author.find("LastName"))
            initials = clean_text(author.find("Initials"))
            name = " ".join(x for x in (last, initials) if x)
            if name:
                authors.append(name)

        doi = ""
        for aid in item.findall(".//ArticleId"):
            if (aid.attrib.get("IdType") or "").lower() == "doi":
                doi = clean_text(aid)
                break

        date_info = publication_date(item)
        year = date_info["sort_key"][0] or None

        old = previous.get(pmid, {})
        first_seen = old.get("first_seen") or today.isoformat()

        try:
            seen_date = dt.date.fromisoformat(first_seen)
            status = "new" if (today - seen_date).days <= 14 else "indexed"
        except ValueError:
            first_seen = today.isoformat()
            status = "new"

        publications.append(
            {
                "pmid": pmid,
                "title": title,
                "authors": authors,
                "journal": journal,
                "date": date_info["date"],
                "date_precision": date_info["date_precision"],
                "year": year,
                "doi": doi,
                "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
                "doi_url": f"https://doi.org/{doi}" if doi else "",
                "areas": old.get("areas") or ["Other / General"],
                "source": "PubMed",
                "first_seen": first_seen,
                "status": status,
                "_sort_key": date_info["sort_key"],
            }
        )

    publications.sort(
        key=lambda p: (p["_sort_key"], p.get("pmid") or ""),
        reverse=True,
    )
    publications = publications[:MAX_RECORDS]

    for publication in publications:
        publication.pop("_sort_key", None)

    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "window_days": WINDOW_DAYS,
        "max_records": MAX_RECORDS,
        "source": "PubMed / NCBI E-utilities",
        "count": len(publications),
        "publications": publications,
    }

    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Wrote {len(publications)} records to {OUT.name}")


if __name__ == "__main__":
    main()w
