#!/usr/bin/env python3
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "library.html"
REPORT = ROOT / "fulltext-link-audit.json"
OA_CACHE = ROOT / "publisher-oa-cache.json"
MAX_NEW_OA_LOOKUPS = 300
UA = "KetogenicResearchHub/1.0 (+https://www.ketogenicresearch.org/)"

MANUAL_OVERRIDES = {
    "10.1093/milmed/usag429": {
        "is_oa": True,
        "landing_page_url": "https://academic.oup.com/milmed/advance-article/doi/10.1093/milmed/usag429/8812765",
        "pdf_url": None,
        "source": "publisher-verified",
    },
}

def get_json(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_html(url, timeout=25):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        final_url = r.geturl()
        content_type = (r.headers.get("Content-Type") or "").lower()
        body = r.read().decode("utf-8", errors="replace")
    return final_url, content_type, body


def looks_like_pdf_url(url):
    value = (url or "").lower()
    return (
        value.endswith(".pdf")
        or "/pdf/" in value
        or "/content/pdf/" in value
        or "downloadpdf" in value
        or "download/pdf" in value
    )


def verify_pdf_url(url, timeout=20):
    if not url:
        return False
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": UA,
                "Accept": "application/pdf,*/*;q=0.8",
                "Range": "bytes=0-1023",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            content_type = (r.headers.get("Content-Type") or "").lower()
            final_url = (r.geturl() or "").lower()
            head = r.read(16)
        return (
            "application/pdf" in content_type
            or final_url.endswith(".pdf")
            or head.startswith(b"%PDF")
        )
    except Exception:
        return False


def publisher_pdf_from_landing(landing_url):
    """Find a legal publisher PDF advertised by the article landing page."""
    if not landing_url:
        return None

    try:
        final_url, content_type, html = fetch_html(landing_url)
    except Exception:
        return None

    if "application/pdf" in content_type and verify_pdf_url(final_url):
        return final_url

    soup = BeautifulSoup(html, "html.parser")
    candidates = []

    # Standard scholarly metadata. Springer Nature exposes citation_pdf_url.
    for meta_name in (
        "citation_pdf_url",
        "dc.identifier",
        "eprints.document_url",
        "wkhealth_pdf_url",
    ):
        for meta in soup.find_all("meta"):
            name = (meta.get("name") or meta.get("property") or "").strip().lower()
            if name != meta_name:
                continue
            value = (meta.get("content") or "").strip()
            if value and (meta_name == "citation_pdf_url" or looks_like_pdf_url(value)):
                candidates.append(urllib.parse.urljoin(final_url, value))

    for link in soup.find_all("link", href=True):
        kind = (link.get("type") or "").lower()
        rel = " ".join(link.get("rel") or []).lower()
        href = urllib.parse.urljoin(final_url, link.get("href"))
        if "application/pdf" in kind or ("alternate" in rel and looks_like_pdf_url(href)):
            candidates.append(href)

    for a in soup.find_all("a", href=True):
        href = urllib.parse.urljoin(final_url, a.get("href"))
        label = a.get_text(" ", strip=True).lower()
        if (
            looks_like_pdf_url(href)
            or "download pdf" in label
            or label == "pdf"
        ):
            candidates.append(href)

    # Springer Nature has a stable publisher PDF path even when metadata
    # aggregators have not indexed the newly published PDF yet.
    m = re.search(r"10\.1007/[^?#]+", final_url, re.I)
    if "link.springer.com/article/" in final_url and m:
        doi = m.group(0).rstrip("/")
        candidates.append(f"https://link.springer.com/content/pdf/{doi}.pdf")

    seen = set()
    for candidate in candidates:
        candidate = candidate.strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        if verify_pdf_url(candidate):
            return candidate

    return None

def is_fulltext_link(a):
    return a.get("data-link-kind") == "fulltext" or "full text" in a.get_text(" ", strip=True).lower() or "testo completo" in a.get_text(" ", strip=True).lower()

def is_pdf_link(a):
    return a.get("data-link-kind") == "pdf" or a.get_text(" ", strip=True).lower().startswith("pdf")

def ensure_links_container(soup, article):
    links = article.select_one(".paper-links")
    if links is None:
        links = soup.new_tag("div", attrs={"class": "paper-links"})
        article.append(links)
    return links

def new_link(soup, href, en, it, kind, source=None):
    a = soup.new_tag("a", href=href, target="_blank", rel="noopener")
    a["data-en"] = en
    a["data-it"] = it
    a["data-link-kind"] = kind
    if source:
        a["data-source"] = source
    a.string = en
    return a

def infer_missing_pmids(soup):
    n = 0
    for article in soup.select("article.folder-paper"):
        if article.get("data-pmid"):
            continue
        for a in article.select(".paper-links a[href]"):
            m = re.search(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)", a.get("href", ""))
            if m:
                article["data-pmid"] = m.group(1)
                n += 1
                break
    return n

def fetch_verified_pmcids(pmids):
    out = {}
    # NCBI efetch in batches
    for i in range(0, len(pmids), 150):
        batch = pmids[i:i+150]
        url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&retmode=xml&id=" + ",".join(batch)
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                xml = r.read().decode("utf-8", errors="replace")
        except Exception:
            continue
        try:
            root = ET.fromstring(xml)
        except ET.ParseError:
            continue
        for rec in root.findall(".//PubmedArticle"):
            p = rec.find(".//MedlineCitation/PMID")
            if p is None or not (p.text or "").strip():
                continue
            pmid = (p.text or "").strip()
            pmcid = None
            for aid in rec.findall(".//PubmedData/ArticleIdList/ArticleId"):
                if aid.attrib.get("IdType") == "pmc" and (aid.text or "").strip():
                    pmcid = (aid.text or "").strip()
                    break
            out[pmid] = pmcid
        time.sleep(0.35)
    return out

def load_cache():
    if OA_CACHE.exists():
        try:
            obj = json.loads(OA_CACHE.read_text(encoding="utf-8"))
            if isinstance(obj, dict): return obj
        except Exception:
            pass
    return {}

def openalex_lookup(doi):
    if doi in MANUAL_OVERRIDES:
        result = dict(MANUAL_OVERRIDES[doi])
    else:
        encoded = urllib.parse.quote("https://doi.org/" + doi, safe="")
        url = "https://api.openalex.org/works/" + encoded
        try:
            data = get_json(url)
        except Exception as exc:
            data = {}
            result = {"error": str(exc), "checked": True}
        else:
            oa = data.get("open_access") or {}
            best = data.get("best_oa_location") or {}
            result = {
                "checked": True,
                "is_oa": bool(oa.get("is_oa")),
                "oa_status": oa.get("oa_status"),
                "landing_page_url": best.get("landing_page_url"),
                "pdf_url": best.get("pdf_url"),
                "license": best.get("license") or oa.get("oa_status"),
                "source": "openalex",
            }

    # OpenAlex can lag behind newly published OA articles. Resolve the DOI
    # landing page and inspect publisher metadata when the PDF is missing.
    landing = result.get("landing_page_url") or f"https://doi.org/{doi}"
    if result.get("is_oa") and not result.get("pdf_url"):
        discovered_pdf = publisher_pdf_from_landing(landing)
        if discovered_pdf:
            result["pdf_url"] = discovered_pdf
            result["landing_page_url"] = landing
            result["source"] = "publisher-metadata"

    return result

def add_or_update_publisher_links(soup, article, info):
    if not info or not info.get("is_oa"):
        return (0,0)
    links = ensure_links_container(soup, article)
    added_full = added_pdf = 0
    landing = info.get("landing_page_url")
    pdf = info.get("pdf_url")
    existing_full = [a for a in links.find_all("a", href=True, recursive=False) if is_fulltext_link(a)]
    existing_pdf = [a for a in links.find_all("a", href=True, recursive=False) if is_pdf_link(a)]
    if landing and not existing_full:
        a = new_link(soup, landing, "Full text ↗", "Testo completo ↗", "fulltext", "publisher")
        links.append(a); added_full += 1
    if pdf and not existing_pdf:
        a = new_link(soup, pdf, "PDF ↓", "PDF ↓", "pdf", "publisher")
        a["aria-label"] = "Open PDF"
        links.append(a); added_pdf += 1
    return added_full, added_pdf

def main():
    soup = BeautifulSoup(LIBRARY.read_text(encoding="utf-8"), "html.parser")
    inferred_pmids = infer_missing_pmids(soup)
    cards = [a for a in soup.select("article.folder-paper") if a.get("data-pmid")]
    pmids = sorted({str(a.get("data-pmid")).strip() for a in cards if a.get("data-pmid")})
    verified = fetch_verified_pmcids(pmids) if pmids else {}

    cards_with_pmc = fulltext_added = fulltext_corrected = fulltext_removed = 0
    pdf_added = pdf_corrected = pdf_removed = 0
    publisher_full_added = publisher_pdf_added = 0
    cache = load_cache()
    new_lookups = 0

    # First pass: authoritative PMC links + clean stale PMC links.
    for article in cards:
        pmid = str(article.get("data-pmid") or "").strip()
        pmcid = verified.get(pmid)
        links = ensure_links_container(soup, article)
        full_links = [a for a in links.find_all("a", href=True, recursive=False) if is_fulltext_link(a)]
        pdf_links = [a for a in links.find_all("a", href=True, recursive=False) if is_pdf_link(a)]
        pdf_ids = {id(a) for a in pdf_links}
        full_links = [a for a in full_links if id(a) not in pdf_ids]

        if not pmcid:
            for a in list(full_links):
                href = (a.get("href") or "").lower()
                if a.get("data-source") == "pmc" or "pmc.ncbi.nlm.nih.gov/articles/" in href:
                    a.decompose(); fulltext_removed += 1
            for a in list(pdf_links):
                href = (a.get("href") or "").lower()
                if a.get("data-source") == "pmc" or "pmc.ncbi.nlm.nih.gov/articles/" in href:
                    a.decompose(); pdf_removed += 1
            article.attrs.pop("data-pmcid", None)
            continue

        cards_with_pmc += 1
        article["data-pmcid"] = pmcid
        full_url = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"
        pdf_url = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/pdf/"

        full_links = [a for a in links.find_all("a", href=True, recursive=False) if is_fulltext_link(a)]
        pmc_full = next((a for a in full_links if a.get("data-source") == "pmc" or "pmc.ncbi.nlm.nih.gov/articles/" in (a.get("href") or "")), None)
        if pmc_full:
            if pmc_full.get("href") != full_url: pmc_full["href"] = full_url; fulltext_corrected += 1
            pmc_full["data-source"]="pmc"; pmc_full["data-link-kind"]="fulltext"; pmc_full["data-en"]="Full text ↗"; pmc_full["data-it"]="Testo completo ↗"; pmc_full.string="Full text ↗"
        else:
            links.append(new_link(soup, full_url, "Full text ↗", "Testo completo ↗", "fulltext", "pmc")); fulltext_added += 1

        pdf_links = [a for a in links.find_all("a", href=True, recursive=False) if is_pdf_link(a)]
        pmc_pdf = next((a for a in pdf_links if a.get("data-source") == "pmc" or "pmc.ncbi.nlm.nih.gov/articles/" in (a.get("href") or "")), None)
        if pmc_pdf:
            if pmc_pdf.get("href") != pdf_url: pmc_pdf["href"] = pdf_url; pdf_corrected += 1
            pmc_pdf["data-source"]="pmc"; pmc_pdf["data-link-kind"]="pdf"; pmc_pdf["data-en"]="PDF ↓"; pmc_pdf["data-it"]="PDF ↓"; pmc_pdf["aria-label"]="Open PDF"; pmc_pdf.string="PDF ↓"
        else:
            a=new_link(soup,pdf_url,"PDF ↓","PDF ↓","pdf","pmc"); a["aria-label"]="Open PDF"; links.append(a); pdf_added += 1

    # Second pass: DOI-only records. Use OpenAlex OA metadata with persistent cache.
    doi_articles = {}
    for article in soup.select("article.folder-paper[data-doi]"):
        if article.get("data-pmcid"): continue
        doi = str(article.get("data-doi") or "").strip().lower()
        if not doi: continue
        # Revisit DOI records until both publisher full text and PDF are
        # present. This allows newly published articles to gain a PDF later.
        publisher_links = [
            a for a in article.select(".paper-links a[href]")
            if a.get("data-source") in {"publisher", "openalex", "publisher-metadata"}
        ]
        has_full = any(is_fulltext_link(a) for a in publisher_links)
        has_pdf = any(is_pdf_link(a) for a in publisher_links)
        if has_full and has_pdf:
            continue
        doi_articles.setdefault(doi, []).append(article)

    for doi, articles in doi_articles.items():
        info = MANUAL_OVERRIDES.get(doi) or cache.get(doi)
        needs_refresh = (
            info is None
            or (
                bool(info.get("is_oa"))
                and not info.get("pdf_url")
            )
        )
        if needs_refresh:
            if new_lookups >= MAX_NEW_OA_LOOKUPS:
                continue
            info = openalex_lookup(doi)
            cache[doi] = info
            new_lookups += 1
            time.sleep(0.08)
        for article in articles:
            f,p = add_or_update_publisher_links(soup, article, info)
            publisher_full_added += f; publisher_pdf_added += p

    LIBRARY.write_text(str(soup), encoding="utf-8")
    OA_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    report = {
        "library_cards_with_pmid": len(cards),
        "pmid_attributes_inferred_from_pubmed_links": inferred_pmids,
        "unique_pmids_checked": len(pmids),
        "verified_pmcid_available": cards_with_pmc,
        "pmc_fulltext_links_added": fulltext_added,
        "pmc_pdf_links_added": pdf_added,
        "publisher_oa_new_lookups": new_lookups,
        "publisher_fulltext_links_added": publisher_full_added,
        "publisher_pdf_links_added": publisher_pdf_added,
        "publisher_oa_cache_entries": len(cache),
        "policy": "PMC remains authoritative when available. When PMCID is absent, OpenAlex OA metadata is checked first. For explicitly open-access works whose PDF is not yet indexed by OpenAlex, the publisher landing page is inspected for scholarly PDF metadata and verified direct PDF links. Cached OA records without a PDF are refreshed on later runs."
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
