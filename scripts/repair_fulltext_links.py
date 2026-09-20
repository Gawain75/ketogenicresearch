#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "library.html"
REPORT = ROOT / "fulltext-link-audit.json"

EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
CHUNK = 100


def extract_pmid(article):
    pmid = (article.get("data-pmid") or "").strip()
    if pmid:
        return pmid
    for a in article.find_all("a", href=True):
        m = re.search(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)/?", a["href"], re.I)
        if m:
            return m.group(1)
    return None


def is_fulltext_link(a):
    txt = " ".join([
        a.get_text(" ", strip=True),
        a.get("data-en") or "",
        a.get("data-it") or "",
    ]).lower()
    return (
        "full text" in txt
        or "testo completo" in txt
        or "pmc.ncbi.nlm.nih.gov/articles/" in (a.get("href") or "").lower()
    )


def request_xml(pmids):
    data = urllib.parse.urlencode({
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
        "tool": "KetogenicResearch-FullTextGuard",
    }).encode("utf-8")

    req = urllib.request.Request(
        EFETCH,
        data=data,
        headers={
            "User-Agent": "KetogenicResearch/FullTextGuard/1.0",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )

    last = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read()
        except Exception as exc:
            last = exc
            if attempt == 4:
                raise
            wait = 5 * (attempt + 1)
            print(f"PubMed request failed; retrying in {wait}s: {exc}")
            time.sleep(wait)
    raise RuntimeError(last)


def fetch_verified_pmcids(pmids):
    out = {}
    for start in range(0, len(pmids), CHUNK):
        chunk = pmids[start:start + CHUNK]
        print(f"Checking PMIDs {start + 1}-{start + len(chunk)} of {len(pmids)}...")
        root = ET.fromstring(request_xml(chunk))

        for item in root.findall(".//PubmedArticle"):
            pmid_node = item.find(".//MedlineCitation/PMID")
            if pmid_node is None or not (pmid_node.text or "").strip():
                continue
            pmid = pmid_node.text.strip()
            pmcid = None

            for aid in item.findall(".//PubmedData/ArticleIdList/ArticleId"):
                if (aid.attrib.get("IdType") or "").lower() == "pmc":
                    value = (aid.text or "").strip()
                    if value:
                        pmcid = value if value.upper().startswith("PMC") else "PMC" + value
                        break

            out[pmid] = pmcid

        time.sleep(0.4)

    return out


def main():
    soup = BeautifulSoup(LIBRARY.read_text(encoding="utf-8"), "html.parser")

    articles_with_fulltext = []
    pmids = set()

    for article in soup.select("article.folder-paper"):
        full_links = [a for a in article.find_all("a", href=True) if is_fulltext_link(a)]
        if not full_links:
            continue

        pmid = extract_pmid(article)
        articles_with_fulltext.append((article, pmid, full_links))
        if pmid:
            pmids.add(pmid)

    verified = fetch_verified_pmcids(sorted(pmids)) if pmids else {}

    corrected = 0
    removed = 0
    already_correct = 0
    no_pmid_removed = 0

    for article, pmid, links in articles_with_fulltext:
        expected_pmcid = verified.get(pmid) if pmid else None
        expected_url = (
            f"https://pmc.ncbi.nlm.nih.gov/articles/{expected_pmcid}/"
            if expected_pmcid else None
        )

        # Keep only one verified Full text link per card.
        first = True
        for a in list(links):
            if expected_url and first:
                current = (a.get("href") or "").rstrip("/") + "/"
                if current != expected_url:
                    a["href"] = expected_url
                    corrected += 1
                else:
                    already_correct += 1

                a["target"] = "_blank"
                a["rel"] = "noopener"
                a["data-en"] = "Full text ↗"
                a["data-it"] = "Testo completo ↗"
                a.string = "Full text ↗"
                first = False
            else:
                a.decompose()
                removed += 1
                if not pmid:
                    no_pmid_removed += 1

    LIBRARY.write_text(str(soup), encoding="utf-8")

    report = {
        "cards_with_fulltext_links": len(articles_with_fulltext),
        "unique_pmids_checked": len(pmids),
        "verified_pmcid_available": sum(1 for v in verified.values() if v),
        "corrected_wrong_fulltext_links": corrected,
        "removed_unverified_or_duplicate_fulltext_links": removed,
        "already_correct": already_correct,
        "links_removed_because_no_pmid": no_pmid_removed,
        "policy": (
            "A Full text link is retained only when PubMed ArticleIdList "
            "provides a PMCID for the same PMID. Otherwise the Full text link is removed."
        ),
    }

    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
