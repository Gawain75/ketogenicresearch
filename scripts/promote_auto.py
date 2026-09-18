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
STYLES = ROOT / "styles.css"

EVIDENCE_DATA = {
    "Systematic review / meta-analysis": "systematic-review",
    "Guideline / consensus": "guideline",
    "Randomized clinical trial": "clinical-trial",
    "Clinical trial / intervention": "clinical-trial",
    "Observational human study": "human",
    "Case report / case series": "human",
    "Review": "review",
    "Preclinical / mechanistic": "mechanistic",
    "Other": "other",
}


def norm_title(value):
    value = re.sub(
        r"^\s*\d+\.\s*",
        "",
        value or "",
    ).lower()

    value = (
        value.replace("’", "'")
        .replace("–", "-")
        .replace("—", "-")
    )

    return re.sub(
        r"[^a-z0-9]+",
        " ",
        value,
    ).strip()


def norm_doi(value):
    value = (
        value or ""
    ).strip().lower()

    value = re.sub(
        r"^https?://(?:dx\.)?doi\.org/",
        "",
        value,
    )

    return value.rstrip(" .")


def load_json(
    path,
    default,
):
    if not path.exists():
        return default

    try:
        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    except Exception:
        return default


def collect_existing(soup):
    titles = set()
    pmids = set()
    dois = set()

    for article in soup.select(
        "article.folder-paper"
    ):
        h4 = article.find("h4")

        if h4:
            titles.add(
                norm_title(
                    h4.get("data-en")
                    or h4.get_text(
                        " ",
                        strip=True,
                    )
                )
            )

        data_pmid = article.get(
            "data-pmid"
        )

        data_doi = article.get(
            "data-doi"
        )

        if data_pmid:
            pmids.add(
                str(data_pmid)
            )

        if data_doi:
            dois.add(
                norm_doi(
                    data_doi
                )
            )

        for link in article.find_all(
            "a",
            href=True,
        ):
            href = link["href"]

            pmid_match = re.search(
                r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)/",
                href,
                re.I,
            )

            if pmid_match:
                pmids.add(
                    pmid_match.group(1)
                )

            doi_match = re.search(
                r"https?://(?:dx\.)?doi\.org/(.+)$",
                href,
                re.I,
            )

            if doi_match:
                dois.add(
                    norm_doi(
                        doi_match.group(1)
                    )
                )

    return (
        titles,
        pmids,
        dois,
    )


def ensure_area_filter(
    soup,
):
    controls = soup.select_one(
        ".library-filter-row"
    )

    if (
        not controls
        or soup.select_one(
            "#areaFilter"
        )
    ):
        return

    area = soup.new_tag(
        "select",
        id="areaFilter",
    )

    area[
        "aria-label"
    ] = "Filter by clinical area"

    first = soup.new_tag(
        "option",
        value="all",
    )

    first[
        "data-en"
    ] = "All clinical areas"

    first[
        "data-it"
    ] = "Tutte le aree cliniche"

    first.string = (
        "All clinical areas"
    )

    area.append(
        first
    )

    for folder in soup.select(
        "details.library-folder"
    ):
        label = folder.select_one(
            "summary strong"
        )

        if not label:
            continue

        en = (
            label.get(
                "data-en"
            )
            or label.get_text(
                " ",
                strip=True,
            )
        )

        it = (
            label.get(
                "data-it"
            )
            or en
        )

        option = soup.new_tag(
            "option",
            value=(
                folder.get("id")
                or ""
            ),
        )

        option[
            "data-en"
        ] = en

        option[
            "data-it"
        ] = it

        option.string = en

        area.append(
            option
        )

    controls.insert(
        0,
        area,
    )


def ensure_filter_assets():
    if SCRIPT.exists():
        js = SCRIPT.read_text(
            encoding="utf-8"
        )

        if (
            "V65_AREA_FILTER"
            not in js
        ):
            js += """
// V65_AREA_FILTER
(function () {
  function applyAreaFilter() {
    const area = document.getElementById('areaFilter');
    if (!area) return;

    const chosen = area.value;

    document.querySelectorAll(
      'details.library-folder'
    ).forEach(folder => {
      const areaMatch =
        chosen === 'all' ||
        folder.id === chosen;

      if (!areaMatch) {
        folder.hidden = true;
      } else {
        folder.hidden = false;

        if (chosen !== 'all') {
          folder.open = true;
        }
      }
    });

    document.querySelectorAll(
      '.library-group'
    ).forEach(group => {
      const visible = [
        ...group.querySelectorAll(
          'details.library-folder'
        )
      ].some(
        folder =>
          !folder.hidden
      );

      group.hidden = !visible;
    });
  }

  document.addEventListener(
    'DOMContentLoaded',
    () => {
      const area =
        document.getElementById(
          'areaFilter'
        );

      if (area) {
        area.addEventListener(
          'change',
          () => {
            if (
              typeof applyLibraryFilters
              === 'function'
            ) {
              applyLibraryFilters();
            }

            applyAreaFilter();
          }
        );
      }

      const clear =
        document.getElementById(
          'clearLibraryFilters'
        );

      if (clear) {
        clear.addEventListener(
          'click',
          () => {
            const area =
              document.getElementById(
                'areaFilter'
              );

            if (area) {
              area.value = 'all';
            }

            window.setTimeout(
              applyAreaFilter,
              0
            );
          }
        );
      }

      applyAreaFilter();
    }
  );
})();
"""

            SCRIPT.write_text(
                js,
                encoding="utf-8",
            )

    if STYLES.exists():
        css = STYLES.read_text(
            encoding="utf-8"
        )

        if (
            "V65_AREA_FILTER"
            not in css
        ):
            css += """
/* V65_AREA_FILTER */
#areaFilter {
  min-width: 210px;
}

@media (max-width: 720px) {
  #areaFilter {
    width: 100%;
    min-width: 0;
  }
}
"""

            STYLES.write_text(
                css,
                encoding="utf-8",
            )


def update_home_and_script(
    total,
    area_count,
):
    if INDEX.exists():
        home = BeautifulSoup(
            INDEX.read_text(
                encoding="utf-8"
            ),
            "html.parser",
        )

        for item in home.select(
            ".home-metric"
        ):
            strong = item.find(
                "strong"
            )

            span = item.find(
                "span"
            )

            if (
                not strong
                or not span
            ):
                continue

            label = (
                span.get(
                    "data-en"
                )
                or ""
            ).lower()

            if (
                "publication"
                in label
            ):
                strong[
                    "data-publication-count"
                ] = ""

                strong.string = str(
                    total
                )

            elif (
                "clinical areas"
                in label
            ):
                strong[
                    "data-clinical-area-count"
                ] = ""

                strong.string = str(
                    area_count
                )

        for card in home.select(
            ".update-card"
        ):
            span = card.find(
                "span"
            )

            strong = card.find(
                "strong"
            )

            if (
                span
                and strong
                and (
                    span.get(
                        "data-en"
                    )
                    or ""
                )
                == "Curated publications"
            ):
                strong[
                    "data-en"
                ] = str(total)

                strong[
                    "data-it"
                ] = str(total)

                strong.string = str(
                    total
                )

        INDEX.write_text(
            str(home),
            encoding="utf-8",
        )

    if SCRIPT.exists():
        js = SCRIPT.read_text(
            encoding="utf-8"
        )

        js = re.sub(
            r"(const KR_LIBRARY_STATS = \{\s*publications:\s*)\d+",
            rf"\g<1>{total}",
            js,
        )

        js = re.sub(
            r"(clinicalAreas:\s*)\d+",
            rf"\g<1>{area_count}",
            js,
        )

        SCRIPT.write_text(
            js,
            encoding="utf-8",
        )


def main():
    queue = load_json(
        QUEUE,
        {
            "records": []
        },
    )

    soup = BeautifulSoup(
        LIBRARY.read_text(
            encoding="utf-8"
        ),
        "html.parser",
    )

    sections = {}

    for details in soup.select(
        "details.library-folder"
    ):
        strong = details.select_one(
            "summary strong"
        )

        if strong:
            title = (
                strong.get(
                    "data-en"
                )
                or strong.get_text(
                    " ",
                    strip=True,
                )
            )

            sections[
                title
            ] = details

    (
        titles,
        pmids,
        dois,
    ) = collect_existing(
        soup
    )

    promoted_records = 0
    inserted_cards = 0

    for record in queue.get(
        "records",
        [],
    ):
        if not record.get(
            "auto_eligible"
        ):
            continue

        pmid = str(
            record.get(
                "pmid"
            )
            or ""
        )

        doi = norm_doi(
            record.get(
                "doi"
            )
            or ""
        )

        title = (
            record.get(
                "title"
            )
            or ""
        )

        title_key = norm_title(
            title
        )

        duplicate = (
            (
                pmid
                and pmid
                in pmids
            )
            or (
                doi
                and doi
                in dois
            )
            or (
                title_key
                in titles
            )
        )

        if duplicate:
            continue

        valid_areas = [
            area
            for area
            in (
                record.get(
                    "areas"
                )
                or []
            )
            if area in sections
        ]

        if not valid_areas:
            print(
                f"Skipping PMID "
                f"{pmid}: "
                f"no valid clinical area."
            )
            continue

        inserted_for_record = 0

        for area in valid_areas:
            details = sections[
                area
            ]

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

            evidence_type = (
                record.get(
                    "evidence_type"
                )
                or "Other"
            )

            article = soup.new_tag(
                "article",
                attrs={
                    "class":
                        "folder-paper"
                },
            )

            article[
                "data-evidence"
            ] = EVIDENCE_DATA.get(
                evidence_type,
                "other",
            )

            article[
                "data-year"
            ] = str(
                (
                    record.get(
                        "date"
                    )
                    or ""
                )[:4]
                or "unknown"
            )

            article[
                "data-pmid"
            ] = pmid

            if doi:
                article[
                    "data-doi"
                ] = doi

            article[
                "data-search"
            ] = (
                f"{title} "
                f"{area} "
                f"{record.get('journal', '')} "
                f"{' '.join(record.get('authors') or [])} "
                f"{pmid} "
                f"{doi}"
            ).lower()

            level = soup.new_tag(
                "div",
                attrs={
                    "class":
                        "evidence-level"
                },
            )

            level[
                "data-en"
            ] = evidence_type

            level[
                "data-it"
            ] = (
                record.get(
                    "evidence_type_it"
                )
                or evidence_type
            )

            level.string = (
                evidence_type
            )

            article.append(
                level
            )

            h4 = soup.new_tag(
                "h4"
            )

            h4[
                "data-en"
            ] = (
                f"{current + 1}. "
                f"{title}"
            )

            h4[
                "data-it"
            ] = (
                f"{current + 1}. "
                f"{title}"
            )

            h4.string = (
                h4["data-en"]
            )

            article.append(
                h4
            )

            meta = soup.new_tag(
                "p"
            )

            authors = ", ".join(
                record.get(
                    "authors"
                )
                or []
            )

            meta.string = " · ".join(
                x
                for x in [
                    authors,
                    record.get(
                        "journal"
                    )
                    or "",
                    record.get(
                        "date"
                    )
                    or "",
                ]
                if x
            )

            article.append(
                meta
            )

            links = soup.new_tag(
                "div",
                attrs={
                    "class":
                        "paper-links"
                },
            )

            if record.get(
                "pubmed_url"
            ):
                link = soup.new_tag(
                    "a",
                    href=record[
                        "pubmed_url"
                    ],
                    target="_blank",
                    rel="noopener",
                )

                link[
                    "data-en"
                ] = "PubMed ↗"

                link[
                    "data-it"
                ] = "PubMed ↗"

                link.string = (
                    "PubMed ↗"
                )

                links.append(
                    link
                )

            if record.get(
                "doi_url"
            ):
                link = soup.new_tag(
                    "a",
                    href=record[
                        "doi_url"
                    ],
                    target="_blank",
                    rel="noopener",
                )

                link[
                    "data-en"
                ] = "DOI ↗"

                link[
                    "data-it"
                ] = "DOI ↗"

                link.string = (
                    "DOI ↗"
                )

                links.append(
                    link
                )

            if record.get(
                "pmc_url"
            ):
                link = soup.new_tag(
                    "a",
                    href=record[
                        "pmc_url"
                    ],
                    target="_blank",
                    rel="noopener",
                )

                link[
                    "data-en"
                ] = "Full text ↗"

                link[
                    "data-it"
                ] = "Testo completo ↗"

                link.string = (
                    "Full text ↗"
                )

                links.append(
                    link
                )

            article.append(
                links
            )

            wrap.append(
                article
            )

            inserted_cards += 1
            inserted_for_record += 1

        if inserted_for_record:
            titles.add(
                title_key
            )

            if pmid:
                pmids.add(
                    pmid
                )

            if doi:
                dois.add(
                    doi
                )

            promoted_records += 1

    ensure_area_filter(
        soup
    )

    total = len(
        soup.select(
            "article.folder-paper"
        )
    )

    area_count = len(
        soup.select(
            "details.library-folder"
        )
    )

    for item in soup.select(
        ".library-status-item"
    ):
        strong = item.find(
            "strong"
        )

        span = item.find(
            "span"
        )

        if (
            not strong
            or not span
        ):
            continue

        label = (
            span.get(
                "data-en"
            )
            or ""
        ).lower()

        if (
            "publication"
            in label
        ):
            strong[
                "data-publication-count"
            ] = ""

            strong.string = str(
                total
            )

        elif (
            "clinical areas"
            in label
        ):
            strong[
                "data-clinical-area-count"
            ] = ""

            strong.string = str(
                area_count
            )

    LIBRARY.write_text(
        str(soup),
        encoding="utf-8",
    )

    ensure_filter_assets()

    update_home_and_script(
        total,
        area_count,
    )

    if promoted_records:
        print(
            f"Promoted "
            f"{promoted_records} "
            f"unique publication(s) "
            f"automatically; "
            f"inserted "
            f"{inserted_cards} "
            f"area card(s). "
            f"Curated total: "
            f"{total}"
        )

    else:
        print(
            f"No new unique "
            f"auto-eligible records "
            f"to promote. "
            f"Curated total: "
            f"{total}"
        )


if __name__ == "__main__":
    main()
