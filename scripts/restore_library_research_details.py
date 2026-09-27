#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from bs4 import BeautifulSoup
from pubmed_record_guard import fetch_pubmed_records

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "library.html"


def has_details(card) -> bool:
    return card.select_one("details.paper-study-details") is not None


def main() -> None:
    soup = BeautifulSoup(LIBRARY.read_text(encoding="utf-8"), "html.parser")

    cards_by_pmid = {}
    for card in soup.select("article.folder-paper[data-pmid]"):
        pmid = str(card.get("data-pmid") or "").strip()
        if pmid and not has_details(card):
            cards_by_pmid.setdefault(pmid, []).append(card)

    if not cards_by_pmid:
        print("No Library cards require research-detail restoration.")
        return

    print(f"Fetching authoritative PubMed data for {len(cards_by_pmid)} unique PMID(s).")
    pubmed = fetch_pubmed_records(list(cards_by_pmid))

    changed_cards = 0
    missing_abstract = 0

    for pmid, cards in cards_by_pmid.items():
        record = pubmed.get(pmid) or {}
        abstract = (record.get("abstract") or "").strip()
        if not abstract:
            missing_abstract += len(cards)
            continue

        for card in cards:
            details = soup.new_tag("details", attrs={"class": "paper-study-details"})
            summary = soup.new_tag("summary")
            summary["data-en"] = "Research details"
            summary["data-it"] = "Dettagli della ricerca"
            summary.string = "Research details"
            details.append(summary)

            p = soup.new_tag("p")
            p["class"] = "paper-source-abstract"
            p["data-en"] = abstract
            p["data-it"] = abstract
            p.string = abstract
            details.append(p)

            links = card.select_one(".paper-links")
            if links:
                links.insert_before(details)
            else:
                card.append(details)
            changed_cards += 1

    if changed_cards:
        LIBRARY.write_text(str(soup), encoding="utf-8")

    print(f"Research details restored on {changed_cards} Library card(s).")
    print(f"Cards without a PubMed abstract left unchanged: {missing_abstract}.")


if __name__ == "__main__":
    main()
