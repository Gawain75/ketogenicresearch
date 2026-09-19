#!/usr/bin/env python3
from __future__ import annotations

import difflib
import json
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
REPORT = ROOT / "library-legacy-audit.json"
STATE = ROOT / "library-legacy-audit-state.json"

NCBI_EMAIL = os.getenv("NCBI_EMAIL", "info@ketogenicresearch.org").strip()
NCBI_API_KEY = os.getenv("NCBI_API_KEY", "").strip()
AUDIT_BATCH = max(10, int(os.getenv("AUDIT_BATCH", "150")))

REQUEST_DELAY = 0.18 if NCBI_API_KEY else 0.45
_LAST_REQUEST = 0.0


def api(endpoint: str, params: dict[str, str]) -> bytes:
    global _LAST_REQUEST

    params = dict(params)
    params["tool"] = "KetogenicResearchLegacyAudit"
    params["email"] = NCBI_EMAIL
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY

    url = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
        + endpoint + "?" + urllib.parse.urlencode(params)
    )

    elapsed = time.monotonic() - _LAST_REQUEST
    if elapsed < REQUEST_DELAY:
        time.sleep(REQUEST_DELAY - elapsed)

    last_exc = None
    for attempt in range(6):
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": f"KetogenicResearchLegacyAudit/1.0 ({NCBI_EMAIL})"
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                data = response.read()
                _LAST_REQUEST = time.monotonic()
                return data
        except urllib.error.HTTPError as exc:
            last_exc = exc
            _LAST_REQUEST = time.monotonic()

            if exc.code == 429:
                retry_after = exc.headers.get("Retry-After")
                try:
                    wait = float(retry_after)
                except Exception:
                    wait = min(60.0, 2.0 * (2 ** attempt))
                wait = max(wait, 3.0)
                print(f"NCBI 429. Waiting {wait:.0f}s before retry.")
                time.sleep(wait)
                continue

            if 500 <= exc.code < 600:
                wait = min(30.0, 2.0 * (2 ** attempt))
                print(f"NCBI HTTP {exc.code}. Waiting {wait:.0f}s.")
                time.sleep(wait)
                continue

            raise

        except urllib.error.URLError as exc:
            last_exc = exc
            wait = min(30.0, 2.0 * (2 ** attempt))
            print(f"NCBI network error. Waiting {wait:.0f}s: {exc}")
            time.sleep(wait)

    raise RuntimeError(f"NCBI request failed after retries: {last_exc}")


def txt(node):
    return "".join(node.itertext()).strip() if node is not None else ""


def norm_title(value: str) -> str:
    value = re.sub(r"^\s*\d+\.\s*", "", value or "")
    value = value.lower().replace("β", "beta")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def norm_author(value: str) -> str:
    value = (value or "").lower()
    value = re.sub(r"[^a-z]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def card_title(card) -> str:
    h4 = card.find("h4")
    if not h4:
        return ""
    return re.sub(
        r"^\s*\d+\.\s*",
        "",
        h4.get("data-en") or h4.get_text(" ", strip=True),
    ).strip()


def card_year(card) -> str:
    year = str(card.get("data-year") or "").strip()
    if re.fullmatch(r"(19|20)\d{2}", year):
        return year
    p = card.find("p")
    if p:
        m = re.search(r"\b((?:19|20)\d{2})\b", p.get_text(" ", strip=True))
        if m:
            return m.group(1)
    return ""


def card_first_author(card) -> str:
    p = card.find("p")
    if not p:
        return ""
    raw = p.get_text(" ", strip=True)
    first = re.split(r"\s*[·|]\s*", raw, maxsplit=1)[0].strip()
    if not first:
        return ""
    return re.split(r",|;|\band\b", first, maxsplit=1, flags=re.I)[0].strip()


def search_candidates(title: str, year: str, author: str) -> list[str]:
    queries = [f'"{title}"[Title]']

    words = [w for w in norm_title(title).split() if len(w) >= 4][:10]
    if words:
        q = " AND ".join(f"{w}[Title]" for w in words[:7])
        if year:
            q += f" AND {year}[pdat]"
        if author:
            q += f' AND "{author}"[Author]'
        queries.append(q)

        q2 = " AND ".join(f"{w}[Title]" for w in words[:5])
        if year:
            q2 += f" AND {year}[pdat]"
        queries.append(q2)

    for query in queries:
        data = json.loads(
            api(
                "esearch.fcgi",
                {
                    "db": "pubmed",
                    "term": query,
                    "retmode": "json",
                    "retmax": "10",
                },
            ).decode("utf-8")
        )
        ids = data.get("esearchresult", {}).get("idlist", [])
        if ids:
            return ids
    return []


def fetch_records(pmids: list[str]) -> list[dict]:
    if not pmids:
        return []

    root = ET.fromstring(
        api(
            "efetch.fcgi",
            {
                "db": "pubmed",
                "id": ",".join(pmids),
                "retmode": "xml",
            },
        )
    )

    out = []
    for item in root.findall(".//PubmedArticle"):
        citation = item.find("MedlineCitation")
        article = citation.find("Article") if citation is not None else None
        if citation is None or article is None:
            continue

        pmid = txt(citation.find("PMID"))
        title = txt(article.find("ArticleTitle"))

        year = ""
        for path in (
            "Journal/JournalIssue/PubDate/Year",
            "ArticleDate/Year",
        ):
            year = txt(article.find(path))
            if year:
                break
        if not year:
            medline = txt(article.find("Journal/JournalIssue/PubDate/MedlineDate"))
            m = re.search(r"\b((?:19|20)\d{2})\b", medline)
            if m:
                year = m.group(1)

        first_author = ""
        author = article.find("AuthorList/Author")
        if author is not None:
            first_author = (
                txt(author.find("CollectiveName"))
                or txt(author.find("LastName"))
            )

        doi = ""
        for aid in item.findall(".//PubmedData/ArticleIdList/ArticleId"):
            if (aid.attrib.get("IdType") or "").lower() == "doi":
                doi = txt(aid).strip()
                break

        out.append(
            {
                "pmid": pmid,
                "title": title,
                "year": year,
                "first_author": first_author,
                "doi": doi,
            }
        )

    return out


def classify_match(
    local_title: str,
    local_year: str,
    local_author: str,
    candidates: list[dict],
):
    target = norm_title(local_title)
    local_author_n = norm_author(local_author)

    ranked = []
    for rec in candidates:
        title_score = difflib.SequenceMatcher(
            None, target, norm_title(rec["title"])
        ).ratio()

        year_match = bool(local_year and rec["year"] == local_year)

        rec_author_n = norm_author(rec.get("first_author") or "")
        author_match = False
        if local_author_n and rec_author_n:
            author_match = (
                local_author_n in rec_author_n
                or rec_author_n in local_author_n
                or difflib.SequenceMatcher(
                    None, local_author_n, rec_author_n
                ).ratio() >= 0.82
            )

        composite = title_score
        if year_match:
            composite += 0.03
        if author_match:
            composite += 0.04

        ranked.append(
            (composite, title_score, year_match, author_match, rec)
        )

    ranked.sort(key=lambda x: x[0], reverse=True)

    if not ranked:
        return "no_match", None, {}

    composite, title_score, year_match, author_match, rec = ranked[0]
    second = ranked[1][0] if len(ranked) > 1 else 0.0
    separation = composite - second

    # High-confidence: safe enough for later automatic application.
    certain = (
        title_score >= 0.985
        or (title_score >= 0.95 and year_match)
        or (title_score >= 0.94 and author_match)
        or (title_score >= 0.92 and year_match and author_match)
    ) and (separation >= 0.02 or len(ranked) == 1)

    # Possible: plausible, but not safe for automatic linking.
    possible = (
        title_score >= 0.86
        or (title_score >= 0.82 and (year_match or author_match))
    )

    detail = {
        "title_score": round(title_score, 3),
        "composite": round(composite, 3),
        "second_composite": round(second, 3),
        "year_match": year_match,
        "author_match": author_match,
    }

    if certain:
        return "certain", rec, detail
    if possible:
        return "possible", rec, detail
    return "no_match", rec, detail


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data):
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main():
    soup = BeautifulSoup(LIBRARY.read_text(encoding="utf-8"), "html.parser")

    cards = []
    for card in soup.select("article.folder-paper"):
        if str(card.get("data-pmid") or "").strip():
            continue
        title = card_title(card)
        if title:
            cards.append(
                {
                    "title": title,
                    "year": card_year(card),
                    "first_author": card_first_author(card),
                }
            )

    state = load_json(
        STATE,
        {
            "next_index": 0,
            "completed": False,
        },
    )

    next_index = int(state.get("next_index", 0))
    if next_index >= len(cards):
        state["completed"] = True
        save_json(STATE, state)
        print("Legacy audit already complete.")
        return

    batch = cards[next_index:next_index + AUDIT_BATCH]
    existing_report = load_json(
        REPORT,
        {
            "certain": [],
            "possible": [],
            "no_match": [],
            "summary": {},
        },
    )

    certain = existing_report.get("certain", [])
    possible = existing_report.get("possible", [])
    no_match = existing_report.get("no_match", [])

    for i, item in enumerate(batch, start=1):
        ids = search_candidates(
            item["title"],
            item["year"],
            item["first_author"],
        )
        records = fetch_records(ids)
        category, rec, detail = classify_match(
            item["title"],
            item["year"],
            item["first_author"],
            records,
        )

        entry = {
            "library_title": item["title"],
            "library_year": item["year"],
            "library_first_author": item["first_author"],
            "candidate": rec,
            "match_detail": detail,
        }

        if category == "certain":
            certain.append(entry)
        elif category == "possible":
            possible.append(entry)
        else:
            no_match.append(entry)

        print(
            f"[{next_index + i}/{len(cards)}] "
            f"{category.upper()}: {item['title'][:90]}"
        )

    new_next = next_index + len(batch)
    completed = new_next >= len(cards)

    report = {
        "certain": certain,
        "possible": possible,
        "no_match": no_match,
        "summary": {
            "cards_without_pmid_total": len(cards),
            "cards_audited": new_next,
            "certain_matches": len(certain),
            "possible_matches": len(possible),
            "no_match": len(no_match),
            "cards_remaining": max(0, len(cards) - new_next),
            "completed": completed,
        },
    }

    state = {
        "next_index": new_next,
        "completed": completed,
    }

    save_json(REPORT, report)
    save_json(STATE, state)

    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
