#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "library.html"
REPORT = ROOT / "research-details-backfill-report.json"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
EMAIL = os.getenv("NCBI_EMAIL", "info@ketogenicresearch.org").strip()
API_KEY = os.getenv("NCBI_API_KEY", "").strip()
DELAY = 0.12 if API_KEY else 0.36
UA = f"KetogenicResearchResearchDetails/1.0 ({EMAIL})"


def clean_title(value: str) -> str:
    value = re.sub(r"^\s*\d+\.\s*", "", value or "")
    return re.sub(r"\s+", " ", value).strip()


def norm_title(value: str) -> str:
    value = clean_title(value).lower().replace("β", "beta")
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def norm_doi(value: str) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value, flags=re.I)
    return value.rstrip(".,; )]")


def request(url: str, data: bytes | None = None, accept: str = "application/json") -> bytes:
    headers = {"User-Agent": UA, "Accept": accept}
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    last = None
    for attempt in range(6):
        req = urllib.request.Request(url, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=75) as response:
                body = response.read()
            time.sleep(DELAY)
            return body
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
            if isinstance(exc, urllib.error.HTTPError) and exc.code not in (429, 500, 502, 503, 504):
                raise
            wait = min(45, 3 * (2 ** attempt))
            print(f"Network error; retry {attempt + 1}/6 in {wait}s: {exc}")
            time.sleep(wait)
    raise RuntimeError(f"Request failed after retries: {last}")


def eutils(endpoint: str, params: dict[str, str]) -> bytes:
    params = dict(params)
    params.update({"tool": "KetogenicResearchResearchDetails", "email": EMAIL})
    if API_KEY:
        params["api_key"] = API_KEY
    encoded = urllib.parse.urlencode(params).encode("utf-8")
    base = f"{EUTILS}/{endpoint}"
    if endpoint == "efetch.fcgi" or len(encoded) > 1800:
        return request(base, data=encoded, accept="application/xml")
    return request(f"{base}?{encoded.decode('utf-8')}")


def text(node) -> str:
    return "" if node is None else "".join(node.itertext()).strip()


def parse_pubmed(item) -> dict | None:
    citation = item.find("MedlineCitation")
    article = citation.find("Article") if citation is not None else None
    if citation is None or article is None:
        return None
    pmid = text(citation.find("PMID"))
    title = text(article.find("ArticleTitle"))
    abstract = " ".join(
        text(n) for n in article.findall("Abstract/AbstractText") if text(n)
    ).strip()
    doi = ""
    pmcid = ""
    for aid in item.findall("./PubmedData/ArticleIdList/ArticleId"):
        kind = (aid.attrib.get("IdType") or "").lower()
        value = text(aid)
        if kind == "doi" and value:
            doi = norm_doi(value)
        elif kind == "pmc" and value:
            pmcid = value
    return {
        "pmid": pmid,
        "title": title,
        "title_norm": norm_title(title),
        "abstract": abstract,
        "doi": doi,
        "pmcid": pmcid,
    }


def _fetch_pubmed_batch(batch: list[str], depth: int = 0) -> dict[str, dict]:
    """Fetch a PubMed batch robustly.

    NCBI occasionally returns a truncated or malformed XML payload even when
    the HTTP request itself succeeds. Retry the same batch, then split it into
    smaller batches so one bad response cannot abort the entire backfill.
    """
    if not batch:
        return {}

    last_error = None
    for attempt in range(4):
        try:
            payload = eutils("efetch.fcgi", {
                "db": "pubmed",
                "id": ",".join(batch),
                "retmode": "xml",
            })
            root = ET.fromstring(payload)
            out = {}
            for item in root.findall(".//PubmedArticle"):
                rec = parse_pubmed(item)
                if rec and rec["pmid"]:
                    out[rec["pmid"]] = rec
            return out
        except ET.ParseError as exc:
            last_error = exc
            wait = min(20, 2 ** attempt * 2)
            print(
                f"Malformed PubMed XML for batch of {len(batch)} records "
                f"(attempt {attempt + 1}/4): {exc}. Retrying in {wait}s..."
            )
            time.sleep(wait)

    if len(batch) == 1:
        print(
            f"WARNING: unable to parse PubMed XML for PMID {batch[0]} "
            f"after retries: {last_error}. The record will be resolved by "
            "DOI/title fallback when possible."
        )
        return {}

    mid = len(batch) // 2
    print(
        f"Splitting malformed PubMed batch of {len(batch)} into "
        f"{mid} + {len(batch) - mid} records."
    )
    left = _fetch_pubmed_batch(batch[:mid], depth + 1)
    right = _fetch_pubmed_batch(batch[mid:], depth + 1)
    left.update(right)
    return left


def fetch_pmids(pmids: list[str]) -> dict[str, dict]:
    unique = list(dict.fromkeys(p for p in pmids if p and p.isdigit()))
    out = {}
    batch_size = 50
    total_batches = (len(unique) + batch_size - 1) // batch_size
    for i in range(0, len(unique), batch_size):
        batch = unique[i:i + batch_size]
        out.update(_fetch_pubmed_batch(batch))
        print(f"Fetched PubMed batch {i // batch_size + 1}/{total_batches}.")
    return out


def search_pubmed(term: str, retmax: int = 5) -> list[str]:
    data = json.loads(eutils("esearch.fcgi", {
        "db": "pubmed", "term": term, "retmode": "json", "retmax": str(retmax),
    }).decode("utf-8"))
    return data.get("esearchresult", {}).get("idlist", [])


def resolve_pubmed_by_doi(doi: str) -> dict | None:
    ids = search_pubmed(f'"{doi}"[AID]', 3)
    if not ids:
        return None
    recs = fetch_pmids(ids)
    target = norm_doi(doi)
    for rec in recs.values():
        if rec.get("doi") == target:
            return rec
    return next(iter(recs.values()), None)


def resolve_pubmed_by_title(title: str) -> dict | None:
    safe = clean_title(title).replace('"', "")
    if not safe:
        return None
    ids = search_pubmed(f'"{safe}"[Title]', 5)
    if not ids:
        return None
    recs = fetch_pmids(ids)
    nt = norm_title(title)
    ranked = sorted(
        ((SequenceMatcher(None, nt, rec.get("title_norm", "")).ratio(), rec)
         for rec in recs.values()),
        reverse=True,
        key=lambda x: x[0],
    )
    return ranked[0][1] if ranked and ranked[0][0] >= 0.93 else None


def crossref_abstract(doi: str) -> str:
    if not doi:
        return ""
    url = (
        "https://api.crossref.org/works/"
        + urllib.parse.quote(doi, safe="")
        + "?mailto=" + urllib.parse.quote(EMAIL)
    )
    try:
        data = json.loads(request(url).decode("utf-8"))
    except Exception:
        return ""
    raw = ((data.get("message") or {}).get("abstract") or "").strip()
    if not raw:
        return ""
    soup = BeautifulSoup(html.unescape(raw), "html.parser")
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()


def extract_ids(card) -> tuple[str, str]:
    pmid = str(card.get("data-pmid") or "").strip()
    doi = norm_doi(str(card.get("data-doi") or ""))

    if not pmid:
        for a in card.select("a[href]"):
            href = a.get("href") or ""
            m = re.search(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)/", href, re.I)
            if m:
                pmid = m.group(1)
                break

    if not doi:
        for a in card.select("a[href]"):
            href = a.get("href") or ""
            m = re.search(r"https?://(?:dx\.)?doi\.org/([^?#]+)", href, re.I)
            if m:
                doi = norm_doi(m.group(1))
                break

    return pmid, doi


def add_details(soup, card, content: str, source: str) -> None:
    details = soup.new_tag("details", attrs={"class": "paper-study-details"})
    details["data-detail-source"] = source

    summary = soup.new_tag("summary")
    summary["data-en"] = "Research details"
    summary["data-it"] = "Dettagli della ricerca"
    summary.string = "Research details"
    details.append(summary)

    p = soup.new_tag("p")
    p["class"] = "paper-source-abstract"
    p["data-en"] = content
    p["data-it"] = content
    p.string = content
    details.append(p)

    links = card.select_one(".paper-links")
    if links:
        links.insert_before(details)
    else:
        card.append(details)


def main() -> None:
    soup = BeautifulSoup(LIBRARY.read_text(encoding="utf-8"), "html.parser")
    missing = [
        card for card in soup.select("article.folder-paper")
        if card.select_one("details.paper-study-details") is None
    ]
    print(f"Cards missing Research details: {len(missing)}")
    if not missing:
        return

    entries = []
    pmids = []
    for card in missing:
        h4 = card.find("h4")
        title = clean_title(
            (h4.get("data-en") if h4 else "")
            or (h4.get_text(" ", strip=True) if h4 else "")
        )
        pmid, doi = extract_ids(card)
        entries.append({"card": card, "title": title, "pmid": pmid, "doi": doi})
        if pmid:
            pmids.append(pmid)

    pubmed = fetch_pmids(pmids)
    doi_cache = {}
    title_cache = {}
    crossref_cache = {}

    counts = {
        "pubmed_abstract": 0,
        "crossref_abstract": 0,
        "no_abstract_notice": 0,
        "pmid_resolved_by_doi": 0,
        "pmid_resolved_by_title": 0,
    }
    unresolved = []

    for idx, entry in enumerate(entries, start=1):
        card = entry["card"]
        rec = pubmed.get(entry["pmid"]) if entry["pmid"] else None

        if rec is None and entry["doi"]:
            if entry["doi"] not in doi_cache:
                doi_cache[entry["doi"]] = resolve_pubmed_by_doi(entry["doi"])
            rec = doi_cache[entry["doi"]]
            if rec:
                counts["pmid_resolved_by_doi"] += 1

        if rec is None and entry["title"]:
            key = norm_title(entry["title"])
            if key not in title_cache:
                title_cache[key] = resolve_pubmed_by_title(entry["title"])
            rec = title_cache[key]
            if rec:
                counts["pmid_resolved_by_title"] += 1

        if rec:
            if rec.get("pmid"):
                card["data-pmid"] = rec["pmid"]
            if rec.get("doi"):
                card["data-doi"] = rec["doi"]
            abstract = (rec.get("abstract") or "").strip()
            if abstract:
                add_details(soup, card, abstract, "pubmed-abstract")
                counts["pubmed_abstract"] += 1
                continue
            if not entry["doi"] and rec.get("doi"):
                entry["doi"] = rec["doi"]

        abstract = ""
        if entry["doi"]:
            if entry["doi"] not in crossref_cache:
                crossref_cache[entry["doi"]] = crossref_abstract(entry["doi"])
            abstract = crossref_cache[entry["doi"]]

        if abstract:
            add_details(soup, card, abstract, "crossref-abstract")
            counts["crossref_abstract"] += 1
        else:
            notice = (
                "No abstract is available from the indexed bibliographic sources for this record. "
                "Use the PubMed, DOI, full-text or PDF links below when available."
            )
            add_details(soup, card, notice, "no-indexed-abstract")
            counts["no_abstract_notice"] += 1
            unresolved.append({
                "title": entry["title"], "pmid": entry["pmid"], "doi": entry["doi"]
            })

        if idx % 250 == 0:
            print(f"Processed {idx}/{len(entries)} cards.")

    LIBRARY.write_text(str(soup), encoding="utf-8")
    report = {
        "cards_missing_before": len(missing),
        "cards_missing_after": len([
            c for c in soup.select("article.folder-paper")
            if c.select_one("details.paper-study-details") is None
        ]),
        **counts,
        "records_without_indexed_abstract": unresolved,
    }
    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(
        {k: v for k, v in report.items() if k != "records_without_indexed_abstract"},
        indent=2,
    ))


if __name__ == "__main__":
    main()
