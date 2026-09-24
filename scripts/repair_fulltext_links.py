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
        return MANUAL_OVERRIDES[doi]
    encoded = urllib.parse.quote("https://doi.org/" + doi, safe="")
    url = "https://api.openalex.org/works/" + encoded
    try:
        data = get_json(url)
    except Exception as exc:
        return {"error": str(exc), "checked": True}
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
        # Skip if a publisher fulltext or PDF is already curated.
        publisher_links = [a for a in article.select(".paper-links a[href]") if a.get("data-source") in {"publisher","openalex"}]
        if publisher_links: continue
        doi_articles.setdefault(doi, []).append(article)

    for doi, articles in doi_articles.items():
        info = MANUAL_OVERRIDES.get(doi) or cache.get(doi)
        if info is None:
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
        "policy": "PMC remains authoritative when available. When PMCID is absent, OpenAlex OA metadata is used only if the work is explicitly open access; publisher landing-page and PDF URLs are added only when supplied by that metadata. Manually verified publisher overrides are supported for newly published works not yet indexed by OpenAlex."
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
