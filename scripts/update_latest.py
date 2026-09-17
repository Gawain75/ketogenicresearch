#!/usr/bin/env python3

import datetime as dt
import json
import os
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "latest-publications.json"

EMAIL = os.getenv("NCBI_EMAIL", "info@ketogenicresearch.org")
API_KEY = os.getenv("NCBI_API_KEY", "")
WINDOW_DAYS = int(os.getenv("WINDOW_DAYS", "90"))
MAX_RECORDS = int(os.getenv("MAX_RECORDS", "100"))

BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

QUERY = """
(
"ketogenic diet"[Title/Abstract]
OR "ketogenic diets"[Title/Abstract]
OR "ketogenic therapy"[Title/Abstract]
OR "nutritional ketosis"[Title/Abstract]
OR VLCKD[Title/Abstract]
OR VLEKT[Title/Abstract]
OR "beta-hydroxybutyrate"[Title/Abstract]
OR "ketone bodies"[Title/Abstract]
)
"""


def api(name, params):
    params.update({
        "tool": "ketogenicresearch-literature-monitor",
        "email": EMAIL
    })

    if API_KEY:
        params["api_key"] = API_KEY

    url = f"{BASE}/{name}?{urllib.parse.urlencode(params)}"

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent":
            f"ketogenicresearch-literature-monitor/1.0 ({EMAIL})"
        }
    )

    with urllib.request.urlopen(req, timeout=60) as response:
        data = response.read()

    time.sleep(0.12 if API_KEY else 0.36)

    return data


def text(node):
    if node is None:
        return ""

    return "".join(node.itertext()).strip()


def main():

    search = json.loads(
        api(
            "esearch.fcgi",
            {
                "db": "pubmed",
                "term": QUERY,
                "retmode": "json",
                "retmax": str(MAX_RECORDS),
                "sort": "pub date",
                "datetype": "pdat",
                "reldate": str(WINDOW_DAYS),
            }
        ).decode("utf-8")
    )

    ids = search.get(
        "esearchresult",
        {}
    ).get(
        "idlist",
        []
    )

    if not ids:
        raise SystemExit(
            "No PubMed records returned."
        )

    root = ET.fromstring(
        api(
            "efetch.fcgi",
            {
                "db": "pubmed",
                "id": ",".join(ids),
                "retmode": "xml",
            }
        )
    )

    publications = []

    today = dt.date.today().isoformat()

    for item in root.findall(
        ".//PubmedArticle"
    ):

        citation = item.find(
            "MedlineCitation"
        )

        article = (
            citation.find("Article")
            if citation is not None
            else None
        )

        if citation is None or article is None:
            continue

        pmid = text(
            citation.find("PMID")
        )

        title = text(
            article.find("ArticleTitle")
        )

        journal = text(
            article.find("Journal/Title")
        )

        authors = []

        for author in article.findall(
            "AuthorList/Author"
        ):

            last = text(
                author.find("LastName")
            )

            initials = text(
                author.find("Initials")
            )

            name = " ".join(
                x for x in
                [last, initials]
                if x
            )

            if name:
                authors.append(name)

        doi = ""

        for aid in item.findall(
            ".//ArticleId"
        ):

            if (
                aid.attrib.get("IdType") or ""
            ).lower() == "doi":

                doi = text(aid)
                break

        year_text = text(
            article.find(
                "Journal/JournalIssue/PubDate/Year"
            )
        )

        year = (
            int(year_text)
            if year_text.isdigit()
            else None
        )

        publications.append({
            "pmid": pmid,
            "title": title,
            "authors": authors,
            "journal": journal,
            "date": (
                f"{year}-01-01"
                if year
                else ""
            ),
            "year": year,
            "doi": doi,
            "pubmed_url": (
                f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
                if pmid
                else ""
            ),
            "doi_url": (
                f"https://doi.org/{doi}"
                if doi
                else ""
            ),
            "areas": [
                "Other / General"
            ],
            "source": "PubMed",
            "first_seen": today,
            "status": "new",
        })

    payload = {
        "generated_at": (
            dt.datetime.now(
                dt.timezone.utc
            )
            .replace(
                microsecond=0
            )
            .isoformat()
        ),
        "window_days": WINDOW_DAYS,
        "max_records": MAX_RECORDS,
        "source":
            "PubMed / NCBI E-utilities",
        "count":
            len(publications),
        "publications":
            publications,
    }

    OUT.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    print(
        f"Wrote {len(publications)} records "
        f"to {OUT.name}"
    )


if __name__ == "__main__":
    main()
