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
        m = re.search(
            r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)/?",
            a["href"],
            re.I,
        )
        if m:
            return m.group(1)

    return None


def link_text(a):
    return " ".join(
        [
            a.get_text(" ", strip=True),
            a.get("data-en") or "",
            a.get("data-it") or "",
        ]
    ).lower()


def is_fulltext_link(a):
    txt = link_text(a)
    href = (a.get("href") or "").lower()
    return (
        "full text" in txt
        or "testo completo" in txt
        or (
            "pmc.ncbi.nlm.nih.gov/articles/" in href
            and "/pdf/" not in href
        )
    )


def is_pdf_link(a):
    txt = link_text(a)
    href = (a.get("href") or "").lower()
    return (
        re.search(r"\bpdf\b", txt) is not None
        or (
            "pmc.ncbi.nlm.nih.gov/articles/" in href
            and "/pdf/" in href
        )
    )


def request_xml(pmids):
    data = urllib.parse.urlencode(
        {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml",
            "tool": "KetogenicResearch-PMCGuard",
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        EFETCH,
        data=data,
        headers={
            "User-Agent": "KetogenicResearch/PMCGuard/2.0",
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
        chunk = pmids[start : start + CHUNK]
        print(
            f"Checking PMIDs {start + 1}-"
            f"{start + len(chunk)} of {len(pmids)}..."
        )

        root = ET.fromstring(request_xml(chunk))

        for item in root.findall(".//PubmedArticle"):
            pmid_node = item.find(".//MedlineCitation/PMID")
            if pmid_node is None or not (pmid_node.text or "").strip():
                continue

            pmid = pmid_node.text.strip()
            pmcid = None

            for aid in item.findall(".//PubmedData/ArticleIdList/ArticleId"):
                if (aid.attrib.get("IdType") or "").lower() != "pmc":
                    continue
                value = (aid.text or "").strip()
                if value:
                    pmcid = (
                        value
                        if value.upper().startswith("PMC")
                        else "PMC" + value
                    )
                    break

            out[pmid] = pmcid

        time.sleep(0.4)

    return out


def ensure_links_container(soup, article):
    links = article.select_one(":scope > .paper-links")
    if links is None:
        links = soup.new_tag("div")
        links["class"] = ["paper-links"]
        article.append(links)
    return links


def new_link(soup, href, en, it, kind):
    a = soup.new_tag(
        "a",
        href=href,
        target="_blank",
        rel="noopener",
    )
    a["data-en"] = en
    a["data-it"] = it
    a["data-source"] = "pmc"
    a["data-link-kind"] = kind
    a.string = en
    return a


def main():
    soup = BeautifulSoup(
        LIBRARY.read_text(encoding="utf-8"),
        "html.parser",
    )

    cards = []
    pmids = set()

    for article in soup.select("article.folder-paper"):
        pmid = extract_pmid(article)
        if not pmid:
            continue
        cards.append((article, pmid))
        pmids.add(pmid)

    verified = fetch_verified_pmcids(sorted(pmids)) if pmids else {}

    cards_with_pmc = 0
    fulltext_added = 0
    fulltext_corrected = 0
    fulltext_removed = 0
    pdf_added = 0
    pdf_corrected = 0
    pdf_removed = 0

    for article, pmid in cards:
        pmcid = verified.get(pmid)
        links = ensure_links_container(soup, article)

        full_links = [
            a
            for a in links.find_all("a", href=True, recursive=False)
            if is_fulltext_link(a)
        ]
        pdf_links = [
            a
            for a in links.find_all("a", href=True, recursive=False)
            if is_pdf_link(a)
        ]

        # De-duplicate in case an old link matches both rules.
        pdf_ids = {id(a) for a in pdf_links}
        full_links = [a for a in full_links if id(a) not in pdf_ids]

        if not pmcid:
            # Remove only PMC-managed/PMC-hosted links. Do not delete a
            # legitimate publisher PDF that may have been curated manually.
            for a in list(full_links):
                href = (a.get("href") or "").lower()
                if (
                    a.get("data-source") == "pmc"
                    or "pmc.ncbi.nlm.nih.gov/articles/" in href
                ):
                    a.decompose()
                    fulltext_removed += 1

            for a in list(pdf_links):
                href = (a.get("href") or "").lower()
                if (
                    a.get("data-source") == "pmc"
                    or "pmc.ncbi.nlm.nih.gov/articles/" in href
                ):
                    a.decompose()
                    pdf_removed += 1

            article.attrs.pop("data-pmcid", None)
            continue

        cards_with_pmc += 1
        article["data-pmcid"] = pmcid

        full_url = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"
        pdf_url = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/pdf/"

        # ----- Full text -----
        if full_links:
            keep = full_links[0]
            if (keep.get("href") or "").rstrip("/") + "/" != full_url:
                keep["href"] = full_url
                fulltext_corrected += 1

            keep["target"] = "_blank"
            keep["rel"] = "noopener"
            keep["data-en"] = "Full text ↗"
            keep["data-it"] = "Testo completo ↗"
            keep["data-source"] = "pmc"
            keep["data-link-kind"] = "fulltext"
            keep.string = "Full text ↗"

            for extra in full_links[1:]:
                extra.decompose()
                fulltext_removed += 1
        else:
            links.append(
                new_link(
                    soup,
                    full_url,
                    "Full text ↗",
                    "Testo completo ↗",
                    "fulltext",
                )
            )
            fulltext_added += 1

        # ----- Direct PDF -----
        if pdf_links:
            keep = pdf_links[0]
            if (keep.get("href") or "").rstrip("/") + "/" != pdf_url:
                keep["href"] = pdf_url
                pdf_corrected += 1

            keep["target"] = "_blank"
            keep["rel"] = "noopener"
            keep["data-en"] = "PDF ↓"
            keep["data-it"] = "PDF ↓"
            keep["data-source"] = "pmc"
            keep["data-link-kind"] = "pdf"
            keep["aria-label"] = "Open PDF"
            keep.string = "PDF ↓"

            for extra in pdf_links[1:]:
                extra.decompose()
                pdf_removed += 1
        else:
            pdf_link = new_link(
                soup,
                pdf_url,
                "PDF ↓",
                "PDF ↓",
                "pdf",
            )
            pdf_link["aria-label"] = "Open PDF"
            links.append(pdf_link)
            pdf_added += 1

    LIBRARY.write_text(str(soup), encoding="utf-8")

    report = {
        "library_cards_with_pmid": len(cards),
        "unique_pmids_checked": len(pmids),
        "verified_pmcid_available": cards_with_pmc,
        "fulltext_links_added": fulltext_added,
        "fulltext_links_corrected": fulltext_corrected,
        "fulltext_links_removed": fulltext_removed,
        "pdf_links_added": pdf_added,
        "pdf_links_corrected": pdf_corrected,
        "pdf_links_removed": pdf_removed,
        "policy": (
            "Full text and PDF links are automatically created only when "
            "PubMed ArticleIdList supplies a PMCID for the same PMID. "
            "PDF points to the direct PubMed Central /pdf/ endpoint. "
            "Non-PMC publisher PDF links are not invented or automatically removed."
        ),
    }

    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
