#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

NCBI_EMAIL = os.getenv("NCBI_EMAIL", "info@ketogenicresearch.org").strip()
NCBI_API_KEY = os.getenv("NCBI_API_KEY", "").strip()
REQUEST_DELAY = 0.12 if NCBI_API_KEY else 0.36
_LAST_REQUEST = 0.0


def _text(node) -> str:
    return "".join(node.itertext()).strip() if node is not None else ""


def norm_title(value: str) -> str:
    value = re.sub(r"^\s*\d+\.\s*", "", value or "")
    value = value.lower().replace("β", "beta")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def norm_doi(value: str) -> str:
    value = (value or "").strip()
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value, flags=re.I)
    return value.rstrip(".,;").lower()


def _api(endpoint: str, params: dict[str, str]) -> bytes:
    global _LAST_REQUEST

    params = dict(params)
    params["tool"] = "KetogenicResearchBibliographyGuard"
    params["email"] = NCBI_EMAIL
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY

    url = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
        + endpoint
        + "?"
        + urllib.parse.urlencode(params)
    )

    elapsed = time.monotonic() - _LAST_REQUEST
    if elapsed < REQUEST_DELAY:
        time.sleep(REQUEST_DELAY - elapsed)

    last_error = None
    for attempt in range(6):
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": f"KetogenicResearchBibliographyGuard/1.0 ({NCBI_EMAIL})"
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                data = response.read()
                _LAST_REQUEST = time.monotonic()
                return data
        except urllib.error.HTTPError as exc:
            last_error = exc
            _LAST_REQUEST = time.monotonic()
            if exc.code == 429 or 500 <= exc.code < 600:
                wait = min(60.0, max(3.0, 2.0 * (2 ** attempt)))
                print(f"PubMed HTTP {exc.code}; retrying in {wait:.0f}s.")
                time.sleep(wait)
                continue
            raise
        except urllib.error.URLError as exc:
            last_error = exc
            wait = min(30.0, max(3.0, 2.0 * (2 ** attempt)))
            print(f"PubMed network error; retrying in {wait:.0f}s.")
            time.sleep(wait)

    raise RuntimeError(f"PubMed verification failed after retries: {last_error}")


def fetch_pubmed_records(pmids: list[str]) -> dict[str, dict]:
    """Return authoritative title/DOI/PMCID for each PMID."""
    unique = list(dict.fromkeys(str(x).strip() for x in pmids if str(x).strip()))
    out: dict[str, dict] = {}

    for i in range(0, len(unique), 150):
        batch = unique[i:i+150]
        root = ET.fromstring(
            _api(
                "efetch.fcgi",
                {
                    "db": "pubmed",
                    "id": ",".join(batch),
                    "retmode": "xml",
                },
            )
        )

        for item in root.findall(".//PubmedArticle"):
            citation = item.find("MedlineCitation")
            article = citation.find("Article") if citation is not None else None
            if citation is None or article is None:
                continue

            pmid = _text(citation.find("PMID"))
            title = _text(article.find("ArticleTitle"))
            doi = ""
            pmcid = ""

            # IMPORTANT: only identifiers in PubmedData/ArticleIdList are accepted.
            for aid in item.findall("./PubmedData/ArticleIdList/ArticleId"):
                kind = (aid.attrib.get("IdType") or "").lower()
                value = _text(aid)
                if kind == "doi" and value:
                    doi = norm_doi(value)
                elif kind == "pmc" and value:
                    pmcid = value

            out[pmid] = {
                "pmid": pmid,
                "title": title,
                "title_norm": norm_title(title),
                "doi": doi,
                "pmcid": pmcid,
                "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "doi_url": f"https://doi.org/{doi}" if doi else "",
                "pmc_url": (
                    f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"
                    if pmcid
                    else ""
                ),
            }

    return out


def verified_record(queue_record: dict, pubmed_map: dict[str, dict]) -> dict | None:
    """
    Return a copy of the queue record with PMID/DOI/links replaced by
    authoritative PubMed values. Refuse title/PMID mismatches.
    """
    pmid = str(queue_record.get("pmid") or "").strip()
    if not pmid:
        return None

    authoritative = pubmed_map.get(pmid)
    if not authoritative:
        print(f"Skipping PMID {pmid}: PubMed verification returned no record.")
        return None

    local_title = norm_title(queue_record.get("title") or "")
    pubmed_title = authoritative["title_norm"]

    if not local_title or local_title != pubmed_title:
        print(
            f"Skipping PMID {pmid}: queue title does not exactly match PubMed title."
        )
        return None

    rec = dict(queue_record)
    rec["pmid"] = pmid
    rec["doi"] = authoritative["doi"]
    rec["pmc"] = authoritative["pmcid"]
    rec["pubmed_url"] = authoritative["pubmed_url"]
    rec["doi_url"] = authoritative["doi_url"]
    rec["pmc_url"] = authoritative["pmc_url"]
    return rec
