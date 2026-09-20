#!/usr/bin/env python3
from __future__ import annotations

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
STATE = ROOT / "library-year-backfill-state.json"

BATCH_MAX = max(1, int(os.getenv("YEAR_BACKFILL_BATCH_MAX", "300")))
REQUEST_CHUNK = max(1, int(os.getenv("YEAR_BACKFILL_REQUEST_CHUNK", "100")))
PAUSE_SECONDS = max(0, int(os.getenv("YEAR_BACKFILL_PAUSE", "2")))

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"

def extract_pmid(article):
    for a in article.find_all("a", href=True):
        m = re.search(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)/?", a["href"])
        if m:
            return m.group(1)
    text = article.get_text(" ", strip=True)
    m = re.search(r"\bPMID\s*:?\s*(\d{6,9})\b", text, re.I)
    return m.group(1) if m else None

def year_is_missing(article):
    y = (article.get("data-year") or "").strip().lower()
    return not re.fullmatch(r"(19|20)\d{2}", y)

def fetch_years(pmids):
    params = urllib.parse.urlencode({
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "json",
        "tool": "KetogenicResearch",
        "email": "info@ketogenicresearch.org",
    })
    url = EUTILS + "?" + params
    req = urllib.request.Request(url, headers={"User-Agent":"KetogenicResearch/YearBackfill/1.0"})

    last = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read().decode("utf-8"))
            out = {}
            result = data.get("result", {})
            for pmid in pmids:
                rec = result.get(pmid) or {}
                pubdate = str(rec.get("pubdate") or "")
                sortpubdate = str(rec.get("sortpubdate") or "")
                candidates = [pubdate, sortpubdate]
                year = None
                for c in candidates:
                    m = re.search(r"\b((?:19|20)\d{2})\b", c)
                    if m:
                        year = int(m.group(1))
                        break
                if year:
                    out[pmid] = year
            return out
        except Exception as exc:
            last = exc
            if attempt == 4:
                raise
            wait = 5 * (attempt + 1)
            print(f"PubMed request failed; retrying in {wait}s: {exc}")
            time.sleep(wait)
    raise RuntimeError(last)

def main():
    soup = BeautifulSoup(LIBRARY.read_text(encoding="utf-8"), "html.parser")

    targets = []
    seen_pmids = set()
    for article in soup.select("article.folder-paper"):
        if not year_is_missing(article):
            continue
        pmid = extract_pmid(article)
        if not pmid:
            continue
        if pmid in seen_pmids:
            continue
        seen_pmids.add(pmid)
        targets.append(pmid)

    batch = targets[:BATCH_MAX]

    if not batch:
        state = {
            "updated_this_run": 0,
            "remaining_with_missing_year_and_pmid": 0,
            "completed": True,
        }
        STATE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(state, indent=2))
        return

    year_map = {}
    for i in range(0, len(batch), REQUEST_CHUNK):
        chunk = batch[i:i+REQUEST_CHUNK]
        print(f"Fetching publication years for PMIDs {i+1}-{i+len(chunk)} of {len(batch)}...")
        year_map.update(fetch_years(chunk))
        if i + REQUEST_CHUNK < len(batch) and PAUSE_SECONDS:
            time.sleep(PAUSE_SECONDS)

    updated = 0
    for article in soup.select("article.folder-paper"):
        if not year_is_missing(article):
            continue
        pmid = extract_pmid(article)
        year = year_map.get(pmid)
        if not year:
            continue
        article["data-year"] = str(year)
        updated += 1

    LIBRARY.write_text(str(soup), encoding="utf-8")

    remaining = 0
    for article in soup.select("article.folder-paper"):
        if year_is_missing(article) and extract_pmid(article):
            remaining += 1

    state = {
        "updated_this_run": updated,
        "unique_pmids_requested": len(batch),
        "unique_pmids_with_year_found": len(year_map),
        "remaining_with_missing_year_and_pmid": remaining,
        "completed": remaining == 0,
    }
    STATE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(state, indent=2))

if __name__ == "__main__":
    main()
