#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "library.html"
STATE = ROOT / "library-2025-year-repair-state.json"

TARGET_YEAR = 2025
BATCH_MAX = max(1, int(os.getenv("YEAR_2025_BATCH_MAX", "150")))
PAUSE = float(os.getenv("NCBI_PAUSE_SECONDS", "0.4"))

ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"

def norm_title(value: str) -> str:
    value = re.sub(r"^\s*\d+\.\s*", "", value or "")
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = value.lower()
    return re.sub(r"[^a-z0-9]+", "", value)

def title_from(article) -> str:
    h = article.find("h4")
    if not h:
        return ""
    return (h.get("data-en") or h.get_text(" ", strip=True)).strip()

def doi_from(article) -> str | None:
    for a in article.find_all("a", href=True):
        href = urllib.parse.unquote(a["href"])
        m = re.search(r"(?:doi\.org/|doi:\s*)(10\.\d{4,9}/[^\s?#\"'<>]+)", href, re.I)
        if m:
            return m.group(1).rstrip(".,;)").lower()
    text = article.get_text(" ", strip=True)
    m = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", text, re.I)
    return m.group(0).rstrip(".,;)").lower() if m else None

def year_missing(article) -> bool:
    return not re.fullmatch(r"(19|20)\d{2}", (article.get("data-year") or "").strip())

def request_json(url: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "KetogenicResearch/Repair2025/1.0"}
    )
    last = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as exc:
            last = exc
            if attempt == 4:
                raise
            wait = 4 * (attempt + 1)
            print(f"NCBI request failed; retrying in {wait}s: {exc}")
            time.sleep(wait)
    raise RuntimeError(last)

def search_pubmed(article) -> list[str]:
    doi = doi_from(article)
    title = title_from(article)

    if doi:
        term = f'"{doi}"[aid] AND {TARGET_YEAR}[pdat]'
    elif title:
        # Restrict the search to 2025; exact title is verified afterwards.
        cleaned = re.sub(r'["\[\]]', " ", re.sub(r"^\s*\d+\.\s*", "", title)).strip()
        term = f'"{cleaned}"[Title] AND {TARGET_YEAR}[pdat]'
    else:
        return []

    params = urllib.parse.urlencode({
        "db": "pubmed",
        "term": term,
        "retmode": "json",
        "retmax": 5,
        "tool": "KetogenicResearch",
    })
    data = request_json(ESEARCH + "?" + params)
    time.sleep(PAUSE)
    return data.get("esearchresult", {}).get("idlist", [])

def verify_2025_match(article, pmids: list[str]) -> bool:
    if not pmids:
        return False

    params = urllib.parse.urlencode({
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "json",
        "tool": "KetogenicResearch",
    })
    data = request_json(ESUMMARY + "?" + params)
    time.sleep(PAUSE)

    expected_title = norm_title(title_from(article))
    expected_doi = (doi_from(article) or "").lower()

    result = data.get("result", {})
    for pmid in pmids:
        rec = result.get(pmid) or {}
        pubdate = str(rec.get("pubdate") or "")
        sortpubdate = str(rec.get("sortpubdate") or "")
        if not any(re.search(r"\b2025\b", x) for x in (pubdate, sortpubdate)):
            continue

        if expected_doi:
            articleids = rec.get("articleids") or []
            dois = {
                str(x.get("value") or "").lower()
                for x in articleids
                if str(x.get("idtype") or "").lower() == "doi"
            }
            if expected_doi in dois:
                return True

        candidate_title = norm_title(str(rec.get("title") or ""))
        if expected_title and candidate_title == expected_title:
            return True

    return False

def load_offset() -> int:
    if not STATE.exists():
        return 0
    try:
        return int(json.loads(STATE.read_text(encoding="utf-8")).get("offset", 0))
    except Exception:
        return 0

def main():
    soup = BeautifulSoup(LIBRARY.read_text(encoding="utf-8"), "html.parser")

    candidates = [
        a for a in soup.select("article.folder-paper")
        if year_missing(a) and (doi_from(a) or title_from(a))
    ]

    offset = load_offset()
    if offset >= len(candidates):
        offset = 0

    batch = candidates[offset:offset + BATCH_MAX]
    checked = 0
    corrected = 0

    for i, article in enumerate(batch, 1):
        checked += 1
        title = re.sub(r"^\s*\d+\.\s*", "", title_from(article))
        print(f"[{i}/{len(batch)}] Checking: {title[:100]}")
        try:
            pmids = search_pubmed(article)
            if verify_2025_match(article, pmids):
                article["data-year"] = str(TARGET_YEAR)
                corrected += 1
                print("  -> confirmed 2025")
        except Exception as exc:
            print(f"  -> skipped after error: {exc}")

    LIBRARY.write_text(str(soup), encoding="utf-8")

    next_offset = offset + len(batch)
    completed_pass = next_offset >= len(candidates)

    state = {
        "target_year": TARGET_YEAR,
        "checked_this_run": checked,
        "corrected_to_2025_this_run": corrected,
        "candidate_records_at_start": len(candidates),
        "offset": 0 if completed_pass else next_offset,
        "completed_full_pass": completed_pass,
    }
    STATE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(state, indent=2))

if __name__ == "__main__":
    main()
