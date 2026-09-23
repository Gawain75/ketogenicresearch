#!/usr/bin/env python3
from __future__ import annotations

import difflib
import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "library.html"
LEGACY_AUDIT = ROOT / "library-legacy-audit.json"
REPORT = ROOT / "publication-metadata-recovery.json"

NCBI_API_KEY = (os.getenv("NCBI_API_KEY") or "").strip()
NCBI_EMAIL = (os.getenv("NCBI_EMAIL") or "info@ketogenicresearch.org").strip()
MAX_TITLE_SEARCHES = max(0, int(os.getenv("METADATA_RECOVERY_TITLE_MAX", "350")))
OFFLINE = os.getenv("METADATA_RECOVERY_OFFLINE", "0").strip() == "1"
REQUEST_PAUSE = float(os.getenv("METADATA_RECOVERY_PAUSE", "0.11" if NCBI_API_KEY else "0.34"))

ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
CROSSREF = "https://api.crossref.org/works"

STOPWORDS = {
    "a", "an", "the", "of", "and", "or", "in", "on", "for", "to", "with",
    "from", "by", "as", "at", "is", "are", "be", "this", "that", "their",
}
CORRECTION_WORDS = {"corrigendum", "correction", "erratum", "retraction", "retracted"}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def norm_title(value: str) -> str:
    value = re.sub(r"^\s*\d+\.\s*", "", value or "")
    value = (
        value.lower()
        .replace("β", "beta")
        .replace("α", "alpha")
        .replace("’", "'")
        .replace("–", "-")
        .replace("—", "-")
    )
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def content_words(value: str) -> list[str]:
    return [w for w in norm_title(value).split() if w not in STOPWORDS and len(w) > 2]


def norm_doi(value: str) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value)
    value = re.sub(r"^doi:\s*", "", value)
    return value.rstrip(" .;,") if value.startswith("10.") else ""


def valid_year(value) -> int | None:
    m = re.search(r"\b((?:18|19|20)\d{2})\b", str(value or ""))
    if not m:
        return None
    year = int(m.group(1))
    return year if 1800 <= year <= datetime.now(timezone.utc).year else None


def title_from(article) -> str:
    h4 = article.find("h4")
    if not h4:
        return ""
    return (h4.get("data-en") or h4.get_text(" ", strip=True) or "").strip()


def existing_year(article) -> int | None:
    return valid_year(article.get("data-year"))


def article_pmid(article) -> str:
    raw = str(article.get("data-pmid") or "").strip()
    if re.fullmatch(r"\d{5,10}", raw):
        return raw
    for a in article.find_all("a", href=True):
        m = re.search(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)", a["href"])
        if m:
            return m.group(1)
    return ""


def article_doi(article) -> str:
    doi = norm_doi(str(article.get("data-doi") or ""))
    if doi:
        return doi
    for a in article.find_all("a", href=True):
        doi = norm_doi(a["href"])
        if doi:
            return doi
    return ""


def request_json(base: str, params: dict, attempts: int = 5, user_agent: str = "KetogenicResearch/MetadataRecovery/1.0") -> dict:
    params = dict(params)
    if "ncbi.nlm.nih.gov" in base:
        params.setdefault("tool", "KetogenicResearch")
        params.setdefault("email", NCBI_EMAIL)
        if NCBI_API_KEY:
            params.setdefault("api_key", NCBI_API_KEY)
    url = base + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    last = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            last = exc
            if attempt == attempts - 1:
                raise
            time.sleep(min(20, 2 ** (attempt + 1)))
    raise RuntimeError(last)


def pubmed_summaries(pmids: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    unique = list(dict.fromkeys(p for p in pmids if p))
    for i in range(0, len(unique), 180):
        chunk = unique[i:i + 180]
        data = request_json(ESUMMARY, {"db": "pubmed", "id": ",".join(chunk), "retmode": "json"})
        result = data.get("result", {}) or {}
        for pmid in chunk:
            if isinstance(result.get(pmid), dict):
                out[pmid] = result[pmid]
        time.sleep(REQUEST_PAUSE)
    return out


def year_from_summary(rec: dict) -> int | None:
    return valid_year(rec.get("sortpubdate")) or valid_year(rec.get("pubdate")) or valid_year(rec.get("epubdate"))


def doi_from_summary(rec: dict) -> str:
    for item in rec.get("articleids", []) or []:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("idtype") or item.get("idtypeid") or "").lower()
        value = str(item.get("value") or "")
        if kind == "doi" or value.startswith("10."):
            doi = norm_doi(value)
            if doi:
                return doi
    return ""


def similarity(source: str, candidate: str) -> tuple[float, float, float, bool, int]:
    a, b = norm_title(source), norm_title(candidate)
    if not a or not b:
        return 0.0, 0.0, 0.0, False, 0
    seq = difflib.SequenceMatcher(None, a, b).ratio()
    aset, bset = set(a.split()), set(b.split())
    inter = aset & bset
    jac = len(inter) / max(1, len(aset | bset))
    min_cover = min(len(inter) / max(1, len(aset)), len(inter) / max(1, len(bset)))
    substring = a in b or b in a
    return seq, jac, min_cover, substring, min(len(a.split()), len(b.split()))


def strong_title_match(source: str, candidate: str) -> tuple[bool, float]:
    a, b = norm_title(source), norm_title(candidate)
    if not a or not b:
        return False, 0.0
    if a == b:
        return True, 1.0

    a_corrections = CORRECTION_WORDS & set(a.split())
    b_corrections = CORRECTION_WORDS & set(b.split())
    if bool(a_corrections) != bool(b_corrections):
        return False, 0.0

    seq, jac, min_cover, substring, min_words = similarity(a, b)
    cwords = min(len(content_words(a)), len(content_words(b)))

    # Expanded/subtitled version of the same sufficiently specific title.
    if substring and min_words >= 8 and cwords >= 7 and seq >= 0.65:
        return True, max(seq, 0.93)
    if seq >= 0.94:
        return True, seq
    if seq >= 0.88 and jac >= 0.78 and min_cover >= 0.78:
        return True, seq
    return False, seq


def update_links(article, pmid: str = "", doi: str = "") -> None:
    links = article.find("div", class_="paper-links")
    if links is None:
        links = BeautifulSoup('<div class="paper-links"></div>', "html.parser").div
        article.append(links)

    # Remove placeholder PubMed title-search links once a direct identifier exists.
    if pmid or doi:
        for a in list(links.find_all("a", href=True)):
            href = a.get("href", "")
            if "pubmed.ncbi.nlm.nih.gov/?term=" in href:
                a.decompose()

    if pmid and not any(re.search(rf"pubmed\.ncbi\.nlm\.nih\.gov/{re.escape(pmid)}/?", a.get("href", "")) for a in links.find_all("a", href=True)):
        a = BeautifulSoup("<a></a>", "html.parser").a
        a["href"] = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        a["target"] = "_blank"
        a["rel"] = "noopener"
        a["data-en"] = a["data-it"] = "PubMed ↗"
        a.string = "PubMed ↗"
        links.append(a)

    doi = norm_doi(doi)
    if doi and not any(norm_doi(a.get("href", "")) == doi for a in links.find_all("a", href=True)):
        a = BeautifulSoup("<a></a>", "html.parser").a
        a["href"] = f"https://doi.org/{doi}"
        a["target"] = "_blank"
        a["rel"] = "noopener"
        a["data-en"] = a["data-it"] = "DOI ↗"
        a.string = "DOI ↗"
        links.append(a)


def set_metadata(article, year: int, pmid: str = "", doi: str = "") -> None:
    article["data-year"] = str(year)
    if pmid:
        article["data-pmid"] = str(pmid)
    doi = norm_doi(doi)
    if doi:
        article["data-doi"] = doi
    update_links(article, pmid, doi)


def load_legacy_candidates() -> dict[str, dict]:
    if not LEGACY_AUDIT.exists():
        return {}
    try:
        doc = json.loads(LEGACY_AUDIT.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out = {}
    for status in ("certain", "possible", "no_match"):
        for row in doc.get(status, []) or []:
            key = norm_title(str(row.get("library_title") or ""))
            cand = row.get("candidate") if isinstance(row, dict) else None
            if key and isinstance(cand, dict) and cand.get("pmid"):
                out[key] = {"status": status, "candidate": cand, "match_detail": row.get("match_detail") or {}}
    return out


def recover_from_dated_duplicates(articles: list) -> list[dict]:
    dated = []
    for a in articles:
        year = existing_year(a)
        if not year:
            continue
        title = title_from(a)
        dated.append((norm_title(title), title, year, article_pmid(a), article_doi(a)))

    recovered = []
    for a in articles:
        if existing_year(a):
            continue
        source = title_from(a)
        skey = norm_title(source)
        swords = skey.split()
        best = None
        for ckey, candidate_title, year, pmid, doi in dated:
            if not skey or not ckey:
                continue
            # Cheap and conservative local duplicate detection: exact title or
            # one sufficiently specific title being a literal expansion of the other.
            if skey == ckey:
                score = 1.0
            elif (skey in ckey or ckey in skey) and min(len(swords), len(ckey.split())) >= 8:
                score = 0.93
            else:
                continue
            if bool(CORRECTION_WORDS & set(skey.split())) != bool(CORRECTION_WORDS & set(ckey.split())):
                continue
            rank = (score, bool(pmid), bool(doi), len(ckey))
            if best is None or rank > best[0]:
                best = (rank, candidate_title, year, pmid, doi)
        if best:
            _, candidate_title, year, pmid, doi = best
            set_metadata(a, year, pmid, doi)
            recovered.append({"source": "dated-library-match", "title": source, "matched_title": candidate_title, "year": year, "pmid": pmid, "doi": doi, "score": round(best[0][0], 4)})
    return recovered

def recover_from_legacy_audit(articles: list) -> list[dict]:
    legacy = load_legacy_candidates()
    pending = []
    for a in articles:
        if existing_year(a):
            continue
        key = norm_title(title_from(a))
        row = legacy.get(key)
        if row:
            pending.append((a, row))
    if not pending:
        return []

    pmids = [str(row["candidate"].get("pmid")) for _, row in pending]
    summaries = {} if OFFLINE else pubmed_summaries(pmids)
    recovered = []

    for a, row in pending:
        source = title_from(a)
        cand = row["candidate"]
        pmid = str(cand.get("pmid") or "")

        if OFFLINE:
            candidate_title = str(cand.get("title") or "")
            year = valid_year(cand.get("year"))
            doi = norm_doi(str(cand.get("doi") or ""))
            # Offline mode is deliberately stricter because no fresh PubMed check occurs.
            seq, _, _, substring, min_words = similarity(source, candidate_title)
            ok = norm_title(source) == norm_title(candidate_title) or seq >= 0.94 or (substring and min_words >= 10)
            score = seq
        else:
            rec = summaries.get(pmid, {})
            candidate_title = str(rec.get("title") or "")
            year = year_from_summary(rec)
            doi = doi_from_summary(rec)
            ok, score = strong_title_match(source, candidate_title)

        if ok and year:
            set_metadata(a, year, pmid, doi)
            recovered.append({"source": "legacy-audit-pubmed" if not OFFLINE else "legacy-audit-offline", "title": source, "matched_title": candidate_title, "year": year, "pmid": pmid, "doi": doi, "score": round(score, 4)})
    return recovered


def pubmed_candidates(title: str) -> list[str]:
    clean = re.sub(r"^\s*\d+\.\s*", "", title).strip()
    queries = [f'"{clean}"[Title]']

    before_colon = clean.split(":", 1)[0].strip()
    if before_colon and before_colon != clean and len(content_words(before_colon)) >= 5:
        queries.append(f'"{before_colon}"[Title]')

    words = content_words(clean)
    if len(words) >= 5:
        distinctive = words[:10]
        queries.append(" AND ".join(f'{w}[Title]' for w in distinctive))

    seen = []
    for query in queries:
        data = request_json(ESEARCH, {"db": "pubmed", "term": query, "retmode": "json", "retmax": "10", "sort": "relevance"})
        ids = [str(x) for x in data.get("esearchresult", {}).get("idlist", []) or []]
        for pmid in ids:
            if pmid not in seen:
                seen.append(pmid)
        if len(seen) >= 10:
            break
        time.sleep(REQUEST_PAUSE)
    return seen[:10]


def resolve_pubmed_title(title: str) -> tuple[int | None, str, str, str, float]:
    pmids = pubmed_candidates(title)
    if not pmids:
        return None, "", "", "", 0.0
    summaries = pubmed_summaries(pmids)
    best = None
    for pmid, rec in summaries.items():
        candidate_title = str(rec.get("title") or "")
        year = year_from_summary(rec)
        if not year:
            continue
        ok, score = strong_title_match(title, candidate_title)
        if not ok:
            continue
        item = (score, year, pmid, doi_from_summary(rec), candidate_title)
        if best is None or item[0] > best[0]:
            best = item
    if not best:
        return None, "", "", "", 0.0
    return best[1], best[2], best[3], best[4], best[0]


def crossref_year(item: dict) -> int | None:
    for key in ("published-print", "published-online", "issued", "created"):
        block = item.get(key)
        if not isinstance(block, dict):
            continue
        parts = block.get("date-parts")
        if isinstance(parts, list) and parts and isinstance(parts[0], list) and parts[0]:
            year = valid_year(parts[0][0])
            if year:
                return year
        year = valid_year(block.get("date-time"))
        if year:
            return year
    return None


def resolve_crossref_title(title: str) -> tuple[int | None, str, str, float]:
    data = request_json(
        CROSSREF,
        {
            "query.title": re.sub(r"^\s*\d+\.\s*", "", title).strip(),
            "rows": "6",
            "mailto": NCBI_EMAIL,
        },
        user_agent=f"KetogenicResearch/MetadataRecovery/1.0 (mailto:{NCBI_EMAIL})",
    )
    best = None
    for item in (data.get("message", {}) or {}).get("items", []) or []:
        titles = item.get("title") or []
        candidate_title = str(titles[0] if titles else "")
        year = crossref_year(item)
        doi = norm_doi(str(item.get("DOI") or ""))
        if not candidate_title or not year:
            continue
        ok, score = strong_title_match(title, candidate_title)
        if not ok:
            continue
        row = (score, year, doi, candidate_title)
        if best is None or row[0] > best[0]:
            best = row
    if not best:
        return None, "", "", 0.0
    return best[1], best[2], best[3], best[0]


def main() -> None:
    soup = BeautifulSoup(LIBRARY.read_text(encoding="utf-8"), "html.parser")
    articles = list(soup.select("article.folder-paper"))
    missing_before = [a for a in articles if existing_year(a) is None]

    resolved: list[dict] = []
    resolved.extend(recover_from_dated_duplicates(articles))
    resolved.extend(recover_from_legacy_audit(articles))

    attempted_pubmed = 0
    attempted_crossref = 0

    if not OFFLINE:
        remaining_groups: dict[str, list] = {}
        originals: dict[str, str] = {}
        for a in articles:
            if existing_year(a):
                continue
            key = norm_title(title_from(a))
            if key:
                remaining_groups.setdefault(key, []).append(a)
                originals.setdefault(key, title_from(a))

        for idx, key in enumerate(list(remaining_groups)[:MAX_TITLE_SEARCHES], 1):
            title = originals[key]
            print(f"[metadata {idx}/{min(MAX_TITLE_SEARCHES, len(remaining_groups))}] {title[:120]}")
            attempted_pubmed += 1
            try:
                year, pmid, doi, matched_title, score = resolve_pubmed_title(title)
            except Exception as exc:
                print(f"  PubMed error: {exc}")
                year = None

            source = "pubmed-title-search"
            if not year:
                attempted_crossref += 1
                try:
                    year, doi, matched_title, score = resolve_crossref_title(title)
                    pmid = ""
                    source = "crossref-title-search"
                except Exception as exc:
                    print(f"  Crossref error: {exc}")
                    year = None

            if year:
                for a in remaining_groups[key]:
                    set_metadata(a, year, pmid, doi)
                resolved.append({"source": source, "title": title, "matched_title": matched_title, "year": year, "pmid": pmid, "doi": doi, "score": round(score, 4)})
            time.sleep(REQUEST_PAUSE)

    LIBRARY.write_text(str(soup), encoding="utf-8")

    remaining = [a for a in soup.select("article.folder-paper") if existing_year(a) is None]
    unique_remaining = {}
    for a in remaining:
        key = norm_title(title_from(a))
        if key:
            unique_remaining.setdefault(key, title_from(a))

    report = {
        "version": "metadata-recovery-v1",
        "run_at": now_iso(),
        "offline": OFFLINE,
        "missing_year_instances_before": len(missing_before),
        "recovered_instances": len(missing_before) - len(remaining),
        "resolved_unique_titles": len({norm_title(x["title"]) for x in resolved}),
        "remaining_missing_year_instances": len(remaining),
        "remaining_unique_missing_titles": len(unique_remaining),
        "pubmed_title_searches_attempted": attempted_pubmed,
        "crossref_title_searches_attempted": attempted_crossref,
        "resolved": resolved,
        "unresolved_titles": list(unique_remaining.values()),
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in {"resolved", "unresolved_titles"}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
