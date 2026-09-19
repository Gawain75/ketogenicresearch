#!/usr/bin/env python3
from __future__ import annotations
import json, re
from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "library.html"
AUDIT = ROOT / "library-legacy-audit.json"
REPORT = ROOT / "library-legacy-apply-report.json"

def norm_title(value: str) -> str:
    value = re.sub(r"^\s*\d+\.\s*", "", value or "").lower().replace("β", "beta")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()

def card_title(card) -> str:
    h4 = card.find("h4")
    if not h4:
        return ""
    return re.sub(r"^\s*\d+\.\s*", "", h4.get("data-en") or h4.get_text(" ", strip=True)).strip()

def rebuild_links(soup, card, candidate):
    links = card.select_one(".paper-links")
    if not links:
        links = soup.new_tag("div", attrs={"class": "paper-links"})
        card.append(links)

    for a in list(links.find_all("a", href=True)):
        href = a["href"]
        if "pubmed.ncbi.nlm.nih.gov" in href or "pmc.ncbi.nlm.nih.gov" in href or re.search(r"https?://(?:dx\.)?doi\.org/", href, re.I):
            a.decompose()

    pmid = str(candidate.get("pmid") or "").strip()
    doi = str(candidate.get("doi") or "").strip()

    if pmid:
        a = soup.new_tag("a", href=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/", target="_blank", rel="noopener")
        a["data-en"] = a["data-it"] = "PubMed ↗"
        a.string = "PubMed ↗"
        links.append(a)

    if doi:
        a = soup.new_tag("a", href=f"https://doi.org/{doi}", target="_blank", rel="noopener")
        a["data-en"] = a["data-it"] = "DOI ↗"
        a.string = "DOI ↗"
        links.append(a)

def main():
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    certain = audit.get("certain", [])
    soup = BeautifulSoup(LIBRARY.read_text(encoding="utf-8"), "html.parser")

    cards_by_title = {}
    for card in soup.select("article.folder-paper"):
        if str(card.get("data-pmid") or "").strip():
            continue
        key = norm_title(card_title(card))
        if key:
            cards_by_title.setdefault(key, []).append(card)

    applied = missing_card = missing_candidate = ambiguous_local = 0

    for entry in certain:
        candidate = entry.get("candidate") or {}
        pmid = str(candidate.get("pmid") or "").strip()
        if not pmid:
            missing_candidate += 1
            continue

        key = norm_title(entry.get("library_title") or "")
        matches = [c for c in cards_by_title.get(key, []) if not str(c.get("data-pmid") or "").strip()]

        if not matches:
            missing_card += 1
            continue
        if len(matches) > 1:
            ambiguous_local += 1
            continue

        card = matches[0]
        card["data-pmid"] = pmid

        doi = str(candidate.get("doi") or "").strip()
        if doi:
            card["data-doi"] = doi
        elif card.has_attr("data-doi"):
            del card["data-doi"]

        year = str(candidate.get("year") or "").strip()
        if year:
            card["data-year"] = year

        rebuild_links(soup, card, candidate)
        applied += 1

    LIBRARY.write_text(str(soup), encoding="utf-8")

    report = {
        "certain_matches_in_audit": len(certain),
        "certain_matches_applied": applied,
        "skipped_missing_local_card": missing_card,
        "skipped_missing_candidate_pmid": missing_candidate,
        "skipped_ambiguous_local_duplicate": ambiguous_local,
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
