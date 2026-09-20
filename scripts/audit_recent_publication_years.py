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
STATE = ROOT / "library-recent-year-audit-state.json"

START_YEAR = int(os.getenv("YEAR_AUDIT_START", "2024"))
END_YEAR = int(os.getenv("YEAR_AUDIT_END", "2026"))
BATCH_MAX = max(1, int(os.getenv("YEAR_AUDIT_BATCH_MAX", "300")))
REQUEST_CHUNK = max(1, int(os.getenv("YEAR_AUDIT_REQUEST_CHUNK", "100")))
PAUSE = max(0.0, float(os.getenv("YEAR_AUDIT_PAUSE", "1.0")))

ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"

def extract_pmid(article):
    for a in article.find_all("a", href=True):
        m = re.search(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)/?", a["href"])
        if m:
            return m.group(1)
    text = article.get_text(" ", strip=True)
    m = re.search(r"\bPMID\s*:?\s*(\d{6,9})\b", text, re.I)
    return m.group(1) if m else None

def request_json(url):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "KetogenicResearch/RecentYearAudit/1.0"}
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
            wait = 5 * (attempt + 1)
            print(f"NCBI request failed; retrying in {wait}s: {exc}")
            time.sleep(wait)
    raise RuntimeError(last)

def fetch_years(pmids):
    params = urllib.parse.urlencode({
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "json",
        "tool": "KetogenicResearch",
    })
    data = request_json(ESUMMARY + "?" + params)
    result = data.get("result", {})
    out = {}

    for pmid in pmids:
        rec = result.get(pmid) or {}
        candidates = [
            str(rec.get("sortpubdate") or ""),
            str(rec.get("pubdate") or ""),
            str(rec.get("epubdate") or ""),
        ]

        year = None
        for value in candidates:
            m = re.search(r"\b((?:19|20)\d{2})\b", value)
            if m:
                year = int(m.group(1))
                break

        if year is not None:
            out[pmid] = year

    return out

def load_offset():
    if not STATE.exists():
        return 0
    try:
        return int(json.loads(STATE.read_text(encoding="utf-8")).get("offset", 0))
    except Exception:
        return 0

def main():
    soup = BeautifulSoup(LIBRARY.read_text(encoding="utf-8"), "html.parser")

    pmids = []
    seen = set()
    for article in soup.select("article.folder-paper"):
        pmid = extract_pmid(article)
        if pmid and pmid not in seen:
            seen.add(pmid)
            pmids.append(pmid)

    offset = load_offset()
    if offset >= len(pmids):
        offset = 0

    batch = pmids[offset:offset + BATCH_MAX]
    year_map = {}

    for i in range(0, len(batch), REQUEST_CHUNK):
        chunk = batch[i:i + REQUEST_CHUNK]
        print(f"Checking PMIDs {offset+i+1}-{offset+i+len(chunk)} of {len(pmids)}...")
        year_map.update(fetch_years(chunk))
        if i + REQUEST_CHUNK < len(batch) and PAUSE:
            time.sleep(PAUSE)

    changed_instances = 0
    changed_unique_pmids = set()
    corrected_to_2025 = set()
    corrected_from_2025 = set()

    for article in soup.select("article.folder-paper"):
        pmid = extract_pmid(article)
        if not pmid or pmid not in year_map:
            continue

        verified_year = year_map[pmid]
        if verified_year < START_YEAR or verified_year > END_YEAR:
            continue

        old = (article.get("data-year") or "").strip()
        new = str(verified_year)

        if old != new:
            article["data-year"] = new
            changed_instances += 1
            changed_unique_pmids.add(pmid)

            if verified_year == 2025:
                corrected_to_2025.add(pmid)
            if old == "2025" and verified_year != 2025:
                corrected_from_2025.add(pmid)

    LIBRARY.write_text(str(soup), encoding="utf-8")

    next_offset = offset + len(batch)
    completed = next_offset >= len(pmids)

    state = {
        "audit_range": [START_YEAR, END_YEAR],
        "unique_pmids_total": len(pmids),
        "unique_pmids_checked_this_run": len(batch),
        "unique_pmids_with_pubmed_year": len(year_map),
        "changed_card_instances_this_run": changed_instances,
        "changed_unique_pmids_this_run": len(changed_unique_pmids),
        "corrected_to_2025_this_run": len(corrected_to_2025),
        "corrected_from_2025_this_run": len(corrected_from_2025),
        "offset": 0 if completed else next_offset,
        "completed_full_pass": completed,
    }

    STATE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(state, indent=2))

if __name__ == "__main__":
    main()
