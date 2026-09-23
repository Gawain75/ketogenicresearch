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

OLD_ID = "obesity-glp1-keto"
NEW_ID = "glp1-keto-metabolic-endocrine"
STYLE_MARKER = "/* GLP-1RA + ketogenic metabolic folder */"

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

SUPPLEMENTAL_ARTICLES = [
    {
        "title_en": "Preserving Lean Mass During GLP-1RA-Induced Weight Loss: The Potential Role of Ketogenic Metabolic Therapy in Improving Weight-Loss Quality",
        "title_it": "Preservare la massa magra durante la perdita di peso indotta da GLP-1RA: il potenziale ruolo della terapia metabolica chetogenica nel migliorare la qualità del dimagrimento",
        "authors": "Marco Medeot",
        "journal": "Biomedicine Advances",
        "citation": "Biomed adv. 2026;3(3):89-91.",
        "article_type_en": "Opinion",
        "article_type_it": "Opinion",
        "year": "2026",
        "doi": "10.34172/bma.74",
        "article_url": "https://biomedad.ae/Article/bma-74",
        "search": "glp-1ra glp-1 ketogenic metabolic therapy ketogenic diet ketosis ketones lean mass obesity weight loss semaglutide tirzepatide body composition",
    },
]

def text(node) -> str:
    if node is None:
        return ""
    return " ".join("".join(node.itertext()).split())

def api(endpoint: str, params: dict[str, str]) -> bytes:
    params = dict(params)
    params["tool"] = "KetogenicResearchGlp1KetoFolder"
    params["email"] = NCBI_EMAIL
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY

    url = EUTILS + "/" + endpoint + "?" + urllib.parse.urlencode(params)
    waits = [2, 5, 10, 20, 40, 60]

    for attempt in range(len(waits) + 1):
        req = urllib.request.Request(
            url,
            headers={"User-Agent": f"KetogenicResearchGlp1KetoFolder/1.0 ({NCBI_EMAIL})"},
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
    result: dict[str, str] = {}
    unique = list(dict.fromkeys(p for p in pmids if p))

    for i in range(0, len(unique), 150):
        batch = unique[i:i + 150]
        root = ET.fromstring(
            api("efetch.fcgi", {"db": "pubmed", "id": ",".join(batch), "retmode": "xml"})
        )
        for item in root.findall(".//PubmedArticle"):
            citation = item.find("MedlineCitation")
            article = citation.find("Article") if citation is not None else None
            if citation is None or article is None:
                continue
            pmid = text(citation.find("PMID"))
            title = text(article.find("ArticleTitle"))
            abstract = " ".join(text(n) for n in article.findall("Abstract/AbstractText"))
            mesh = " ".join(
                text(n) for n in citation.findall("MeshHeadingList/MeshHeading/DescriptorName")
            )
            keywords = " ".join(text(n) for n in citation.findall("KeywordList/Keyword"))
            result[pmid] = " ".join((title, abstract, mesh, keywords)).lower()

        if i + 150 < len(unique):
            time.sleep(0.4 if not NCBI_API_KEY else 0.15)

    return result

def is_match(raw: str) -> bool:
    raw = (raw or "").lower()
    return any(t in raw for t in GLP_TERMS) and any(t in raw for t in KETO_TERMS)

def card_pmid(card) -> str:
    pmid = str(card.get("data-pmid") or "").strip()
    if pmid:
        return pmid
    for a in card.find_all("a", href=True):
        m = re.search(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)/", a["href"], re.I)
        if m:
            return m.group(1)
    return ""

def clone_node(node):
    if node is None:
        return None
    return BeautifulSoup(str(node), "html.parser").find()

def make_supplemental_card(soup: BeautifulSoup, article: dict[str, str]):
    card = soup.new_tag("article")
    card["class"] = ["folder-paper", "drive-paper", "supplemental-paper"]
    card["data-doi"] = article["doi"]
    card["data-evidence"] = "opinion"
    card["data-search"] = article["search"]
    card["data-year"] = article["year"]

    badge = soup.new_tag("span")
    badge["class"] = ["evidence-level"]
    badge["data-en"] = article["article_type_en"]
    badge["data-it"] = article["article_type_it"]
    badge.string = article["article_type_en"]
    card.append(badge)

    h4 = soup.new_tag("h4")
    h4["data-en"] = article["title_en"]
    h4["data-it"] = article["title_it"]
    h4.string = article["title_en"]
    card.append(h4)

    p = soup.new_tag("p")
    meta_en = f'{article["authors"]}. {article["citation"]}'
    meta_it = meta_en
    p["data-en"] = meta_en
    p["data-it"] = meta_it
    p.string = meta_en
    card.append(p)

    links = soup.new_tag("div")
    links["class"] = ["paper-links"]

    article_link = soup.new_tag("a", href=article["article_url"])
    article_link["target"] = "_blank"
    article_link["rel"] = "noopener"
    article_link["data-en"] = "Article ↗"
    article_link["data-it"] = "Articolo ↗"
    article_link.string = "Article ↗"
    links.append(article_link)

    doi_link = soup.new_tag("a", href=f'https://doi.org/{article["doi"]}')
    doi_link["target"] = "_blank"
    doi_link["rel"] = "noopener"
    doi_link["data-en"] = "DOI ↗"
    doi_link["data-it"] = "DOI ↗"
    doi_link.string = "DOI ↗"
    links.append(doi_link)

    card.append(links)
    return card


def make_folder(soup: BeautifulSoup, matches: list[tuple[str, object]]):
    folder = soup.new_tag("details")
    folder["class"] = ["library-folder"]
    folder["id"] = NEW_ID
    folder["data-library-type"] = "thematic"
    folder["data-search"] = (
        "glp-1ra ketogenic ketosis ketones incretin semaglutide liraglutide "
        "tirzepatide retatrutide vlckd vlekt beta-hydroxybutyrate"
    )

    summary = soup.new_tag("summary")

    icon = soup.new_tag("span")
    icon["class"] = ["folder-icon", "glp1-keto-icon"]
    icon["data-icon-area"] = "GLP-1RA + Ketogenic Metabolism"
    icon["data-icon-family"] = "metabolic"

    svg = BeautifulSoup(
        '''
        <svg aria-hidden="true" viewBox="0 0 24 24">
          <circle cx="6" cy="6" r="2"></circle>
          <path d="M6 8v3c0 2.2 1.8 4 4 4h2"></path>
          <path d="M16 4s3.5 3.8 3.5 6.5a3.5 3.5 0 0 1-7 0C12.5 7.8 16 4 16 4Z"></path>
          <path d="M10 18h8"></path>
          <path d="M14 15v6"></path>
        </svg>
        ''',
        "html.parser",
    ).find("svg")
    icon.append(svg)

    labels = soup.new_tag("span")
    strong = soup.new_tag("strong")
    strong["data-en"] = "GLP-1RA + Ketogenic Metabolism"
    strong["data-it"] = "GLP-1RA + metabolismo chetogenico"
    strong.string = strong["data-en"]

    matched_dois = {
        str(card.get("data-doi") or "").strip().lower()
        for _, card in matches
        if str(card.get("data-doi") or "").strip()
    }
    supplemental = [
        article for article in SUPPLEMENTAL_ARTICLES
        if article["doi"].lower() not in matched_dois
    ]
    total_count = len(matches) + len(supplemental)

    small = soup.new_tag("small")
    small["data-en"] = f"{total_count} studies/publications combining GLP-1-based therapies with ketogenic interventions, ketosis or ketones"
    small["data-it"] = f"{total_count} studi/pubblicazioni che combinano terapie basate su GLP-1 con chetogenica, chetosi o chetoni"
    small.string = small["data-en"]

    labels.append(strong)
    labels.append(small)

    arrow = soup.new_tag("span")
    arrow["class"] = ["folder-arrow"]
    arrow.string = "＋"

    summary.append(icon)
    summary.append(labels)
    summary.append(arrow)
    folder.append(summary)

    body = soup.new_tag("div")
    body["class"] = ["folder-body"]

    intro = soup.new_tag("p")
    intro["data-en"] = (
        "Automatically curated from PubMed records in the Metabolic & Endocrine section. "
        "Inclusion requires both a GLP-1/incretin therapy concept and a ketogenic, ketosis "
        "or ketone-related concept."
    )
    intro["data-it"] = (
        "Selezione automatica dai record PubMed della sezione Metabolismo ed endocrinologia. "
        "L'inclusione richiede sia un concetto relativo a terapie GLP-1/incretiniche sia "
        "un concetto relativo a chetogenica, chetosi o chetoni."
    )
    intro.string = intro["data-en"]
    body.append(intro)

    curated = soup.new_tag("div")
    curated["class"] = ["folder-curated"]

    title = soup.new_tag("div")
    title["class"] = ["folder-curated-title"]
    title["data-en"] = "Matched peer-reviewed literature"
    title["data-it"] = "Letteratura peer-reviewed corrispondente"
    title.string = title["data-en"]
    curated.append(title)

    for _, source in matches:
        clone = clone_node(source)
        if clone is not None:
            curated.append(clone)

    for article in supplemental:
        curated.append(make_supplemental_card(soup, article))

    body.append(curated)
    folder.append(body)
    return folder

def rebuild():
    soup = BeautifulSoup(LIBRARY.read_text(encoding="utf-8"), "html.parser")

    # Remove previous implementations.
    for old_id in (OLD_ID, NEW_ID):
        old = soup.find(id=old_id)
        if old is not None:
            old.decompose()

    # Remove abandoned global thematic filter if present.
    topic_filter = soup.find(id="topicFilter")
    if topic_filter is not None:
        topic_filter.decompose()

    heading = soup.find("h2", attrs={"data-en": "Metabolic & Endocrine"})
    if heading is None:
        heading = soup.find("h2", string=re.compile(r"Metabolic\s*&\s*Endocrine", re.I))
    if heading is None:
        raise RuntimeError("Metabolic & Endocrine group not found")

    group = heading.find_parent(class_="library-group")
    if group is None:
        raise RuntimeError("Metabolic & Endocrine library-group not found")

    folder_list = group.select_one(".folder-list")
    if folder_list is None:
        raise RuntimeError("Metabolic & Endocrine folder-list not found")

    cards = []
    seen = set()
    for folder in folder_list.find_all("details", class_="library-folder", recursive=False):
        for card in folder.select(".folder-curated > article.folder-paper"):
            pmid = card_pmid(card)
            if pmid and pmid not in seen:
                seen.add(pmid)
                cards.append((pmid, card))

    if not cards:
        raise RuntimeError("No PMID-backed records found in Metabolic & Endocrine")

    print(f"Checking {len(cards)} unique PMID-backed records in Metabolic & Endocrine.")
    pubmed = fetch_pubmed_text([pmid for pmid, _ in cards])

    matches = [(pmid, card) for pmid, card in cards if is_match(pubmed.get(pmid, ""))]
    print(f"Matched {len(matches)} PubMed-indexed GLP-1RA + ketogenic/ketosis/ketone studies.")
    if matches:
        print("Matched PMIDs: " + ", ".join(pmid for pmid, _ in matches))
    print(
        f"Supplemental peer-reviewed publications configured: "
        f"{len(SUPPLEMENTAL_ARTICLES)}"
    )

    new_folder = make_folder(soup, matches)

    obesity = folder_list.find("details", id="obesity", recursive=False)
    if obesity is not None:
        obesity.insert_after(new_folder)
    else:
        folder_list.insert(0, new_folder)

    LIBRARY.write_text(str(soup), encoding="utf-8")

def patch_styles():
    css = STYLES.read_text(encoding="utf-8")
    if STYLE_MARKER in css:
        return

    css += '''
/* GLP-1RA + ketogenic metabolic folder */
.library-folder .folder-icon.glp1-keto-icon{
  background:linear-gradient(145deg,#eef7fb,#f7fbfe);
  border-color:#a9cadb;
  color:#1f6d86;
}
'''
    STYLES.write_text(css, encoding="utf-8")

def main():
    rebuild()
    patch_styles()

    check = LIBRARY.read_text(encoding="utf-8")
    if check.count(f'id="{NEW_ID}"') != 1:
        raise RuntimeError("Final GLP-1RA metabolic folder verification failed")
    if f'id="{OLD_ID}"' in check:
        raise RuntimeError("Old Obesity subsection still present")
    if '10.34172/bma.74' not in check:
        raise RuntimeError("Biomedicine Advances opinion DOI 10.34172/bma.74 missing")

    print("GLP-1RA + Ketogenic Metabolism folder installed under Metabolic & Endocrine.")

if __name__ == "__main__":
    main()
