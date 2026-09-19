#!/usr/bin/env python3
from __future__ import annotations

import difflib
import json
import os
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "library.html"
REPORT = ROOT / "library-doi-audit.json"

NCBI_API_KEY = os.getenv("NCBI_API_KEY", "").strip()
NCBI_EMAIL = os.getenv("NCBI_EMAIL", "info@ketogenicresearch.org").strip()
BATCH = 150


def text(node):
    return "".join(node.itertext()).strip() if node is not None else ""


def norm_title(value: str) -> str:
    value = re.sub(r"^\s*\d+\.\s*", "", value or "")
    value = value.lower()
    value = value.replace("β", "beta").replace("–", "-").replace("—", "-")
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def norm_doi(value: str) -> str:
    value = (value or "").strip()
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value, flags=re.I)
    return value.rstrip(".,;").lower()


def api(endpoint: str, params: dict[str, str]) -> bytes:
    params = dict(params)
    params["tool"] = "KetogenicResearchDOIAudit"
    params["email"] = NCBI_EMAIL
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/" + endpoint + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": f"KetogenicResearchDOIAudit/1.0 ({NCBI_EMAIL})"},
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        return response.read()


def fetch_pubmed(pmids: list[str]) -> dict[str, dict]:
    out = {}
    for i in range(0, len(pmids), BATCH):
        ids = pmids[i:i+BATCH]
        root = ET.fromstring(
            api(
                "efetch.fcgi",
                {"db": "pubmed", "id": ",".join(ids), "retmode": "xml"},
            )
        )
        for item in root.findall(".//PubmedArticle"):
            citation = item.find("MedlineCitation")
            article = citation.find("Article") if citation is not None else None
            if citation is None or article is None:
                continue

            pmid = text(citation.find("PMID"))
            title = text(article.find("ArticleTitle"))
            doi = ""
            for article_id in item.findall(".//PubmedData/ArticleIdList/ArticleId"):
                if (article_id.attrib.get("IdType") or "").lower() == "doi":
                    doi = text(article_id)
                    break

            out[pmid] = {
                "title": title,
                "doi": norm_doi(doi),
            }

        if i + BATCH < len(pmids):
            time.sleep(0.35)
    return out


def card_title(card) -> str:
    h4 = card.find("h4")
    if not h4:
        return ""
    return re.sub(
        r"^\s*\d+\.\s*",
        "",
        h4.get("data-en") or h4.get_text(" ", strip=True),
    ).strip()


def extract_pmid(card) -> str:
    pmid = str(card.get("data-pmid") or "").strip()
    if pmid:
        return pmid
    for a in card.find_all("a", href=True):
        m = re.search(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)/", a["href"], re.I)
        if m:
            return m.group(1)
    return ""


def ensure_doi_link(soup, card, doi: str):
    links = card.select_one(".paper-links")
    if not links:
        return

    doi_links = []
    for a in links.find_all("a", href=True):
        if re.search(r"https?://(?:dx\.)?doi\.org/", a["href"], re.I):
            doi_links.append(a)

    if not doi:
        for a in doi_links:
            a.decompose()
        if card.has_attr("data-doi"):
            del card["data-doi"]
        return

    url = "https://doi.org/" + doi
    card["data-doi"] = doi

    if doi_links:
        primary = doi_links[0]
        primary["href"] = url
        primary["target"] = "_blank"
        primary["rel"] = "noopener"
        primary["data-en"] = "DOI ↗"
        primary["data-it"] = "DOI ↗"
        primary.string = "DOI ↗"
        for extra in doi_links[1:]:
            extra.decompose()
    else:
        a = soup.new_tag("a", href=url, target="_blank", rel="noopener")
        a["data-en"] = "DOI ↗"
        a["data-it"] = "DOI ↗"
        a.string = "DOI ↗"
        links.append(a)


def main():
    soup = BeautifulSoup(LIBRARY.read_text(encoding="utf-8"), "html.parser")
    cards = soup.select("article.folder-paper")

    cards_by_pmid = {}
    for card in cards:
        pmid = extract_pmid(card)
        if pmid:
            cards_by_pmid.setdefault(pmid, []).append(card)

    pubmed = fetch_pubmed(sorted(cards_by_pmid))

    fixed_wrong_doi = 0
    added_missing_doi = 0
    removed_spurious_doi = 0
    verified_ok = 0
    skipped_title_mismatch = []
    missing_pubmed = []

    for pmid, pmid_cards in cards_by_pmid.items():
        source = pubmed.get(pmid)
        if not source:
            missing_pubmed.append(pmid)
            continue

        correct_doi = source["doi"]
        pubmed_title = norm_title(source["title"])

        for card in pmid_cards:
            local_title_raw = card_title(card)
            local_title = norm_title(local_title_raw)
            similarity = difflib.SequenceMatcher(None, local_title, pubmed_title).ratio()

            # Do not alter a DOI if the displayed paper title and PMID appear
            # to describe different publications. Report it instead.
            if local_title and pubmed_title and similarity < 0.88:
                skipped_title_mismatch.append({
                    "pmid": pmid,
                    "library_title": local_title_raw,
                    "pubmed_title": source["title"],
                    "similarity": round(similarity, 3),
                })
                continue

            old_doi = norm_doi(card.get("data-doi") or "")
            if not old_doi:
                for a in card.find_all("a", href=True):
                    m = re.search(r"https?://(?:dx\.)?doi\.org/(.+)$", a["href"], re.I)
                    if m:
                        old_doi = norm_doi(m.group(1))
                        break

            if old_doi == correct_doi:
                verified_ok += 1
                # Still normalize the visible href.
                ensure_doi_link(soup, card, correct_doi)
            elif old_doi and correct_doi:
                ensure_doi_link(soup, card, correct_doi)
                fixed_wrong_doi += 1
            elif not old_doi and correct_doi:
                ensure_doi_link(soup, card, correct_doi)
                added_missing_doi += 1
            elif old_doi and not correct_doi:
                ensure_doi_link(soup, card, "")
                removed_spurious_doi += 1

    LIBRARY.write_text(str(soup), encoding="utf-8")

    report = {
        "cards_scanned": len(cards),
        "unique_pmids_checked": len(cards_by_pmid),
        "verified_ok": verified_ok,
        "fixed_wrong_doi": fixed_wrong_doi,
        "added_missing_doi": added_missing_doi,
        "removed_spurious_doi": removed_spurious_doi,
        "title_pmid_mismatches_not_modified": skipped_title_mismatch,
        "pmids_not_returned_by_pubmed": missing_pubmed,
    }
    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
