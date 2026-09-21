#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "library.html"
STYLES = ROOT / "styles.css"

NCBI_EMAIL = os.getenv("NCBI_EMAIL", "info@ketogenicresearch.org").strip()
NCBI_API_KEY = os.getenv("NCBI_API_KEY", "").strip()
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

SUBCATEGORY_ID = "obesity-glp1-keto"
STYLE_MARKER = "/* Static Obesity GLP-1RA + ketogenic subcategory */"

GLP_TERMS = (
    "glp-1", "glp1", "glp-1ra", "glp1ra", "glp-1 receptor agonist",
    "glucagon-like peptide-1", "incretin",
    "semaglutide", "liraglutide", "dulaglutide", "exenatide",
    "lixisenatide", "tirzepatide", "retatrutide", "survodutide",
    "orforglipron", "cagrisema",
)

KETO_TERMS = (
    "ketogenic", "ketosis", "ketone", "ketones",
    "ketonemia", "ketonaemia", "beta-hydroxybutyrate",
    "β-hydroxybutyrate", "b-hydroxybutyrate", "bhb",
    "ketone ester", "ketone esters", "exogenous ketone",
    "exogenous ketones", "vlckd", "vlekt",
    "low-energy ketogenic", "very low-calorie ketogenic",
    "very-low-calorie ketogenic", "keto diet",
)

def _text(node) -> str:
    if node is None:
        return ""
    return " ".join("".join(node.itertext()).split())

def _api(endpoint: str, params: dict[str, str]) -> bytes:
    params = dict(params)
    params["tool"] = "KetogenicResearchGlp1KetoIndex"
    params["email"] = NCBI_EMAIL
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY

    url = EUTILS + "/" + endpoint + "?" + urllib.parse.urlencode(params)
    waits = [2, 5, 10, 20, 40, 60]

    for attempt in range(len(waits) + 1):
        req = urllib.request.Request(
            url,
            headers={"User-Agent": f"KetogenicResearchGlp1KetoIndex/1.0 ({NCBI_EMAIL})"},
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if (exc.code == 429 or 500 <= exc.code < 600) and attempt < len(waits):
                wait = waits[attempt]
                print(f"PubMed HTTP {exc.code}; retrying in {wait}s.")
                time.sleep(wait)
                continue
            raise
        except urllib.error.URLError:
            if attempt < len(waits):
                wait = waits[attempt]
                print(f"PubMed network error; retrying in {wait}s.")
                time.sleep(wait)
                continue
            raise

    raise RuntimeError("PubMed request failed after retries")

def fetch_pubmed_text(pmids: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    unique = list(dict.fromkeys(p for p in pmids if p))

    for i in range(0, len(unique), 150):
        batch = unique[i:i + 150]
        root = ET.fromstring(
            _api(
                "efetch.fcgi",
                {"db": "pubmed", "id": ",".join(batch), "retmode": "xml"},
            )
        )

        for item in root.findall(".//PubmedArticle"):
            citation = item.find("MedlineCitation")
            article = citation.find("Article") if citation is not None else None
            if citation is None or article is None:
                continue

            pmid = _text(citation.find("PMID"))
            title = _text(article.find("ArticleTitle"))
            abstract = " ".join(_text(n) for n in article.findall("Abstract/AbstractText"))
            mesh = " ".join(
                _text(n)
                for n in citation.findall("MeshHeadingList/MeshHeading/DescriptorName")
            )
            keywords = " ".join(
                _text(n)
                for n in citation.findall("KeywordList/Keyword")
            )

            out[pmid] = " ".join((title, abstract, mesh, keywords)).lower()

        if i + 150 < len(unique):
            time.sleep(0.4 if not NCBI_API_KEY else 0.15)

    return out

def matches_intersection(text: str) -> bool:
    text = (text or "").lower()
    return (
        any(term in text for term in GLP_TERMS)
        and any(term in text for term in KETO_TERMS)
    )

def card_pmid(card) -> str:
    pmid = str(card.get("data-pmid") or "").strip()
    if pmid:
        return pmid
    for a in card.find_all("a", href=True):
        m = re.search(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)/", a["href"], re.I)
        if m:
            return m.group(1)
    return ""

def make_display_card(soup: BeautifulSoup, source):
    card = soup.new_tag("article")
    card["class"] = ["topic-subfolder-paper"]

    for selector in (".evidence-level", "h4", "p", ".paper-links"):
        node = source.select_one(selector)
        if node:
            clone = BeautifulSoup(str(node), "html.parser").find()
            if clone:
                card.append(clone)

    return card

def rebuild_subcategory():
    soup = BeautifulSoup(LIBRARY.read_text(encoding="utf-8"), "html.parser")

    for old in soup.find_all(id=SUBCATEGORY_ID):
        old.decompose()

    topic_filter = soup.find(id="topicFilter")
    if topic_filter is not None:
        topic_filter.decompose()

    obesity = soup.find("details", id="obesity")
    if obesity is None:
        raise RuntimeError("Obesity clinical area (#obesity) not found")

    body = obesity.select_one(".folder-body")
    curated = obesity.select_one(".folder-curated")
    if body is None or curated is None:
        raise RuntimeError("Obesity folder structure not found")

    original_cards = list(curated.select(":scope > article.folder-paper"))
    pmid_to_card = {}
    for card in original_cards:
        pmid = card_pmid(card)
        if pmid:
            pmid_to_card.setdefault(pmid, card)

    if not pmid_to_card:
        raise RuntimeError("No PMID-backed publications found in Obesity")

    print(f"Checking {len(pmid_to_card)} PMID-backed Obesity publications against PubMed.")
    pubmed_text = fetch_pubmed_text(list(pmid_to_card))

    matches = [
        pmid for pmid in pmid_to_card
        if matches_intersection(pubmed_text.get(pmid, ""))
    ]

    sub = soup.new_tag("details")
    sub["id"] = SUBCATEGORY_ID
    sub["class"] = ["library-topic-subfolder"]

    summary = soup.new_tag("summary")

    heading = soup.new_tag("span")
    heading["class"] = ["topic-subfolder-title"]

    strong = soup.new_tag("strong")
    strong["data-en"] = "GLP-1RA + ketogenic / ketosis / ketones"
    strong["data-it"] = "GLP-1RA + chetogenica / chetosi / chetoni"
    strong.string = strong["data-en"]

    small = soup.new_tag("small")
    small["data-en"] = "Studies combining GLP-1-based therapies with ketogenic interventions, ketosis or ketone biology"
    small["data-it"] = "Studi che combinano terapie basate su GLP-1 con interventi chetogenici, chetosi o biologia dei chetoni"
    small.string = small["data-en"]

    heading.append(strong)
    heading.append(small)

    count = soup.new_tag("span")
    count["class"] = ["topic-subfolder-count"]
    count.string = str(len(matches))

    arrow = soup.new_tag("span")
    arrow["class"] = ["topic-subfolder-arrow"]
    arrow.string = "＋"

    summary.append(heading)
    summary.append(count)
    summary.append(arrow)
    sub.append(summary)

    sub_body = soup.new_tag("div")
    sub_body["class"] = ["topic-subfolder-body"]

    intro = soup.new_tag("p")
    intro["class"] = ["topic-subfolder-intro"]
    intro["data-en"] = (
        "Automatically indexed from PubMed when an Obesity record contains both "
        "a GLP-1/incretin therapy concept and a ketogenic, ketosis or ketone concept."
    )
    intro["data-it"] = (
        "Indicizzati automaticamente da PubMed quando un record dell'area Obesità "
        "contiene sia un concetto relativo a terapie GLP-1/incretiniche sia un concetto "
        "relativo a chetogenica, chetosi o chetoni."
    )
    intro.string = intro["data-en"]
    sub_body.append(intro)

    listing = soup.new_tag("div")
    listing["class"] = ["topic-subfolder-list"]

    for pmid in matches:
        listing.append(make_display_card(soup, pmid_to_card[pmid]))

    if not matches:
        empty = soup.new_tag("p")
        empty["class"] = ["topic-subfolder-empty"]
        empty["data-en"] = "No matching studies are currently indexed."
        empty["data-it"] = "Al momento non risultano studi corrispondenti indicizzati."
        empty.string = empty["data-en"]
        listing.append(empty)

    sub_body.append(listing)
    sub.append(sub_body)

    curated.insert_before(sub)
    LIBRARY.write_text(str(soup), encoding="utf-8")

    print(f"Static Obesity GLP-1RA + ketogenic subsection rebuilt with {len(matches)} study/studies.")
    if matches:
        print("Matched PMIDs: " + ", ".join(matches))

def patch_styles():
    css = STYLES.read_text(encoding="utf-8")
    if STYLE_MARKER in css:
        return

    extra_css = '''
/* Static Obesity GLP-1RA + ketogenic subcategory */
.library-topic-subfolder{
  margin:14px 0 18px;
  border:1px solid #bfd3e3;
  border-radius:10px;
  background:#f4f9fd;
  overflow:hidden;
}
.library-topic-subfolder > summary{
  list-style:none;
  display:grid;
  grid-template-columns:1fr auto 24px;
  gap:12px;
  align-items:center;
  padding:13px 14px;
  cursor:pointer;
}
.library-topic-subfolder > summary::-webkit-details-marker{display:none}
.topic-subfolder-title strong{display:block;color:var(--primary);font-size:14px}
.topic-subfolder-title small{display:block;color:var(--muted);font-size:11px;margin-top:2px}
.topic-subfolder-count{
  min-width:28px;padding:2px 8px;border-radius:999px;background:#dcecf7;
  color:var(--primary);font-size:11px;font-weight:700;text-align:center
}
.topic-subfolder-arrow{color:var(--primary-2);font-size:18px;transition:transform .18s ease}
.library-topic-subfolder[open] .topic-subfolder-arrow{transform:rotate(45deg)}
.topic-subfolder-body{padding:0 14px 14px}
.topic-subfolder-intro{font-size:12px;color:var(--muted)}
.topic-subfolder-list{display:grid;gap:9px}
.topic-subfolder-paper{border:1px solid var(--line);border-radius:9px;padding:12px;background:#fff}
.topic-subfolder-paper h4{margin:6px 0 7px;font-size:13px;line-height:1.35;color:var(--ink)}
.topic-subfolder-paper p{margin:0 0 10px;font-size:11px;color:var(--muted)}
.topic-subfolder-empty{font-size:12px;color:var(--muted)}
'''
    STYLES.write_text(css + extra_css, encoding="utf-8")

def main():
    rebuild_subcategory()
    patch_styles()

    check = LIBRARY.read_text(encoding="utf-8")
    if check.count(f'id="{SUBCATEGORY_ID}"') != 1:
        raise RuntimeError("Final subsection verification failed")

    print("GLP-1RA + ketogenic subsection maintenance completed successfully.")

if __name__ == "__main__":
    main()
