#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import os
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LATEST_OUT = ROOT / "latest-publications.json"
QUEUE_OUT = ROOT / "review-queue.json"
LIBRARY_HTML = ROOT / "library.html"

EMAIL = os.getenv("NCBI_EMAIL", "info@ketogenicresearch.org")
API_KEY = os.getenv("NCBI_API_KEY", "")
WINDOW_DAYS = int(os.getenv("WINDOW_DAYS", "90"))
CURATION_WINDOW_DAYS = int(os.getenv("CURATION_WINDOW_DAYS", "365"))
MAX_RECORDS = int(os.getenv("MAX_RECORDS", "100"))
CURATION_MAX_RECORDS = int(os.getenv("CURATION_MAX_RECORDS", "500"))

BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

QUERY = r'''(
"ketogenic diet"[Title/Abstract]
OR "ketogenic diets"[Title/Abstract]
OR "ketogenic therapy"[Title/Abstract]
OR "ketogenic metabolic therapy"[Title/Abstract]
OR "nutritional ketosis"[Title/Abstract]
OR "very low calorie ketogenic diet"[Title/Abstract]
OR "very-low-calorie ketogenic diet"[Title/Abstract]
OR "very low energy ketogenic therapy"[Title/Abstract]
OR "modified Atkins diet"[Title/Abstract]
OR VLCKD[Title/Abstract]
OR VLEKT[Title/Abstract]
OR "exogenous ketone"[Title/Abstract]
OR "exogenous ketones"[Title/Abstract]
OR "ketone ester"[Title/Abstract]
OR "ketone esters"[Title/Abstract]
OR "ketone salt"[Title/Abstract]
OR "ketone salts"[Title/Abstract]
OR (
    (
        "beta-hydroxybutyrate"[Title/Abstract]
        OR "ketone bodies"[Title/Abstract]
    )
    AND
    (
        ketogenic[Title/Abstract]
        OR "nutritional ketosis"[Title/Abstract]
        OR "ketogenic therapy"[Title/Abstract]
    )
)
)'''

MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

TITLE_CORE_TERMS = (
    "ketogenic",
    "nutritional ketosis",
    "modified atkins",
    "vlckd",
    "vlekt",
    "exogenous ketone",
    "ketone ester",
    "ketone esters",
    "ketone salt",
    "ketone salts",
)

TITLE_SECONDARY_TERMS = (
    "beta-hydroxybutyrate",
    "ketone bodies",
)

CONTEXT_TERMS = (
    "ketogenic diet",
    "ketogenic diets",
    "ketogenic therapy",
    "ketogenic metabolic therapy",
    "nutritional ketosis",
)

AREA_RULES = {
    "Obesity": [
        "obesity", "obese", "weight loss",
        "body weight", "bariatric"
    ],
    "Diabetes & Glucose Metabolism": [
        "diabetes", "glycemic", "glycaemic",
        "glucose", "insulin resistance",
        "prediabetes", "hba1c"
    ],
    "MASLD / Metabolic Liver Disease": [
        "masld", "nafld", "fatty liver",
        "steatotic liver", "hepatic steatosis",
        "liver disease"
    ],
    "Dyslipidemia & Lipid Metabolism": [
        "ldl", "cholesterol", "lipid",
        "lipoprotein", "triglyceride",
        "hypercholesterolemia"
    ],
    "Lipid Energy Model / LMHR": [
        "lean mass hyper-responder",
        "lmhr",
        "lipid energy model"
    ],
    "Thyroid Disorders": [
        "thyroid", "tsh", "thyroxine",
        "triiodothyronine"
    ],
    "Cushing Syndrome": [
        "cushing", "hypercortisol", "cortisol"
    ],
    "Polyendocrine Metabolic Ovarian Syndrome (PMOS, formerly PCOS)": [
        "pcos", "polycystic ovary",
        "polycystic ovarian", "pcom",
        "pomos", "pmos"
    ],
    "Epilepsy": [
        "epilepsy", "epileptic", "seizure",
        "drug-resistant epilepsy",
        "refractory epilepsy"
    ],
    "Alzheimer's Disease": [
        "alzheimer",
        "mild cognitive impairment"
    ],
    "Parkinson's Disease": [
        "parkinson"
    ],
    "Huntington's Disease": [
        "huntington"
    ],
    "Neurodegenerative Disorders": [
        "neurodegenerative",
        "amyotrophic lateral sclerosis",
        "als",
        "motor neuron"
    ],
    "GLUT1 Deficiency Syndrome": [
        "glut1",
        "glucose transporter type 1"
    ],
    "Pyruvate Dehydrogenase Deficiency": [
        "pyruvate dehydrogenase",
        "pdh deficiency",
        "pdhc"
    ],
    "Brain Injury & Neurotrauma": [
        "traumatic brain injury",
        "brain injury",
        "neurotrauma",
        "concussion"
    ],
    "Cognitive Function": [
        "cognitive",
        "memory",
        "cognition"
    ],
    "Headache & Migraine": [
        "migraine",
        "headache",
        "cluster headache"
    ],
    "Multiple Sclerosis": [
        "multiple sclerosis"
    ],
    "Autism Spectrum Disorder": [
        "autism",
        "autistic"
    ],
    "Psychiatry & Mental Health": [
        "bipolar",
        "schizophrenia",
        "depression",
        "anxiety",
        "psychiatric",
        "mental health",
        "psychosis",
        "mood disorder"
    ],
    "Substance Use Disorders": [
        "alcohol use",
        "alcohol withdrawal",
        "ethanol",
        "substance use",
        "addiction",
        "opioid"
    ],
    "Eating Disorders": [
        "binge eating",
        "eating disorder",
        "anorexia nervosa",
        "bulimia"
    ],
    "Oncology & Cancer Metabolism": [
        "cancer",
        "tumor",
        "tumour",
        "glioblastoma",
        "glioma",
        "carcinoma",
        "melanoma",
        "oncology",
        "neoplasm"
    ],
    "Cardiovascular Health": [
        "cardiovascular",
        "heart",
        "cardiac",
        "myocard",
        "atherosclerosis",
        "blood pressure",
        "vascular"
    ],
    "ADPKD": [
        "adpkd",
        "polycystic kidney"
    ],
    "Chronic Kidney Disease": [
        "chronic kidney",
        "renal impairment",
        "kidney disease",
        "renal disease",
        "egfr"
    ],
    "Urinary Incontinence": [
        "urinary incontinence",
        "lower urinary tract",
        "bladder function"
    ],
    "Sarcopenia & Skeletal Muscle": [
        "sarcopenia",
        "skeletal muscle",
        "muscle mass",
        "muscle strength",
        "handgrip",
        "motor unit"
    ],
    "Osteoarthritis": [
        "osteoarthritis"
    ],
    "Rheumatoid Arthritis": [
        "rheumatoid",
        "inflammatory arthritis"
    ],
    "Fibromyalgia": [
        "fibromyalgia"
    ],
    "Acne": [
        "acne",
        "hidradenitis"
    ],
    "Psoriasis": [
        "psoriasis",
        "psoriatic"
    ],
    "Keto Rash / Prurigo Pigmentosa": [
        "prurigo pigmentosa",
        "keto rash"
    ],
    "Asthma": [
        "asthma"
    ],
    "Inflammation & Immunometabolism": [
        "inflammation",
        "inflammatory",
        "immune",
        "immunometabolism",
        "nlrp3",
        "inflammasome"
    ],
    "Endometriosis": [
        "endometriosis"
    ],
    "Reproduction & Fertility": [
        "fertility",
        "infertility",
        "reproductive",
        "ivf",
        "testosterone",
        "ovarian function"
    ],
    "Lipedema": [
        "lipedema",
        "lipoedema"
    ],
    "Longevity & Healthy Aging": [
        "aging",
        "ageing",
        "longevity",
        "lifespan",
        "healthy aging"
    ],
    "Circadian Rhythms": [
        "circadian",
        "sleep",
        "wakefulness"
    ],
    "Gut Microbiome": [
        "microbiome",
        "microbiota",
        "gut bacteria",
        "intestinal microbiota"
    ],
    "Candida & Mycobiome": [
        "candida",
        "mycobiome",
        "fungal microbiome"
    ],
    "Exogenous Ketones": [
        "exogenous ketone",
        "ketone ester",
        "ketone salt"
    ],
    "Medium-Chain Triglycerides (MCT)": [
        "medium-chain triglyceride",
        "medium chain triglyceride",
        "mct",
        "tricaprylin",
        "coconut oil"
    ],
    "Supplementation & Nutraceuticals": [
        "supplement",
        "nutraceutical",
        "exogenous ketone",
        "ketone ester",
        "ketone salt"
    ],
    "Exercise & Performance": [
        "exercise",
        "athlete",
        "athletic",
        "performance",
        "endurance",
        "training",
        "vo2"
    ],
    "Glaucoma": [
        "glaucoma"
    ],
    "Down Syndrome": [
        "down syndrome",
        "trisomy 21"
    ],
    "Gilbert Syndrome": [
        "gilbert syndrome",
        "bilirubin"
    ],
    "COVID-19 & Metabolism": [
        "covid",
        "sars-cov-2",
        "long covid"
    ],
    "Aesthetic Medicine & Body Composition": [
        "body composition",
        "fat mass",
        "lean mass",
        "aesthetic medicine"
    ],
}

EVIDENCE_LABEL_IT = {
    "Systematic review / meta-analysis":
        "Revisione sistematica / meta-analisi",
    "Guideline / consensus":
        "Linea guida / consensus",
    "Randomized clinical trial":
        "Trial clinico randomizzato",
    "Clinical trial / intervention":
        "Trial clinico / intervento",
    "Observational human study":
        "Studio osservazionale umano",
    "Case report / case series":
        "Case report / case series",
    "Review":
        "Revisione",
    "Preclinical / mechanistic":
        "Preclinico / meccanicistico",
    "Other":
        "Altro",
}


def api(name: str, params: dict[str, str]) -> bytes:
    params = {
        **params,
        "tool": "ketogenicresearch-literature-monitor",
        "email": EMAIL,
    }

    if API_KEY:
        params["api_key"] = API_KEY

    url = f"{BASE}/{name}?{urllib.parse.urlencode(params)}"

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent":
                f"ketogenicresearch-literature-monitor/2.0 ({EMAIL})"
        },
    )

    with urllib.request.urlopen(req, timeout=60) as response:
        data = response.read()

    time.sleep(0.12 if API_KEY else 0.36)

    return data


def clean_text(node) -> str:
    if node is None:
        return ""

    return "".join(node.itertext()).strip()


def normalize_title(value: str) -> str:
    value = re.sub(
        r"^\s*\d+\.\s*",
        "",
        value or "",
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    ).strip().lower()

    return re.sub(
        r"[^a-z0-9]+",
        " ",
        value,
    )


def load_curated_titles() -> set[str]:
    if not LIBRARY_HTML.exists():
        return set()

    html = LIBRARY_HTML.read_text(
        encoding="utf-8"
    )

    titles = re.findall(
        r'<h4[^>]*data-en="([^"]+)"',
        html,
    )

    return {
        normalize_title(t)
        for t in titles
        if t
    }


def load_previous_queue() -> dict[str, dict]:
    if not QUEUE_OUT.exists():
        return {}

    try:
        data = json.loads(
            QUEUE_OUT.read_text(
                encoding="utf-8"
            )
        )

        return {
            str(x.get("pmid")): x
            for x in data.get("records", [])
            if x.get("pmid")
        }

    except Exception:
        return {}


def is_relevant_record(
    article: ET.Element
) -> bool:

    title = clean_text(
        article.find("ArticleTitle")
    ).lower()

    abstract = " ".join(
        clean_text(n)
        for n in article.findall(
            "Abstract/AbstractText"
        )
    ).lower()

    text = f"{title} {abstract}"

    if any(
        term in title
        for term in TITLE_CORE_TERMS
    ):
        return True

    if any(
        term in title
        for term in TITLE_SECONDARY_TERMS
    ):
        return any(
            term in text
            for term in CONTEXT_TERMS
        )

    return False


def classify_areas(
    title: str,
    abstract: str,
    mesh_terms: list[str],
) -> tuple[list[str], int]:

    title_l = title.lower()

    combined = " ".join(
        [
            title,
            abstract,
            *mesh_terms,
        ]
    ).lower()

    scored = []

    for area, keywords in AREA_RULES.items():
        score = 0

        for kw in keywords:
            if kw in title_l:
                score += 4

            elif kw in combined:
                score += 1

        if score:
            scored.append(
                (score, area)
            )

    scored.sort(
        key=lambda x: (
            -x[0],
            x[1],
        )
    )

    strong = [
        (score, area)
        for score, area in scored
        if score >= 1
    ]

    if not strong:
        return [
            "Other / General"
        ], 0

    areas = [
        area
        for score, area in strong[:3]
    ]

    confidence = strong[0][0]

    return areas, confidence


def classify_evidence(
    item: ET.Element,
    title: str,
    abstract: str,
) -> str:

    types = [
        clean_text(n).lower()
        for n in item.findall(
            ".//PublicationTypeList/PublicationType"
        )
    ]

    text = f"{title} {abstract}".lower()
    joined = " ".join(types)

    if (
        "meta-analysis" in joined
        or "meta-analysis" in text
        or "systematic review" in joined
        or "systematic review" in text
    ):
        return "Systematic review / meta-analysis"

    if (
        "guideline" in joined
        or "consensus" in text
        or "position statement" in text
    ):
        return "Guideline / consensus"

    if (
        "randomized controlled trial" in joined
        or "randomized" in text
        or "randomised" in text
    ):
        return "Randomized clinical trial"

    if (
        "clinical trial" in joined
        or "clinical trial" in text
        or "intervention" in text
    ):
        return "Clinical trial / intervention"

    if (
        any(
            x in joined
            for x in [
                "observational study",
                "cohort",
                "case-control",
            ]
        )
        or any(
            x in text
            for x in [
                "prospective",
                "retrospective",
                "cohort study",
                "cross-sectional",
            ]
        )
    ):
        return "Observational human study"

    if (
        any(
            x in joined
            for x in [
                "case reports",
                "case report",
            ]
        )
        or "case series" in text
    ):
        return "Case report / case series"

    if (
        "review" in joined
        or "review" in text
    ):
        return "Review"

    if any(
        x in text
        for x in [
            "mouse",
            "mice",
            "rat ",
            "rats",
            "cell line",
            "in vitro",
            "animal model",
            "preclinical",
        ]
    ):
        return "Preclinical / mechanistic"

    return "Other"


def parse_month(
    value: str
) -> int | None:

    value = (
        value or ""
    ).strip()

    if not value:
        return None

    if value.isdigit():
        month = int(value)

        return (
            month
            if 1 <= month <= 12
            else None
        )

    return MONTHS.get(
        value.lower()
    )


def make_date(
    year: int,
    month: int | None = None,
    day: int | None = None,
) -> dict:

    if (
        month is not None
        and day is not None
    ):

        try:
            full = dt.date(
                year,
                month,
                day,
            )

            return {
                "date":
                    full.isoformat(),
                "date_precision":
                    "day",
                "sort_key":
                    (
                        year,
                        month,
                        day,
                    ),
            }

        except ValueError:
            pass

    if month is not None:

        return {
            "date":
                f"{year:04d}-{month:02d}",
            "date_precision":
                "month",
            "sort_key":
                (
                    year,
                    month,
                    0,
                ),
        }

    return {
        "date":
            f"{year:04d}",
        "date_precision":
            "year",
        "sort_key":
            (
                year,
                0,
                0,
            ),
    }


def date_from_node(
    node
) -> dict | None:

    if node is None:
        return None

    year_text = clean_text(
        node.find("Year")
    )

    month_text = clean_text(
        node.find("Month")
    )

    day_text = clean_text(
        node.find("Day")
    )

    if year_text.isdigit():

        year = int(
            year_text
        )

        month = parse_month(
            month_text
        )

        day = (
            int(day_text)
            if day_text.isdigit()
            else None
        )

        return make_date(
            year,
            month,
            day,
        )

    medline = clean_text(
        node.find("MedlineDate")
    )

    if medline:

        match = re.search(
            r"\b(?:19|20)\d{2}\b",
            medline,
        )

        if match:

            year = int(
                match.group(0)
            )

            month = None

            lower = medline.lower()

            for name, number in MONTHS.items():

                if re.search(
                    rf"\b{re.escape(name)}\b",
                    lower,
                ):
                    month = number
                    break

            return make_date(
                year,
                month,
            )

    return None


def publication_date(
    pubmed_article: ET.Element
) -> dict:

    candidates = []

    for node in pubmed_article.findall(
        ".//Article/ArticleDate"
    ):

        parsed = date_from_node(
            node
        )

        if parsed:
            candidates.append(
                parsed
            )

    if candidates:

        candidates.sort(
            key=lambda x:
                x["sort_key"],
            reverse=True,
        )

        return candidates[0]

    preferred_statuses = (
        "epublish",
        "ppublish",
        "pubmed",
    )

    status_candidates = []

    for node in pubmed_article.findall(
        ".//PubmedData/History/PubMedPubDate"
    ):

        status = (
            node.attrib.get(
                "PubStatus"
            )
            or ""
        ).lower()

        parsed = date_from_node(
            node
        )

        if parsed:

            priority = (
                preferred_statuses.index(
                    status
                )
                if status
                in preferred_statuses
                else 99
            )

            status_candidates.append(
                (
                    priority,
                    parsed,
                )
            )

    preferred = [
        x
        for x in status_candidates
        if x[0] < 99
    ]

    if preferred:

        preferred.sort(
            key=lambda x: (
                x[0],
                tuple(
                    -v
                    for v
                    in x[1]["sort_key"]
                ),
            )
        )

        return preferred[0][1]

    journal_date = date_from_node(
        pubmed_article.find(
            ".//Article/Journal/JournalIssue/PubDate"
        )
    )

    if journal_date:
        return journal_date

    if status_candidates:

        status_candidates.sort(
            key=lambda x:
                x[1]["sort_key"],
            reverse=True,
        )

        return (
            status_candidates[0][1]
        )

    return {
        "date": "",
        "date_precision":
            "unknown",
        "sort_key":
            (
                0,
                0,
                0,
            ),
    }


def is_within_recent_window(
    date_info: dict,
    cutoff: dt.date,
    today: dt.date,
) -> bool:

    precision = date_info.get(
        "date_precision"
    )

    value = date_info.get(
        "date",
        "",
    )

    if (
        precision == "day"
        and re.fullmatch(
            r"\d{4}-\d{2}-\d{2}",
            value,
        )
    ):

        try:

            published = dt.date.fromisoformat(
                value
            )

            return (
                cutoff
                <= published
                <= today
            )

        except ValueError:
            return False

    if (
        precision == "month"
        and re.fullmatch(
            r"\d{4}-\d{2}",
            value,
        )
    ):

        year, month = map(
            int,
            value.split("-"),
        )

        try:

            month_start = dt.date(
                year,
                month,
                1,
            )

            if month == 12:
                next_month = dt.date(
                    year + 1,
                    1,
                    1,
                )
            else:
                next_month = dt.date(
                    year,
                    month + 1,
                    1,
                )

            month_end = (
                next_month
                - dt.timedelta(
                    days=1
                )
            )

            return (
                month_end >= cutoff
                and month_start <= today
            )

        except ValueError:
            return False

    return False


def is_new_publication(
    date_info: dict,
    today: dt.date,
) -> bool:

    if (
        date_info.get(
            "date_precision"
        )
        != "day"
    ):
        return False

    try:
        published = dt.date.fromisoformat(
            date_info.get(
                "date",
                "",
            )
        )

    except ValueError:
        return False

    age = (
        today - published
    ).days

    return (
        0 <= age <= 14
    )


def main() -> None:

    today = dt.date.today()

    cutoff = (
        today
        - dt.timedelta(
            days=WINDOW_DAYS
        )
    )

    curation_cutoff = (
        today
        - dt.timedelta(
            days=CURATION_WINDOW_DAYS
        )
    )

    curated_titles = (
        load_curated_titles()
    )

    previous_queue = (
        load_previous_queue()
    )

    search = json.loads(
        api(
            "esearch.fcgi",
            {
                "db":
                    "pubmed",
                "term":
                    QUERY,
                "retmode":
                    "json",
                "retmax":
                    str(
                        CURATION_MAX_RECORDS
                    ),
                "sort":
                    "pub date",
                "datetype":
                    "pdat",
                "mindate":
                    curation_cutoff.strftime(
                        "%Y/%m/%d"
                    ),
                "maxdate":
                    today.strftime(
                        "%Y/%m/%d"
                    ),
            },
        ).decode(
            "utf-8"
        )
    )

    ids = (
        search
        .get(
            "esearchresult",
            {},
        )
        .get(
            "idlist",
            [],
        )
    )

    if not ids:
        raise SystemExit(
            "No PubMed records returned."
        )

    root = ET.fromstring(
        api(
            "efetch.fcgi",
            {
                "db":
                    "pubmed",
                "id":
                    ",".join(ids),
                "retmode":
                    "xml",
            },
        )
    )

    publications = []
    queue = []

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

        if (
            citation is None
            or article is None
            or not is_relevant_record(
                article
            )
        ):
            continue

        pmid = clean_text(
            citation.find(
                "PMID"
            )
        )

        title = clean_text(
            article.find(
                "ArticleTitle"
            )
        )

        abstract = " ".join(
            clean_text(n)
            for n in article.findall(
                "Abstract/AbstractText"
            )
        )

        journal = clean_text(
            article.find(
                "Journal/Title"
            )
        )

        authors = []

        for author in article.findall(
            "AuthorList/Author"
        ):

            collective = clean_text(
                author.find(
                    "CollectiveName"
                )
            )

            if collective:
                authors.append(
                    collective
                )
                continue

            last = clean_text(
                author.find(
                    "LastName"
                )
            )

            initials = clean_text(
                author.find(
                    "Initials"
                )
            )

            name = " ".join(
                x
                for x in (
                    last,
                    initials,
                )
                if x
            )

            if name:
                authors.append(
                    name
                )

        doi = ""

        for aid in item.findall(
            ".//ArticleId"
        ):

            if (
                (
                    aid.attrib.get(
                        "IdType"
                    )
                    or ""
                ).lower()
                == "doi"
            ):

                doi = clean_text(
                    aid
                )

                break

        mesh_terms = [
            clean_text(n)
            for n in citation.findall(
                ".//MeshHeading/DescriptorName"
            )
            if clean_text(n)
        ]

        date_info = publication_date(
            item
        )

        if not is_within_recent_window(
            date_info,
            curation_cutoff,
            today,
        ):
            continue

        (
            areas,
            category_confidence,
        ) = classify_areas(
            title,
            abstract,
            mesh_terms,
        )

        evidence_type = (
            classify_evidence(
                item,
                title,
                abstract,
            )
        )

        year = (
            date_info[
                "sort_key"
            ][0]
            or None
        )

        status = (
            "new"
            if is_new_publication(
                date_info,
                today,
            )
            else "indexed"
        )

        record = {
            "pmid":
                pmid,
            "title":
                title,
            "authors":
                authors,
            "journal":
                journal,
            "date":
                date_info["date"],
            "date_precision":
                date_info[
                    "date_precision"
                ],
            "year":
                year,
            "doi":
                doi,
            "pubmed_url":
                (
                    f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
                    if pmid
                    else ""
                ),
            "doi_url":
                (
                    f"https://doi.org/{doi}"
                    if doi
                    else ""
                ),
            "areas":
                areas,
            "category_confidence":
                category_confidence,
            "evidence_type":
                evidence_type,
            "evidence_type_it":
                EVIDENCE_LABEL_IT.get(
                    evidence_type,
                    evidence_type,
                ),
            "source":
                "PubMed",
            "first_seen":
                (
                    previous_queue
                    .get(
                        pmid,
                        {},
                    )
                    .get(
                        "first_seen"
                    )
                    or today.isoformat()
                ),
            "status":
                status,
            "_sort_key":
                date_info[
                    "sort_key"
                ],
        }

        if is_within_recent_window(
            date_info,
            cutoff,
            today,
        ):

            publications.append(
                record
            )

        if (
            normalize_title(
                title
            )
            not in curated_titles
        ):

            valid_areas = [
                a
                for a in areas
                if a
                != "Other / General"
            ]

            auto_eligible = bool(
                valid_areas
                and category_confidence
                >= 1
            )

            queue.append(
                {
                    "pmid":
                        pmid,
                    "title":
                        title,
                    "authors":
                        authors,
                    "journal":
                        journal,
                    "date":
                        date_info[
                            "date"
                        ],
                    "doi":
                        doi,
                    "pubmed_url":
                        record[
                            "pubmed_url"
                        ],
                    "doi_url":
                        record[
                            "doi_url"
                        ],
                    "areas":
                        areas,
                    "category_confidence":
                        category_confidence,
                    "auto_eligible":
                        auto_eligible,
                    "evidence_type":
                        evidence_type,
                    "evidence_type_it":
                        EVIDENCE_LABEL_IT.get(
                            evidence_type,
                            evidence_type,
                        ),
                    "first_seen":
                        record[
                            "first_seen"
                        ],
                    "curation_status":
                        (
                            "auto-approved"
                            if auto_eligible
                            else
                            "excluded-low-confidence"
                        ),
                }
            )

    publications.sort(
        key=lambda p: (
            p[
                "_sort_key"
            ],
            p.get(
                "pmid"
            )
            or "",
        ),
        reverse=True,
    )

    publications = (
        publications[
            :MAX_RECORDS
        ]
    )

    for p in publications:
        p.pop(
            "_sort_key",
            None,
        )

    queue.sort(
        key=lambda p: (
            p.get(
                "date"
            )
            or "",
            p.get(
                "pmid"
            )
            or "",
        ),
        reverse=True,
    )

    generated = (
        dt.datetime.now(
            dt.timezone.utc
        )
        .replace(
            microsecond=0
        )
        .isoformat()
    )

    LATEST_OUT.write_text(
        json.dumps(
            {
                "generated_at":
                    generated,
                "window_days":
                    WINDOW_DAYS,
                "max_records":
                    MAX_RECORDS,
                "source":
                    "PubMed / NCBI E-utilities",
                "count":
                    len(
                        publications
                    ),
                "publications":
                    publications,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    QUEUE_OUT.write_text(
        json.dumps(
            {
                "generated_at":
                    generated,
                "curation_window_days":
                    CURATION_WINDOW_DAYS,
                "auto_approved_count":
                    sum(
                        bool(
                            x.get(
                                "auto_eligible"
                            )
                        )
                        for x in queue
                    ),
                "excluded_count":
                    sum(
                        not bool(
                            x.get(
                                "auto_eligible"
                            )
                        )
                        for x in queue
                    ),
                "records":
                    queue,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        f"Wrote {len(publications)} "
        f"recent records to "
        f"{LATEST_OUT.name}"
    )

    print(
        f"Wrote {len(queue)} "
        f"non-curated candidates to "
        f"{QUEUE_OUT.name}"
    )


if __name__ == "__main__":
    main()
