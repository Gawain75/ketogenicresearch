#!/usr/bin/env python3
from __future__ import annotations

import difflib
import json
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "library.html"
REPORT = ROOT / "publication-year-recovery.json"

NCBI_API_KEY = (os.getenv("NCBI_API_KEY") or "").strip()
NCBI_EMAIL = (os.getenv("NCBI_EMAIL") or "info@ketogenicresearch.org").strip()
BATCH_MAX = max(1, int(os.getenv("YEAR_RECOVERY_BATCH_MAX", "600")))
REQUEST_PAUSE = float(os.getenv(
    "YEAR_RECOVERY_PAUSE",
    "0.12" if NCBI_API_KEY else "0.36"
))

ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"

def norm_title(value: str) -> str:
    value = re.sub(r"^\s*\d+\.\s*", "", value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = value.replace("β", "beta").replace("α", "alpha")
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())

def title_from(article) -> str:
    h4 = article.find("h4")
    if not h4:
        return ""
    return (
        h4.get("data-en")
        or h4.get_text(" ", strip=True)
        or ""
    ).strip()

def valid_year(value) -> int | None:
    m = re.search(r"\b((?:18|19|20)\d{2})\b", str(value or ""))
    if not m:
        return None
    year = int(m.group(1))
    current = time.gmtime().tm_year
    return year if 1800 <= year <= current else None

def existing_year(article) -> int | None:
    return valid_year(article.get("data-year"))

def citation_year(article) -> int | None:
    # Only inspect bibliographic/body paragraphs, never the title,
    # to avoid treating a year appearing in a title as publication year.
    for p in article.find_all("p", recursive=False):
        text = p.get_text(" ", strip=True)
        # Common citation structures:
        # Journal · 2026-02-26 / Journal. 2026;18... / (2026)
        for pattern in (
            r"(?:^|[·.;,(]\s*)((?:18|19|20)\d{2})(?:[-/]\d{1,2}(?:[-/]\d{1,2})?)?(?=\s|[;:.,)])",
            r"\b(?:Published|Publication date|Publication year|Year)\s*:?\s*((?:18|19|20)\d{2})\b",
        ):
            m = re.search(pattern, text, re.I)
            if m:
                return valid_year(m.group(1))
    return None

def request_json(base: str, params: dict, attempts: int = 5) -> dict:
    params = dict(params)
    params.update({
        "tool": "KetogenicResearch",
        "email": NCBI_EMAIL,
    })
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY

    url = base + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "KetogenicResearch/PublicationYearRecovery/1.0"},
    )
    last = None
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            last = exc
            if attempt >= attempts:
                raise
            wait = min(30, 3 * attempt)
            print(f"NCBI request failed; retrying in {wait}s: {exc}")
            time.sleep(wait)
    raise RuntimeError(last)

def pubmed_candidates(title: str) -> list[str]:
    # Exact-title search first, then a title-field search if PubMed normalization
    # prevents the quoted form from matching.
    queries = [
        f'"{title}"[Title]',
        f'{title}[Title]',
    ]
    for query in queries:
        data = request_json(ESEARCH, {
            "db": "pubmed",
            "term": query,
            "retmode": "json",
            "retmax": "5",
            "sort": "relevance",
        })
        ids = data.get("esearchresult", {}).get("idlist", []) or []
        if ids:
            return [str(x) for x in ids]
        time.sleep(REQUEST_PAUSE)
    return []

def pubmed_summaries(pmids: list[str]) -> dict:
    if not pmids:
        return {}
    data = request_json(ESUMMARY, {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "json",
    })
    result = data.get("result", {}) or {}
    return {
        pmid: result.get(pmid) or {}
        for pmid in pmids
    }

def similarity(source: str, candidate: str) -> float:
    a = norm_title(source)
    b = norm_title(candidate)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    seq = difflib.SequenceMatcher(None, a, b).ratio()
    aset, bset = set(a.split()), set(b.split())
    overlap = len(aset & bset) / max(1, len(aset | bset))
    return max(seq, (seq + overlap) / 2)

def resolve_title(title: str) -> tuple[int | None, str | None, float]:
    pmids = pubmed_candidates(title)
    if not pmids:
        return None, None, 0.0
    time.sleep(REQUEST_PAUSE)
    summaries = pubmed_summaries(pmids)

    best = None
    for pmid in pmids:
        rec = summaries.get(pmid) or {}
        candidate_title = str(rec.get("title") or "")
        score = similarity(title, candidate_title)
        year = (
            valid_year(rec.get("sortpubdate"))
            or valid_year(rec.get("pubdate"))
            or valid_year(rec.get("epubdate"))
        )
        if not year:
            continue
        item = (score, year, pmid, candidate_title)
        if best is None or item[0] > best[0]:
            best = item

    # Conservative threshold: publication year is written only when
    # the PubMed title match is very strong.
    if not best or best[0] < 0.93:
        return None, None, (best[0] if best else 0.0)
    return best[1], best[2], best[0]

def main():
    soup = BeautifulSoup(
        LIBRARY.read_text(encoding="utf-8"),
        "html.parser"
    )

    articles = list(soup.select("article.folder-paper"))
    missing_instances_before = sum(
        1 for a in articles if existing_year(a) is None
    )

    updated_from_citation = 0
    for article in articles:
        if existing_year(article) is not None:
            continue
        year = citation_year(article)
        if year is not None:
            article["data-year"] = str(year)
            updated_from_citation += 1

    # Resolve unique missing titles only once, then apply the verified year
    # to every duplicate instance of that publication across clinical areas.
    title_instances: dict[str, list] = {}
    title_original: dict[str, str] = {}
    for article in articles:
        if existing_year(article) is not None:
            continue
        title = title_from(article)
        key = norm_title(title)
        if not key:
            continue
        title_instances.setdefault(key, []).append(article)
        title_original.setdefault(key, title)

    keys = list(title_instances)[:BATCH_MAX]
    resolutions = {}
    unresolved = []
    matched_unique = 0
    updated_instances_pubmed = 0

    for idx, key in enumerate(keys, start=1):
        title = title_original[key]
        print(f"[{idx}/{len(keys)}] Resolving: {title[:110]}")
        try:
            year, pmid, score = resolve_title(title)
        except Exception as exc:
            unresolved.append({
                "title": title,
                "reason": f"request_error: {exc}",
            })
            time.sleep(REQUEST_PAUSE)
            continue

        if year is None:
            unresolved.append({
                "title": title,
                "reason": "no_high_confidence_pubmed_match",
                "best_similarity": round(score, 4),
            })
        else:
            matched_unique += 1
            resolutions[key] = {
                "year": year,
                "pmid": pmid,
                "similarity": round(score, 4),
            }
            for article in title_instances[key]:
                article["data-year"] = str(year)
                # Store PMID if the legacy card did not already have one.
                if pmid and not article.get("data-pmid"):
                    article["data-pmid"] = pmid
                updated_instances_pubmed += 1

        time.sleep(REQUEST_PAUSE)

    LIBRARY.write_text(str(soup), encoding="utf-8")

    remaining_instances = sum(
        1 for a in soup.select("article.folder-paper")
        if existing_year(a) is None
    )
    remaining_unique_titles = {
        norm_title(title_from(a))
        for a in soup.select("article.folder-paper")
        if existing_year(a) is None and norm_title(title_from(a))
    }

    report = {
        "missing_year_instances_before": missing_instances_before,
        "updated_instances_from_existing_citation": updated_from_citation,
        "unique_titles_checked_on_pubmed": len(keys),
        "unique_titles_matched_on_pubmed": matched_unique,
        "updated_instances_from_pubmed": updated_instances_pubmed,
        "remaining_missing_year_instances": remaining_instances,
        "remaining_unique_missing_titles": len(remaining_unique_titles),
        "unresolved_sample": unresolved[:100],
    }
    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
