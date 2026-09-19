#!/usr/bin/env python3
from __future__ import annotations

import difflib
import json
import os
import re
import time
import urllib.parse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "library.html"
REPORT = ROOT / "library-legacy-reconcile-report.json"

NCBI_EMAIL = os.getenv("NCBI_EMAIL", "info@ketogenicresearch.org").strip()
NCBI_API_KEY = os.getenv("NCBI_API_KEY", "").strip()
MAX_CARDS = max(1, int(os.getenv("RECONCILE_MAX", "50")))
REQUEST_DELAY = 0.18 if NCBI_API_KEY else 0.45
_LAST_REQUEST = 0.0


def api(endpoint: str, params: dict[str, str]) -> bytes:
    global _LAST_REQUEST

    params = dict(params)
    params["tool"] = "KetogenicResearchLegacyReconcile"
    params["email"] = NCBI_EMAIL
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY

    url = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
        + endpoint + "?" + urllib.parse.urlencode(params)
    )

    # Respect NCBI request-rate guidance conservatively.
    elapsed = time.monotonic() - _LAST_REQUEST
    if elapsed < REQUEST_DELAY:
        time.sleep(REQUEST_DELAY - elapsed)

    last_exc = None
    for attempt in range(6):
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": f"KetogenicResearchLegacyReconcile/1.1 ({NCBI_EMAIL})"
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
                print(
                    f"NCBI rate limit (429). Waiting {wait:.0f}s "
                    f"before retry {attempt + 1}/6."
                )
                time.sleep(wait)
                continue

            if 500 <= exc.code < 600:
                wait = min(30.0, 2.0 * (2 ** attempt))
                print(
                    f"NCBI temporary HTTP {exc.code}. Waiting {wait:.0f}s "
                    f"before retry {attempt + 1}/6."
                )
                time.sleep(wait)
                continue

            raise

        except urllib.error.URLError as exc:
            last_exc = exc
            wait = min(30.0, 2.0 * (2 ** attempt))
            print(
                f"NCBI network error. Waiting {wait:.0f}s "
                f"before retry {attempt + 1}/6: {exc}"
            )
            time.sleep(wait)

    raise RuntimeError(f"NCBI request failed after retries: {last_exc}")

def txt(node):
    return "".join(node.itertext()).strip() if node is not None else ""


def norm_title(value: str) -> str:
    value = re.sub(r"^\s*\d+\.\s*", "", value or "")
    value = value.lower().replace("β", "beta")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def norm_doi(value: str) -> str:
    value = (value or "").strip()
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value, flags=re.I)
    return value.rstrip(".,;").lower()


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
    # Metadata often begins with author list before journal/date.
    first = re.split(r"\s*[·|]\s*", raw, maxsplit=1)[0].strip()
    if not first:
        return ""
    # Keep first listed surname-like token.
    first_author = re.split(r",|;|\band\b", first, maxsplit=1, flags=re.I)[0].strip()
    return first_author


def norm_author(value: str) -> str:
    value = (value or "").lower()
    value = re.sub(r"[^a-z]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()

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
        for path in [
            "Journal/JournalIssue/PubDate/Year",
            "ArticleDate/Year",
        ]:
            year = txt(article.find(path))
            if year:
                break
        if not year:
            medline = txt(article.find("Journal/JournalIssue/PubDate/MedlineDate"))
            m = re.search(r"\b((?:19|20)\d{2})\b", medline)
            if m:
                year = m.group(1)

        first_author = ""
        first_author_node = article.find("AuthorList/Author")
        if first_author_node is not None:
            collective = txt(first_author_node.find("CollectiveName"))
            if collective:
                first_author = collective
            else:
                first_author = txt(first_author_node.find("LastName"))

        doi = ""
        pmc = ""
        for aid in item.findall(".//PubmedData/ArticleIdList/ArticleId"):
            kind = (aid.attrib.get("IdType") or "").lower()
            if kind == "doi":
                doi = norm_doi(txt(aid))
            elif kind == "pmc":
                pmc = txt(aid)

        out.append(
            {
                "pmid": pmid,
                "title": title,
                "year": year,
                "first_author": first_author,
                "doi": doi,
                "pmc": pmc,
            }
        )
    return out


def best_match(
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
            (
                composite,
                title_score,
                year_match,
                author_match,
                rec,
            )
        )

    ranked.sort(key=lambda x: x[0], reverse=True)
    if not ranked:
        return None, "no-candidate"

    composite, title_score, year_match, author_match, rec = ranked[0]
    second = ranked[1][0] if len(ranked) > 1 else 0.0

    # Conservative acceptance rules.
    accept = (
        title_score >= 0.985
        or (title_score >= 0.95 and year_match)
        or (title_score >= 0.92 and year_match and author_match)
        or (title_score >= 0.94 and author_match)
    ) and (composite - second >= 0.02 or len(ranked) == 1)

    if not accept:
        return None, {
            "best_composite": round(composite, 3),
            "best_title_score": round(title_score, 3),
            "second_composite": round(second, 3),
            "best_pubmed_title": rec["title"],
            "best_pmid": rec["pmid"],
            "year_match": year_match,
            "author_match": author_match,
            "library_author": local_author,
            "pubmed_first_author": rec.get("first_author", ""),
        }

    return rec, {
        "composite": round(composite, 3),
        "title_score": round(title_score, 3),
        "year_match": year_match,
        "author_match": author_match,
    }

def set_links(soup, card, rec):
    links = card.select_one(".paper-links")
    if not links:
        links = soup.new_tag("div", attrs={"class": "paper-links"})
        card.append(links)

    # Remove old PubMed-title-search and DOI links; rebuild from verified record.
    for a in list(links.find_all("a", href=True)):
        href = a["href"]
        if (
            "pubmed.ncbi.nlm.nih.gov" in href
            or re.search(r"https?://(?:dx\.)?doi\.org/", href, re.I)
            or "pmc.ncbi.nlm.nih.gov" in href
        ):
            a.decompose()

    a = soup.new_tag(
        "a",
        href=f"https://pubmed.ncbi.nlm.nih.gov/{rec['pmid']}/",
        target="_blank",
        rel="noopener",
    )
    a["data-en"] = "PubMed ↗"
    a["data-it"] = "PubMed ↗"
    a.string = "PubMed ↗"
    links.append(a)

    if rec["doi"]:
        a = soup.new_tag(
            "a",
            href=f"https://doi.org/{rec['doi']}",
            target="_blank",
            rel="noopener",
        )
        a["data-en"] = "DOI ↗"
        a["data-it"] = "DOI ↗"
        a.string = "DOI ↗"
        links.append(a)

    if rec["pmc"]:
        a = soup.new_tag(
            "a",
            href=f"https://pmc.ncbi.nlm.nih.gov/articles/{rec['pmc']}/",
            target="_blank",
            rel="noopener",
        )
        a["data-en"] = "Full text ↗"
        a["data-it"] = "Testo completo ↗"
        a.string = "Full text ↗"
        links.append(a)


def main():
    soup = BeautifulSoup(LIBRARY.read_text(encoding="utf-8"), "html.parser")
    candidates = []
    for card in soup.select("article.folder-paper"):
        if str(card.get("data-pmid") or "").strip():
            continue
        title = card_title(card)
        if title:
            candidates.append((card, title, card_year(card), card_first_author(card)))

    checked = 0
    matched = 0
    no_match = 0
    ambiguous = []

    for card, title, year, author in candidates[:MAX_CARDS]:
        checked += 1
        ids = search_candidates(title, year, author)
        records = fetch_records(ids)
        rec, detail = best_match(title, year, author, records)

        if rec is None:
            no_match += 1
            ambiguous.append(
                {
                    "library_title": title,
                    "library_year": year,
                    "library_first_author": author,
                    "detail": detail,
                }
            )
            continue

        card["data-pmid"] = rec["pmid"]
        if rec["doi"]:
            card["data-doi"] = rec["doi"]
        elif card.has_attr("data-doi"):
            del card["data-doi"]
        if rec["year"]:
            card["data-year"] = rec["year"]

        set_links(soup, card, rec)
        matched += 1
        print(f"Matched PMID {rec['pmid']}: {title}")

    LIBRARY.write_text(str(soup), encoding="utf-8")

    remaining = sum(
        1
        for card in soup.select("article.folder-paper")
        if not str(card.get("data-pmid") or "").strip()
    )

    report = {
        "cards_checked_this_run": checked,
        "cards_matched_this_run": matched,
        "cards_not_matched_this_run": no_match,
        "cards_without_pmid_remaining": remaining,
        "ambiguous_or_unmatched": ambiguous,
    }
    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        k: v for k, v in report.items() if k != "ambiguous_or_unmatched"
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
