#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts" / "generate_articles.py"
DRAFTS = ROOT / "articles-drafts"
NCBI_EMAIL = os.environ.get("NCBI_EMAIL", "info@ketogenicresearch.org").strip()
NCBI_API_KEY = os.environ.get("NCBI_API_KEY", "").strip()
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def text_content(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return " ".join("".join(node.itertext()).split())


def fetch_pubmed(pmid: str) -> ET.Element:
    params = {
        "db": "pubmed",
        "id": pmid,
        "retmode": "xml",
        "tool": "ketogenicresearch",
        "email": NCBI_EMAIL,
    }
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY
    url = f"{EUTILS}/efetch.fcgi?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "KetogenicResearch/CitationRepair"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return ET.fromstring(resp.read())


def extract_citation_metadata(record: ET.Element) -> dict[str, object]:
    citation = record.find("MedlineCitation")
    article = citation.find("Article") if citation is not None else None
    if citation is None or article is None:
        return {}

    authors: list[str] = []
    for author in article.findall("AuthorList/Author"):
        collective = text_content(author.find("CollectiveName"))
        if collective:
            authors.append(collective)
            continue
        last = text_content(author.find("LastName"))
        initials = text_content(author.find("Initials"))
        if last:
            authors.append(" ".join(x for x in (last, initials) if x))

    journal_node = article.find("Journal")
    journal = volume = issue = year = ""
    if journal_node is not None:
        journal = text_content(journal_node.find("ISOAbbreviation")) or text_content(journal_node.find("Title"))
        ji = journal_node.find("JournalIssue")
        if ji is not None:
            volume = text_content(ji.find("Volume"))
            issue = text_content(ji.find("Issue"))
            pd = ji.find("PubDate")
            if pd is not None:
                year = text_content(pd.find("Year"))
                if not year:
                    md = text_content(pd.find("MedlineDate"))
                    m = re.search(r"\b(18|19|20)\d{2}\b", md)
                    year = m.group(0) if m else ""

    if not year:
        ad = article.find("ArticleDate")
        if ad is not None:
            year = text_content(ad.find("Year"))

    pages = text_content(article.find("Pagination/MedlinePgn"))
    if not pages:
        for node in article.findall("ELocationID"):
            kind = (node.attrib.get("EIdType") or "").lower()
            value = text_content(node)
            if value and kind in {"pii", "elocationid"}:
                pages = value
                break

    ids: dict[str, str] = {}
    for node in record.findall("./PubmedData/ArticleIdList/ArticleId"):
        kind = (node.attrib.get("IdType") or "").lower()
        value = text_content(node)
        if kind and value:
            ids[kind] = value

    return {
        "authors": authors,
        "title": text_content(article.find("ArticleTitle")),
        "journal": journal,
        "year": year,
        "volume": volume,
        "issue": issue,
        "pages": pages,
        "doi": (ids.get("doi") or "").strip().lower(),
        "pmid": text_content(citation.find("PMID")),
    }


def format_citation(meta: dict[str, object]) -> str:
    authors = [str(x).strip() for x in (meta.get("authors") or []) if str(x).strip()]
    author_text = ", ".join(authors[:6]) + (", et al." if len(authors) > 6 else "")
    title = str(meta.get("title") or "").strip().rstrip(".")
    journal = str(meta.get("journal") or "").strip()
    year = str(meta.get("year") or "").strip()
    volume = str(meta.get("volume") or "").strip()
    issue = str(meta.get("issue") or "").strip()
    pages = str(meta.get("pages") or "").strip()
    doi = str(meta.get("doi") or "").strip()
    pmid = str(meta.get("pmid") or "").strip()

    bibliographic = journal
    if year:
        bibliographic += (". " if bibliographic else "") + year
    if volume:
        bibliographic += f";{volume}"
    if issue:
        bibliographic += f"({issue})"
    if pages:
        bibliographic += f":{pages}"

    parts: list[str] = []
    if author_text:
        parts.append(author_text.rstrip(".") + ".")
    if title:
        parts.append(title + ".")
    if bibliographic:
        parts.append(bibliographic.rstrip(".") + ".")
    if doi:
        parts.append(f"doi: {doi}.")
    if pmid:
        parts.append(f"PMID: {pmid}.")
    return " ".join(parts).strip()


PUBMED_MODULE = r'''from __future__ import annotations
import re
import xml.etree.ElementTree as ET
from typing import Any

def _text(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return " ".join("".join(node.itertext()).split())

def extract_citation_metadata(record: ET.Element) -> dict[str, Any]:
    citation = record.find("MedlineCitation")
    article = citation.find("Article") if citation is not None else None
    if citation is None or article is None:
        return {}
    authors = []
    for author in article.findall("AuthorList/Author"):
        collective = _text(author.find("CollectiveName"))
        if collective:
            authors.append(collective)
            continue
        last = _text(author.find("LastName"))
        initials = _text(author.find("Initials"))
        if last:
            authors.append(" ".join(x for x in (last, initials) if x))
    journal_node = article.find("Journal")
    journal = volume = issue = year = ""
    if journal_node is not None:
        journal = _text(journal_node.find("ISOAbbreviation")) or _text(journal_node.find("Title"))
        ji = journal_node.find("JournalIssue")
        if ji is not None:
            volume = _text(ji.find("Volume"))
            issue = _text(ji.find("Issue"))
            pd = ji.find("PubDate")
            if pd is not None:
                year = _text(pd.find("Year"))
                if not year:
                    md = _text(pd.find("MedlineDate"))
                    m = re.search(r"\b(18|19|20)\d{2}\b", md)
                    year = m.group(0) if m else ""
    if not year:
        ad = article.find("ArticleDate")
        if ad is not None:
            year = _text(ad.find("Year"))
    pages = _text(article.find("Pagination/MedlinePgn"))
    if not pages:
        for node in article.findall("ELocationID"):
            kind = (node.attrib.get("EIdType") or "").lower()
            value = _text(node)
            if value and kind in {"pii", "elocationid"}:
                pages = value
                break
    ids = {}
    for node in record.findall("./PubmedData/ArticleIdList/ArticleId"):
        kind = (node.attrib.get("IdType") or "").lower()
        value = _text(node)
        if kind and value:
            ids[kind] = value
    return {
        "authors": authors,
        "title": _text(article.find("ArticleTitle")),
        "journal": journal,
        "year": year,
        "volume": volume,
        "issue": issue,
        "pages": pages,
        "doi": (ids.get("doi") or "").strip().lower(),
        "pmid": _text(citation.find("PMID")),
    }

def format_citation(meta: dict[str, Any]) -> str:
    authors = [str(x).strip() for x in (meta.get("authors") or []) if str(x).strip()]
    author_text = ", ".join(authors[:6]) + (", et al." if len(authors) > 6 else "")
    title = str(meta.get("title") or "").strip().rstrip(".")
    journal = str(meta.get("journal") or "").strip()
    year = str(meta.get("year") or "").strip()
    volume = str(meta.get("volume") or "").strip()
    issue = str(meta.get("issue") or "").strip()
    pages = str(meta.get("pages") or "").strip()
    doi = str(meta.get("doi") or "").strip()
    pmid = str(meta.get("pmid") or "").strip()
    bibliographic = journal
    if year:
        bibliographic += (". " if bibliographic else "") + year
    if volume:
        bibliographic += f";{volume}"
    if issue:
        bibliographic += f"({issue})"
    if pages:
        bibliographic += f":{pages}"
    parts = []
    if author_text:
        parts.append(author_text.rstrip(".") + ".")
    if title:
        parts.append(title + ".")
    if bibliographic:
        parts.append(bibliographic.rstrip(".") + ".")
    if doi:
        parts.append(f"doi: {doi}.")
    if pmid:
        parts.append(f"PMID: {pmid}.")
    return " ".join(parts).strip()
'''


def patch_generator() -> None:
    s = GENERATOR.read_text(encoding="utf-8")

    # 1) Import the deterministic PubMed citation helper.
    import_line = "from pubmed_citation import extract_citation_metadata, format_citation\n"
    if import_line not in s:
        s, n = re.subn(
            r"(from typing import Any\s*\n)",
            r"\1" + import_line,
            s,
            count=1,
        )
        if n != 1:
            raise RuntimeError("Could not install pubmed_citation import")

    # 2) Attach structured citation metadata to the authoritative PubMed record.
    if '"citation_meta": extract_citation_metadata(record),' not in s:
        s, n = re.subn(
            r'(?m)^(\s*)"mesh":\s*mesh\[:30\],\s*$',
            lambda m: (
                f'{m.group(1)}"mesh": mesh[:30],\n'
                f'{m.group(1)}"citation_meta": extract_citation_metadata(record),'
            ),
            s,
            count=1,
        )
        if n != 1:
            raise RuntimeError("Could not add citation_meta to extract_pubmed_source")

    # 3) Build Source/Fonte from PubMed, never from model-generated text.
    if "source_citation = format_citation(extra.get(\"citation_meta\") or {})" not in s:
        pattern = re.compile(
            r'(?m)^(\s*)pmcid = extra\.get\("pmcid", ""\)\s*$'
        )
        m = pattern.search(s)
        if not m:
            raise RuntimeError("Could not locate PMCID assignment in markdown()")
        indent = m.group(1)
        insertion = (
            m.group(0)
            + "\n"
            + indent
            + 'source_citation = format_citation(extra.get("citation_meta") or {})'
            + "\n"
            + indent
            + 'if not source_citation:'
            + "\n"
            + indent
            + '    raise RuntimeError(f"Unable to build authoritative PubMed citation for PMID {pmid}")'
        )
        s = s[:m.start()] + insertion + s[m.end():]

    en_old = '{draft.get("source_note_en","")}'
    it_old = '{draft.get("source_note_it","")}'
    if en_old in s:
        s = s.replace(en_old, "{source_citation}", 1)
    elif "{source_citation}" not in s:
        raise RuntimeError("Could not replace English Source citation")

    if it_old in s:
        s = s.replace(it_old, "{source_citation}", 1)
    elif s.count("{source_citation}") < 2:
        raise RuntimeError("Could not replace Italian Fonte citation")

    s = s.replace('generator_version: "4.2"', 'generator_version: "4.3"')

    # The model may still return source_note_* for backward-compatible JSON,
    # but those fields are now deliberately ignored by markdown().
    GENERATOR.write_text(s, encoding="utf-8")

def set_frontmatter_value(text: str, key: str, value: str) -> str:
    line = f'{key}: {json.dumps(value, ensure_ascii=False)}'
    pattern = re.compile(rf"(?m)^{re.escape(key)}:\s*.*$")
    if pattern.search(text):
        return pattern.sub(line, text, count=1)
    if text.startswith("---\n"):
        return text.replace("---\n", f"---\n{line}\n", 1)
    return text


def replace_source_blocks(text: str, citation: str) -> str:
    en = re.compile(r"(### Source\s*\n\n).*?(\n\n---\s*\n# )", re.S)
    if not en.search(text):
        raise RuntimeError("English Source block not found")
    text = en.sub(lambda m: m.group(1) + citation + m.group(2), text, count=1)
    it = re.compile(r"(### Fonte\s*\n\n).*?\s*$", re.S)
    if not it.search(text):
        raise RuntimeError("Italian Fonte block not found")
    return it.sub(lambda m: m.group(1) + citation + "\n", text, count=1)


def backfill_existing_drafts() -> None:
    checked_at = datetime.now(timezone.utc).isoformat()
    drafts = sorted(DRAFTS.glob("*.md"))
    if not drafts:
        raise RuntimeError("No article drafts found")
    repaired = 0
    for path in drafts:
        text = path.read_text(encoding="utf-8")
        m = re.search(r'(?m)^pmid:\s*["\']?(\d+)["\']?\s*$', text)
        if not m:
            raise RuntimeError(f"{path.name}: PMID missing from frontmatter")
        pmid = m.group(1)
        root = fetch_pubmed(pmid)
        record = root.find(".//PubmedArticle")
        if record is None:
            raise RuntimeError(f"PMID {pmid}: PubMed record unavailable")
        meta = extract_citation_metadata(record)
        if str(meta.get("pmid") or "") != pmid:
            raise RuntimeError(f"PMID {pmid}: identity mismatch while building citation")
        citation = format_citation(meta)
        if not citation or f"PMID: {pmid}." not in citation:
            raise RuntimeError(f"PMID {pmid}: incomplete deterministic citation")
        text = replace_source_blocks(text, citation)
        text = set_frontmatter_value(text, "source_citation_basis", "PubMed structured metadata")
        text = set_frontmatter_value(text, "source_citation_checked_at", checked_at)
        path.write_text(text, encoding="utf-8")
        repaired += 1
        print(f"PMID {pmid}: {citation}")
    print(f"Backfilled {repaired} deterministic PubMed citation(s).")


def verify_known_record() -> None:
    matches = list(DRAFTS.glob("*-42709766-*.md"))
    if not matches:
        return
    text = matches[0].read_text(encoding="utf-8")
    required = "PLoS One. 2026;21(9):e0357797."
    wrong = "PLoS One. 2026;15:e357797"
    if required not in text:
        raise RuntimeError(f"PMID 42709766 citation does not contain expected bibliographic core: {required}")
    if wrong in text:
        raise RuntimeError("PMID 42709766 still contains the known incorrect citation")


def main() -> None:
    module_path = ROOT / "scripts" / "pubmed_citation.py"
    module_path.write_text(PUBMED_MODULE, encoding="utf-8")
    compile(PUBMED_MODULE, str(module_path), "exec")
    patch_generator()
    compile(GENERATOR.read_text(encoding="utf-8"), str(GENERATOR), "exec")
    backfill_existing_drafts()
    verify_known_record()
    print("Deterministic PubMed source citations installed successfully.")


if __name__ == "__main__":
    main()
