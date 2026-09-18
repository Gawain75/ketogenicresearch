#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "review-queue.json"
LIBRARY = ROOT / "library.html"
INDEX = ROOT / "index.html"
SCRIPT = ROOT / "script.js"


def norm(value: str) -> str:
    value = re.sub(r"^\s*\d+\.\s*", "", value or "")
    value = re.sub(r"\s+", " ", value).strip().lower()
    return re.sub(r"[^a-z0-9β]+", " ", value)


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def main() -> None:
    queue = load_json(QUEUE, {"records": []})

    soup = BeautifulSoup(
        LIBRARY.read_text(encoding="utf-8"),
        "html.parser"
    )

    sections = {}

    for details in soup.select("details.library-folder"):
        strong = details.select_one("summary strong")
        if strong:
            title = strong.get("data-en") or strong.get_text(
                " ",
                strip=True
            )
            sections[title] = details

    existing = {
        norm(h.get("data-en") or h.get_text(" ", strip=True))
        for h in soup.select("article.folder-paper h4")
    }

    promoted = 0

    for record in queue.get("records", []):

        pmid = str(record.get("pmid") or "")

        if not record.get("auto_eligible"):
            continue

        title = record.get("title") or ""

        if not title or norm(title) in existing:
            continue

        areas = record.get("areas") or []

        valid_areas = [
            area
            for area in areas
            if area in sections
        ]

        if not valid_areas:
            print(
                f"Skipping PMID {pmid}: "
                "no valid curated area."
            )
            continue

        for area in valid_areas:

            details = sections[area]

            wrap = details.select_one(
                ".folder-curated"
            )

            if not wrap:
                continue

            current = len(
                details.select(
                    "article.folder-paper"
                )
            )

            art = soup.new_tag(
                "article",
                attrs={
                    "class": "folder-paper"
                }
            )

            art["data-evidence"] = (
                record.get("evidence_type")
                or "Other"
            ).lower().replace(" ", "-")

            art["data-year"] = str(
                (record.get("date") or "")[:4]
                or "unknown"
            )

            art["data-search"] = (
                f"{title} "
                f"{area} "
                f"{record.get('journal', '')} "
                f"{' '.join(record.get('authors') or [])}"
            ).lower()

            level = soup.new_tag(
                "div",
                attrs={
                    "class": "evidence-level"
                }
            )

            level["data-en"] = (
                record.get("evidence_type")
                or "Other"
            )

            level["data-it"] = (
                record.get("evidence_type_it")
                or record.get("evidence_type")
                or "Altro"
            )

            level.string = level["data-en"]

            art.append(level)

            h4 = soup.new_tag("h4")

            h4["data-en"] = (
                f"{current + 1}. {title}"
            )

            h4["data-it"] = (
                f"{current + 1}. {title}"
            )

            h4.string = h4["data-en"]

            art.append(h4)

            meta = soup.new_tag("p")

            authors = ", ".join(
                record.get("authors") or []
            )

            journal = (
                record.get("journal") or ""
            )

            date = (
                record.get("date") or ""
            )

            meta.string = " · ".join(
                x
                for x in [
                    authors,
                    journal,
                    date
                ]
                if x
            )

            art.append(meta)

            links = soup.new_tag(
                "div",
                attrs={
                    "class": "paper-links"
                }
            )

            if record.get("pubmed_url"):

                a = soup.new_tag(
                    "a",
                    href=record["pubmed_url"],
                    target="_blank",
                    rel="noopener"
                )

                a["data-en"] = "PubMed ↗"
                a["data-it"] = "PubMed ↗"
                a.string = "PubMed ↗"

                links.append(a)

            if record.get("doi_url"):

                a = soup.new_tag(
                    "a",
                    href=record["doi_url"],
                    target="_blank",
                    rel="noopener"
                )

                a["data-en"] = "DOI ↗"
                a["data-it"] = "DOI ↗"
                a.string = "DOI ↗"

                links.append(a)

            art.append(links)
            wrap.append(art)

        existing.add(norm(title))
        promoted += 1

    if not promoted:
        print(
            "No new auto-eligible "
            "records to promote."
        )
        return

    total = len(
        soup.select(
            "article.folder-paper"
        )
    )

    areas_count = len(
        soup.select(
            "details.library-folder"
        )
    )

    for item in soup.select(
        ".library-status-item"
    ):

        st = item.find("strong")
        sp = item.find("span")

        if st and sp:

            label = (
                sp.get("data-en") or ""
            ).lower()

            if "publication" in label:

                st[
                    "data-publication-count"
                ] = ""

                st.string = str(total)

            elif "clinical areas" in label:

                st[
                    "data-clinical-area-count"
                ] = ""

                st.string = str(
                    areas_count
                )

    LIBRARY.write_text(
        str(soup),
        encoding="utf-8"
    )

    home = BeautifulSoup(
        INDEX.read_text(
            encoding="utf-8"
        ),
        "html.parser"
    )

    for item in home.select(
        ".home-metric"
    ):

        st = item.find("strong")
        sp = item.find("span")

        if st and sp:

            label = (
                sp.get("data-en") or ""
            ).lower()

            if "publication" in label:

                st[
                    "data-publication-count"
                ] = ""

                st.string = str(total)

            elif "clinical areas" in label:

                st[
                    "data-clinical-area-count"
                ] = ""

                st.string = str(
                    areas_count
                )

    for card in home.select(
        ".update-card"
    ):

        span = card.find("span")
        strong = card.find("strong")

        if (
            span
            and strong
            and (
                span.get("data-en")
                or ""
            )
            == "Curated publications"
        ):

            strong["data-en"] = str(total)
            strong["data-it"] = str(total)
            strong.string = str(total)

    INDEX.write_text(
        str(home),
        encoding="utf-8"
    )

    js = SCRIPT.read_text(
        encoding="utf-8"
    )

    js = re.sub(
        r"(const KR_LIBRARY_STATS = "
        r"\{\s*publications:\s*)\d+",
        rf"\g<1>{total}",
        js,
    )

    js = re.sub(
        r"(clinicalAreas:\s*)\d+",
        rf"\g<1>{areas_count}",
        js
    )

    SCRIPT.write_text(
        js,
        encoding="utf-8"
    )

    print(
        f"Promoted {promoted} "
        f"publication(s) automatically. "
        f"Curated total: {total}"
    )


if __name__ == "__main__":
    main()
