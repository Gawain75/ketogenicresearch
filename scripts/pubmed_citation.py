from __future__ import annotations
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
