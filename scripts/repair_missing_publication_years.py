#!/usr/bin/env python3
from __future__ import annotations

import difflib
import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "library.html"
REPORT = ROOT / "publication-year-recovery.json"
CACHE = ROOT / "publication-year-recovery-cache.json"

NCBI_API_KEY = (os.getenv("NCBI_API_KEY") or "").strip()
NCBI_EMAIL = (os.getenv("NCBI_EMAIL") or "info@ketogenicresearch.org").strip()

# Only title-only records need slow individual PubMed searches.
# Identifier-based recovery is batched and much faster.
TITLE_SEARCH_MAX = max(0, int(os.getenv("YEAR_RECOVERY_TITLE_MAX", "40")))
RETRY_DAYS = max(1, int(os.getenv("YEAR_RECOVERY_RETRY_DAYS", "30")))
REQUEST_PAUSE = float(os.getenv(
    "YEAR_RECOVERY_PAUSE",
    "0.11" if NCBI_API_KEY else "0.34"
))

ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
IDCONV = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"

def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def norm_title(value: str) -> str:
    value = re.sub(r"^\s*\d+\.\s*", "", value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = value.replace("β", "beta").replace("α", "alpha")
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())

def norm_doi(value: str) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value)
    value = re.sub(r"^doi:\s*", "", value)
    return value.rstrip(" .;,") if value.startswith("10.") else ""

def title_from(article) -> str:
    h4 = article.find("h4")
    if not h4:
        return ""
    return (h4.get("data-en") or h4.get_text(" ", strip=True) or "").strip()

def article_pmid(article) -> str:
    raw = str(article.get("data-pmid") or "").strip()
    if re.fullmatch(r"\d{5,10}", raw):
        return raw
    for a in article.find_all("a", href=True):
        m = re.search(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)", a["href"])
        if m:
            return m.group(1)
    text = article.get_text(" ", strip=True)
    m = re.search(r"\bPMID\s*:?\s*(\d{5,10})\b", text, re.I)
    return m.group(1) if m else ""

def article_doi(article) -> str:
    doi = norm_doi(str(article.get("data-doi") or ""))
    if doi:
        return doi
    for a in article.find_all("a", href=True):
        doi = norm_doi(a["href"])
        if doi:
            return doi
    text = article.get_text(" ", strip=True)
    m = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", text, re.I)
    return norm_doi(m.group(0)) if m else ""

def valid_year(value) -> int | None:
    m = re.search(r"\b((?:18|19|20)\d{2})\b", str(value or ""))
    if not m:
        return None
    y = int(m.group(1))
    current = datetime.now(timezone.utc).year
    return y if 1800 <= y <= current else None

def existing_year(article) -> int | None:
    return valid_year(article.get("data-year"))

def citation_year(article) -> int | None:
    # Inspect bibliographic paragraphs only; never infer from the title.
    for p in article.find_all("p", recursive=False):
        text = p.get_text(" ", strip=True)
        for pattern in (
            r"\b(?:Year|Published|Publication date|Publication year)\s*:?\s*((?:18|19|20)\d{2})\b",
            r"(?:^|[·.;,(]\s*)((?:18|19|20)\d{2})(?:[-/]\d{1,2}(?:[-/]\d{1,2})?)?(?=\s|[;:.,)])",
        ):
            m = re.search(pattern, text, re.I)
            if m:
                y = valid_year(m.group(1))
                if y:
                    return y
    return None

def request_json(base: str, params: dict, attempts: int = 4) -> dict:
    params = dict(params)
    params.setdefault("tool", "KetogenicResearch")
    params.setdefault("email", NCBI_EMAIL)
    if NCBI_API_KEY and "api_key" not in params:
        params["api_key"] = NCBI_API_KEY
    url = base + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "KetogenicResearch/PublicationYearRecovery/2.0"},
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
            time.sleep(min(15, 2 * attempt))
    raise RuntimeError(last)

def pubmed_summaries(pmids: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    unique = list(dict.fromkeys(p for p in pmids if p))
    for i in range(0, len(unique), 200):
        chunk = unique[i:i+200]
        data = request_json(ESUMMARY, {
            "db": "pubmed",
            "id": ",".join(chunk),
            "retmode": "json",
        })
        result = data.get("result", {}) or {}
        for pmid in chunk:
            if isinstance(result.get(pmid), dict):
                out[pmid] = result[pmid]
        time.sleep(REQUEST_PAUSE)
    return out

def year_from_summary(rec: dict) -> int | None:
    return (
        valid_year(rec.get("sortpubdate"))
        or valid_year(rec.get("pubdate"))
        or valid_year(rec.get("epubdate"))
    )

def doi_to_pmids(dois: list[str]) -> dict[str, str]:
    """Resolve DOI -> PMID in batches via NCBI ID Converter."""
    out: dict[str, str] = {}
    unique = list(dict.fromkeys(d for d in dois if d))
    for i in range(0, len(unique), 100):
        chunk = unique[i:i+100]
        params = {
            "ids": ",".join(chunk),
            "format": "json",
            "tool": "KetogenicResearch",
            "email": NCBI_EMAIL,
        }
        try:
            data = request_json(IDCONV, params)
        except Exception:
            continue
        for rec in data.get("records", []) or []:
            doi = norm_doi(str(rec.get("doi") or ""))
            pmid = str(rec.get("pmid") or "").strip()
            if doi and re.fullmatch(r"\d{5,10}", pmid):
                out[doi] = pmid
        time.sleep(REQUEST_PAUSE)
    return out

def similarity(source: str, candidate: str) -> float:
    a, b = norm_title(source), norm_title(candidate)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    seq = difflib.SequenceMatcher(None, a, b).ratio()
    aset, bset = set(a.split()), set(b.split())
    overlap = len(aset & bset) / max(1, len(aset | bset))
    containment = min(
        len(aset & bset) / max(1, len(aset)),
        len(aset & bset) / max(1, len(bset)),
    )
    return max(seq, 0.55 * seq + 0.30 * overlap + 0.15 * containment)

def pubmed_candidates(title: str) -> list[str]:
    clean = re.sub(r"^\s*\d+\.\s*", "", title).strip()
    # First exact title. If absent, use distinctive title words instead of
    # sending the whole punctuation-heavy string.
    queries = [f'"{clean}"[Title]']
    words = [w for w in re.findall(r"[A-Za-z0-9]+", clean) if len(w) > 3]
    if words:
        compact = " ".join(words[:18])
        queries.append(f"{compact}[Title]")
    for query in queries:
        data = request_json(ESEARCH, {
            "db": "pubmed",
            "term": query,
            "retmode": "json",
            "retmax": "8",
            "sort": "relevance",
        })
        ids = [str(x) for x in data.get("esearchresult", {}).get("idlist", []) or []]
        if ids:
            return ids
        time.sleep(REQUEST_PAUSE)
    return []

def resolve_title(title: str) -> tuple[int | None, str | None, float]:
    pmids = pubmed_candidates(title)
    if not pmids:
        return None, None, 0.0
    summaries = pubmed_summaries(pmids)
    best = None
    for pmid, rec in summaries.items():
        candidate_title = str(rec.get("title") or "")
        score = similarity(title, candidate_title)
        year = year_from_summary(rec)
        if not year:
            continue
        item = (score, year, pmid)
        if best is None or item[0] > best[0]:
            best = item
    if not best:
        return None, None, 0.0

    # Exact/near-exact only. Identifier matching is used whenever available,
    # so title-only matching remains deliberately conservative.
    threshold = 0.90
    if best[0] < threshold:
        return None, None, best[0]
    return best[1], best[2], best[0]

def load_cache() -> dict:
    if not CACHE.exists():
        return {"version": 2, "titles": {}}
    try:
        data = json.loads(CACHE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError
        data.setdefault("version", 2)
        data.setdefault("titles", {})
        return data
    except Exception:
        return {"version": 2, "titles": {}}

def should_retry(entry: dict | None) -> bool:
    if not entry:
        return True
    if entry.get("status") == "resolved":
        return False
    tried = entry.get("last_tried_at")
    if not tried:
        return True
    try:
        dt = datetime.fromisoformat(tried.replace("Z", "+00:00"))
    except Exception:
        return True
    return datetime.now(timezone.utc) - dt >= timedelta(days=RETRY_DAYS)

def set_year(article, year: int, pmid: str = "", doi: str = "") -> None:
    article["data-year"] = str(year)
    if pmid and not article.get("data-pmid"):
        article["data-pmid"] = pmid
    if doi and not article.get("data-doi"):
        article["data-doi"] = doi

def main():
    soup = BeautifulSoup(LIBRARY.read_text(encoding="utf-8"), "html.parser")
    articles = list(soup.select("article.folder-paper"))
    missing_before = sum(existing_year(a) is None for a in articles)

    counts = {
        "from_citation": 0,
        "from_duplicate_identifier": 0,
        "from_duplicate_title": 0,
        "from_cache": 0,
        "from_pmid_batch": 0,
        "from_doi_batch": 0,
        "from_title_search": 0,
    }

    # 1) Free local recovery from bibliographic text.
    for a in articles:
        if existing_year(a) is not None:
            continue
        y = citation_year(a)
        if y:
            set_year(a, y)
            counts["from_citation"] += 1

    # 2) Build trusted indexes from already-dated instances.
    by_pmid: dict[str, int] = {}
    by_doi: dict[str, int] = {}
    by_title: dict[str, int] = {}
    title_conflicts: set[str] = set()

    for a in articles:
        y = existing_year(a)
        if not y:
            continue
        p, d, t = article_pmid(a), article_doi(a), norm_title(title_from(a))
        if p:
            by_pmid[p] = y
        if d:
            by_doi[d] = y
        if t:
            if t in by_title and by_title[t] != y:
                title_conflicts.add(t)
            else:
                by_title[t] = y
    for t in title_conflicts:
        by_title.pop(t, None)

    # 3) Propagate years to duplicate instances locally: zero network calls.
    for a in articles:
        if existing_year(a) is not None:
            continue
        p, d, t = article_pmid(a), article_doi(a), norm_title(title_from(a))
        if p and p in by_pmid:
            set_year(a, by_pmid[p], pmid=p, doi=d)
            counts["from_duplicate_identifier"] += 1
        elif d and d in by_doi:
            set_year(a, by_doi[d], pmid=p, doi=d)
            counts["from_duplicate_identifier"] += 1
        elif t and t in by_title:
            set_year(a, by_title[t], pmid=p, doi=d)
            counts["from_duplicate_title"] += 1

    cache = load_cache()
    cache_titles = cache["titles"]

    # 4) Reuse prior successful title resolutions.
    for a in articles:
        if existing_year(a) is not None:
            continue
        key = norm_title(title_from(a))
        entry = cache_titles.get(key) if key else None
        y = valid_year((entry or {}).get("year"))
        if entry and entry.get("status") == "resolved" and y:
            set_year(
                a, y,
                pmid=str(entry.get("pmid") or ""),
                doi=article_doi(a),
            )
            counts["from_cache"] += 1

    # 5) Batch PMID lookup. One request can resolve hundreds of records.
    missing = [a for a in articles if existing_year(a) is None]
    pmid_articles: dict[str, list] = {}
    for a in missing:
        p = article_pmid(a)
        if p:
            pmid_articles.setdefault(p, []).append(a)
    summaries = pubmed_summaries(list(pmid_articles))
    for p, group in pmid_articles.items():
        y = year_from_summary(summaries.get(p, {}))
        if not y:
            continue
        for a in group:
            set_year(a, y, pmid=p, doi=article_doi(a))
            counts["from_pmid_batch"] += 1

    # 6) Batch DOI -> PMID conversion, then batch PubMed summary.
    missing = [a for a in articles if existing_year(a) is None]
    doi_articles: dict[str, list] = {}
    for a in missing:
        d = article_doi(a)
        if d:
            doi_articles.setdefault(d, []).append(a)

    doi_pmids = doi_to_pmids(list(doi_articles))
    doi_summaries = pubmed_summaries(list(doi_pmids.values()))
    for d, p in doi_pmids.items():
        y = year_from_summary(doi_summaries.get(p, {}))
        if not y:
            continue
        for a in doi_articles.get(d, []):
            set_year(a, y, pmid=p, doi=d)
            counts["from_doi_batch"] += 1

    # 7) Slow title search only for records with no useful identifier.
    # Failed titles are cached and skipped for RETRY_DAYS.
    title_groups: dict[str, list] = {}
    originals: dict[str, str] = {}
    for a in articles:
        if existing_year(a) is not None:
            continue
        key = norm_title(title_from(a))
        if not key:
            continue
        title_groups.setdefault(key, []).append(a)
        originals.setdefault(key, title_from(a))

    candidates = [
        key for key in title_groups
        if should_retry(cache_titles.get(key))
    ][:TITLE_SEARCH_MAX]

    attempted = 0
    resolved_unique = 0
    unresolved_sample = []

    for idx, key in enumerate(candidates, 1):
        title = originals[key]
        attempted += 1
        print(f"[title {idx}/{len(candidates)}] {title[:115]}")
        try:
            y, p, score = resolve_title(title)
        except Exception as exc:
            cache_titles[key] = {
                "status": "unresolved",
                "last_tried_at": now_iso(),
                "reason": f"request_error: {exc}",
            }
            unresolved_sample.append({
                "title": title,
                "reason": "request_error",
            })
            continue

        if y and p:
            resolved_unique += 1
            cache_titles[key] = {
                "status": "resolved",
                "year": y,
                "pmid": p,
                "similarity": round(score, 4),
                "last_tried_at": now_iso(),
            }
            for a in title_groups[key]:
                set_year(a, y, pmid=p, doi=article_doi(a))
                counts["from_title_search"] += 1
        else:
            cache_titles[key] = {
                "status": "unresolved",
                "last_tried_at": now_iso(),
                "reason": "no_high_confidence_pubmed_match",
                "best_similarity": round(score, 4),
            }
            unresolved_sample.append({
                "title": title,
                "reason": "no_high_confidence_pubmed_match",
                "best_similarity": round(score, 4),
            })
        time.sleep(REQUEST_PAUSE)

    cache["version"] = 2
    cache["updated_at"] = now_iso()
    CACHE.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    LIBRARY.write_text(str(soup), encoding="utf-8")

    remaining = [a for a in soup.select("article.folder-paper") if existing_year(a) is None]
    remaining_unique = {
        norm_title(title_from(a))
        for a in remaining if norm_title(title_from(a))
    }

    report = {
        "missing_year_instances_before": missing_before,
        "recovered_this_run": missing_before - len(remaining),
        **counts,
        "title_searches_attempted": attempted,
        "title_searches_resolved_unique": resolved_unique,
        "remaining_missing_year_instances": len(remaining),
        "remaining_unique_missing_titles": len(remaining_unique),
        "title_search_retry_days": RETRY_DAYS,
        "unresolved_sample": unresolved_sample[:50],
    }
    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
