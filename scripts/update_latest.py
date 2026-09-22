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
CURATION_MAX_RECORDS = int(os.getenv("CURATION_MAX_RECORDS", "2000"))

BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

QUERY = r'''(
"ketogenic diet"[Title/Abstract] OR "ketogenic diets"[Title/Abstract]
OR "ketogenic therapy"[Title/Abstract] OR "ketogenic metabolic therapy"[Title/Abstract]
OR "nutritional ketosis"[Title/Abstract] OR "very low calorie ketogenic diet"[Title/Abstract]
OR "very-low-calorie ketogenic diet"[Title/Abstract] OR "very low energy ketogenic therapy"[Title/Abstract]
OR "modified Atkins diet"[Title/Abstract] OR VLCKD[Title/Abstract] OR VLEKT[Title/Abstract]
OR "exogenous ketone"[Title/Abstract] OR "exogenous ketones"[Title/Abstract]
OR "ketone ester"[Title/Abstract] OR "ketone esters"[Title/Abstract]
OR "ketone salt"[Title/Abstract] OR "ketone salts"[Title/Abstract]
OR (("beta-hydroxybutyrate"[Title/Abstract] OR "ketone bodies"[Title/Abstract])
AND (ketogenic[Title/Abstract] OR "nutritional ketosis"[Title/Abstract] OR "ketogenic therapy"[Title/Abstract]))
)'''

CORE = (
    "ketogenic", "nutritional ketosis", "modified atkins", "vlckd", "vlekt",
    "exogenous ketone", "ketone ester", "ketone salt",
)
SECONDARY = ("beta-hydroxybutyrate", "ketone bodies")
CONTEXT = (
    "ketogenic diet", "ketogenic diets", "ketogenic therapy",
    "ketogenic metabolic therapy", "nutritional ketosis",
)

AREA_RULES = {
    "Obesity": ["obesity", "obese", "weight loss", "body weight", "bariatric"],
    "Diabetes & Glucose Metabolism": ["diabetes", "glycemic", "glycaemic", "glucose", "insulin resistance", "prediabetes", "hba1c"],
    "MASLD / Metabolic Liver Disease": ["masld", "nafld", "fatty liver", "steatotic liver", "hepatic steatosis", "liver disease"],
    "Dyslipidemia & Lipid Metabolism": ["ldl", "cholesterol", "lipid", "lipoprotein", "triglyceride", "hypercholesterolemia"],
    "Lipid Energy Model / LMHR": ["lean mass hyper-responder", "lmhr", "lipid energy model"],
    "Thyroid Disorders": ["thyroid", "tsh", "thyroxine", "triiodothyronine"],
    "Cushing Syndrome": ["cushing", "hypercortisol", "cortisol"],
    "Polyendocrine Metabolic Ovarian Syndrome (PMOS, formerly PCOS)": ["pcos", "polycystic ovary", "polycystic ovarian", "pcom", "pmos"],
    "Epilepsy": ["epilepsy", "epileptic", "seizure", "drug-resistant epilepsy", "refractory epilepsy"],
    "Alzheimer’s Disease": ["alzheimer", "mild cognitive impairment"],
    "Parkinson’s Disease": ["parkinson"],
    "Huntington’s Disease": ["huntington"],
    "Neurodegenerative Disorders": ["neurodegenerative", "amyotrophic lateral sclerosis", "motor neuron"],
    "GLUT1 Deficiency Syndrome": ["glut1", "glucose transporter type 1"],
    "Pyruvate Dehydrogenase Deficiency": ["pyruvate dehydrogenase", "pdh deficiency", "pdhc"],
    "Brain Injury & Neurotrauma": ["traumatic brain injury", "brain injury", "neurotrauma", "concussion"],
    "Cognitive Function": ["cognitive", "memory", "cognition"],
    "Headache & Migraine": ["migraine", "headache", "cluster headache"],
    "Multiple Sclerosis": ["multiple sclerosis"],
    "Autism Spectrum Disorder": ["autism", "autistic"],
    "Psychiatry & Mental Health": ["bipolar", "schizophrenia", "depression", "anxiety", "psychiatric", "mental health", "psychosis", "mood disorder"],
    "Substance Use Disorders": ["alcohol use", "alcohol withdrawal", "ethanol", "substance use", "addiction", "opioid"],
    "Eating Disorders": ["binge eating", "eating disorder", "anorexia nervosa", "bulimia"],
    "Oncology & Cancer Metabolism": ["cancer", "tumor", "tumour", "glioblastoma", "glioma", "carcinoma", "melanoma", "oncology", "neoplasm"],
    "Cardiovascular Health": ["cardiovascular", "heart", "cardiac", "myocard", "atherosclerosis", "blood pressure", "vascular"],
    "ADPKD": ["adpkd", "polycystic kidney"],
    "Chronic Kidney Disease": ["chronic kidney", "renal impairment", "kidney disease", "renal disease", "egfr"],
    "Urinary Incontinence": ["urinary incontinence", "lower urinary tract", "bladder function"],
    "Sarcopenia & Skeletal Muscle": ["sarcopenia", "skeletal muscle", "muscle mass", "muscle strength", "handgrip", "motor unit"],
    "Osteoarthritis": ["osteoarthritis"],
    "Rheumatoid Arthritis": ["rheumatoid", "inflammatory arthritis"],
    "Fibromyalgia": ["fibromyalgia"],
    "Acne": ["acne", "hidradenitis"],
    "Psoriasis": ["psoriasis", "psoriatic"],
    "Keto Rash / Prurigo Pigmentosa": ["prurigo pigmentosa", "keto rash"],
    "Asthma": ["asthma"],
    "Inflammation & Immunometabolism": ["inflammation", "inflammatory", "immune", "immunometabolism", "nlrp3", "inflammasome"],
    "Endometriosis": ["endometriosis"],
    "Reproduction & Fertility": ["fertility", "infertility", "reproductive", "ivf", "testosterone", "ovarian function"],
    "Lipedema": ["lipedema", "lipoedema"],
    "Longevity & Healthy Aging": ["aging", "ageing", "longevity", "lifespan", "healthy aging"],
    "Circadian Rhythms": ["circadian", "sleep", "wakefulness"],
    "Gut Microbiome": ["microbiome", "microbiota", "gut bacteria", "intestinal microbiota"],
    "Candida & Mycobiome": ["candida", "mycobiome", "fungal microbiome"],
    "Exogenous Ketones": ["exogenous ketone", "ketone ester", "ketone salt"],
    "Medium-Chain Triglycerides (MCT)": ["medium-chain triglyceride", "medium chain triglyceride", "mct", "tricaprylin", "coconut oil"],
    "Supplementation & Nutraceuticals": ["supplement", "nutraceutical", "exogenous ketone", "ketone ester", "ketone salt"],
    "Exercise & Performance": ["exercise", "athlete", "athletic", "performance", "endurance", "training", "vo2"],
    "Glaucoma": ["glaucoma"],
    "Down Syndrome": ["down syndrome", "trisomy 21"],
    "Gilbert Syndrome": ["gilbert syndrome", "bilirubin"],
    "COVID-19 & Metabolism": ["covid", "sars-cov-2", "long covid"],
    "Aesthetic Medicine & Body Composition": ["body composition", "fat mass", "lean mass", "aesthetic medicine"],
}

BROAD_AREAS = {
    "Inflammation & Immunometabolism", "Cognitive Function", "Cardiovascular Health",
    "Longevity & Healthy Aging", "Aesthetic Medicine & Body Composition",
    "Supplementation & Nutraceuticals",
}

IT = {
    "Systematic review / meta-analysis": "Revisione sistematica / meta-analisi",
    "Guideline / consensus": "Linea guida / consensus",
    "Randomized clinical trial": "Trial clinico randomizzato",
    "Clinical trial / intervention": "Trial clinico / intervento",
    "Observational human study": "Studio osservazionale umano",
    "Case report / case series": "Case report / case series",
    "Review": "Revisione",
    "Preclinical / mechanistic": "Preclinico / meccanicistico",
    "Other": "Altro",
}

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}


def api(name, params):
    params = {**params, "tool": "ketogenicresearch-literature-monitor", "email": EMAIL}
    if API_KEY:
        params["api_key"] = API_KEY

    encoded = urllib.parse.urlencode(params).encode("utf-8")
    endpoint = f"{BASE}/{name}"

    if name == "efetch.fcgi" or len(encoded) > 1800:
        req = urllib.request.Request(
            endpoint,
            data=encoded,
            method="POST",
            headers={
                "User-Agent": f"ketogenicresearch/2.1 ({EMAIL})",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
    else:
        req = urllib.request.Request(
            f"{endpoint}?{encoded.decode('utf-8')}",
            headers={"User-Agent": f"ketogenicresearch/2.1 ({EMAIL})"},
        )

    with urllib.request.urlopen(req, timeout=60) as response:
        data = response.read()

    time.sleep(0.12 if API_KEY else 0.36)
    return data


def text(node):
    return "" if node is None else "".join(node.itertext()).strip()


def norm_title(value):
    value = re.sub(r"^\s*\d+\.\s*", "", value or "").lower()
    value = value.replace("’", "'").replace("–", "-").replace("—", "-")
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def norm_doi(value):
    value = (value or "").strip().lower()
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value)
    return value.rstrip(" .")


def existing_ids():
    if not LIBRARY_HTML.exists():
        return {"titles": set(), "pmids": set(), "dois": set()}

    html = LIBRARY_HTML.read_text(encoding="utf-8")

    titles = {
        norm_title(re.sub(r"<[^>]+>", "", x))
        for x in re.findall(r"<h4[^>]*>(.*?)</h4>", html, re.S)
        if x
    }

    pmids = set(
        re.findall(
            r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)/",
            html,
            re.I,
        )
    )

    dois = {
        norm_doi(x)
        for x in re.findall(
            r"https?://(?:dx\.)?doi\.org/([^\"'<>\s]+)",
            html,
            re.I,
        )
        if x
    }

    return {
        "titles": titles,
        "pmids": pmids,
        "dois": dois,
    }


def previous_queue():
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


def relevant(article):
    title = text(
        article.find("ArticleTitle")
    ).lower()

    abstract = " ".join(
        text(n)
        for n in article.findall(
            "Abstract/AbstractText"
        )
    ).lower()

    body = title + " " + abstract

    return (
        any(x in title for x in CORE)
        or (
            any(x in title for x in SECONDARY)
            and any(x in body for x in CONTEXT)
        )
    )


def classify(title, abstract, mesh):
    title_l = title.lower()
    abstract_l = abstract.lower()
    mesh_l = " ".join(mesh).lower()

    scored = []

    for area, keywords in AREA_RULES.items():
        score = 0
        title_hit = False

        for kw in keywords:
            if kw in title_l:
                score += 6
                title_hit = True
            elif kw in mesh_l:
                score += 2
            elif kw in abstract_l:
                score += 1

        if not score:
            continue

        if (
            area in BROAD_AREAS
            and not title_hit
            and score < 3
        ):
            continue

        scored.append(
            (score, area)
        )

    scored.sort(
        key=lambda x: (
            -x[0],
            x[1],
        )
    )

    if not scored:
        return [
            "Other / General"
        ], 0

    top = scored[0][0]

    areas = [
        area
        for score, area in scored
        if score >= max(
            2,
            top - 4,
        )
    ][:3]

    return (
        areas or ["Other / General"],
        top,
    )


def evidence(
    item,
    title,
    abstract,
    mesh,
):
    publication_types = [
        text(n).strip().lower()
        for n in item.findall(
            "./MedlineCitation/Article/PublicationTypeList/PublicationType"
        )
        if text(n).strip()
    ]
    types = " ".join(publication_types)

    body = (title + " " + abstract).lower()
    title_l = title.lower()
    mesh_l = {m.strip().lower() for m in mesh if m and m.strip()}

    # Prefer structured PubMed indexing when available. Recent records may not
    # yet be fully MEDLINE-indexed, so conservative text rules remain as a
    # fallback. Animal evidence must not become a human clinical study simply
    # because the abstract mentions patients in the background/discussion.
    mesh_humans = "humans" in mesh_l
    mesh_animals = (
        "animals" in mesh_l
        or any(x in mesh_l for x in ("mice", "rats", "zebrafish"))
    )

    animal_title = re.search(
        r"\b(mouse|mice|murine|rat|rats|rodent|rodents|zebrafish|drosophila|rabbit|rabbits|porcine|swine)\b",
        title_l,
    ) is not None
    animal_methods = re.search(
        r"\b(mouse|mice|murine|rat|rats|rodent|rodents|zebrafish|drosophila|rabbit|rabbits|porcine|swine)\b.{0,45}\b(fed|treated|randomi[sz]ed|assigned|received|injected|model|models)\b",
        body,
    ) is not None
    explicit_preclinical = (
        animal_title
        or animal_methods
        or "animal model" in body
        or "animal study" in body
        or "preclinical" in body
        or "in vitro" in body
        or "cell line" in body
        or "cell culture" in body
        or (mesh_animals and not mesh_humans)
    )

    explicit_human = (
        mesh_humans
        or re.search(
            r"\b(patient|patients|participant|participants|volunteer|volunteers|men|women|children|adolescent|adolescents|adult|adults)\b",
            body,
        ) is not None
    )

    if (
        "meta-analysis" in types
        or "meta-analysis" in body
        or "systematic review" in types
        or "systematic review" in body
    ):
        return "Systematic review / meta-analysis"

    if (
        "guideline" in types
        or "practice guideline" in types
        or "consensus" in body
        or "position statement" in body
    ):
        return "Guideline / consensus"

    # Case reports/series must be classified before generic clinical language.
    if (
        "case reports" in types
        or "case report" in types
        or "case report" in body
        or "case series" in body
    ) and not explicit_preclinical:
        return "Case report / case series"

    # Strong animal evidence takes precedence over incidental human wording.
    if explicit_preclinical and not (mesh_humans and not mesh_animals):
        return "Preclinical / mechanistic"

    if (
        "randomized controlled trial" in types
        or "controlled clinical trial" in types
        or (
            ("randomized" in body or "randomised" in body)
            and explicit_human
            and not explicit_preclinical
        )
    ):
        return "Randomized clinical trial"

    if (
        "clinical trial" in types
        or (
            ("clinical trial" in body or "intervention" in body)
            and explicit_human
            and not explicit_preclinical
        )
    ):
        return "Clinical trial / intervention"

    if (
        any(
            x in types
            for x in [
                "observational study",
                "cohort studies",
                "case-control studies",
            ]
        )
        or (
            any(
                x in body
                for x in [
                    "prospective",
                    "retrospective",
                    "cohort study",
                    "cross-sectional",
                ]
            )
            and explicit_human
        )
    ) and not explicit_preclinical:
        return "Observational human study"

    if "review" in types or "review" in body:
        return "Review"

    if explicit_preclinical:
        return "Preclinical / mechanistic"

    return "Other"

def pubdate(item):
    nodes = (
        item.findall(
            ".//Article/ArticleDate"
        )
        + item.findall(
            ".//PubmedData/History/PubMedPubDate"
        )
        + item.findall(
            ".//Article/Journal/JournalIssue/PubDate"
        )
    )

    for node in nodes:
        y = text(
            node.find("Year")
        )
        m = text(
            node.find("Month")
        )
        d = text(
            node.find("Day")
        )

        if not y.isdigit():
            continue

        year = int(y)

        month = (
            int(m)
            if m.isdigit()
            else (
                MONTHS.get(
                    m[:4].lower()
                )
                or MONTHS.get(
                    m[:3].lower()
                )
            )
        )

        if (
            month
            and d.isdigit()
        ):
            try:
                return (
                    dt.date(
                        year,
                        month,
                        int(d),
                    ),
                    "day",
                )
            except ValueError:
                pass

        if month:
            return (
                dt.date(
                    year,
                    month,
                    1,
                ),
                "month",
            )

    return (
        None,
        "unknown",
    )


def main():
    today = dt.date.today()

    latest_cutoff = (
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

    existing = existing_ids()
    old_queue = previous_queue()

    search = json.loads(
        api(
            "esearch.fcgi",
            {
                "db": "pubmed",
                "term": QUERY,
                "retmode": "json",
                "retmax": str(
                    CURATION_MAX_RECORDS
                ),
                "sort": "pub date",
                "datetype": "pdat",
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
                "db": "pubmed",
                "id": ",".join(ids),
                "retmode": "xml",
            },
        )
    )

    latest = []
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
            or not relevant(article)
        ):
            continue

        pmid = text(
            citation.find(
                "PMID"
            )
        )

        title = text(
            article.find(
                "ArticleTitle"
            )
        )

        abstract = " ".join(
            text(n)
            for n in article.findall(
                "Abstract/AbstractText"
            )
        )

        journal = text(
            article.find(
                "Journal/Title"
            )
        )

        date_value, precision = (
            pubdate(item)
        )

        if (
            not date_value
            or not (
                curation_cutoff
                <= date_value
                <= today
            )
        ):
            continue

        authors = []

        for author in article.findall(
            "AuthorList/Author"
        ):
            collective = text(
                author.find(
                    "CollectiveName"
                )
            )

            if collective:
                authors.append(
                    collective
                )
                continue

            name = " ".join(
                x
                for x in [
                    text(
                        author.find(
                            "LastName"
                        )
                    ),
                    text(
                        author.find(
                            "Initials"
                        )
                    ),
                ]
                if x
            )

            if name:
                authors.append(
                    name
                )

        doi = ""
        pmc = ""

        # Accept only identifiers belonging to the PubMed record itself.
        # Descendant-wide ArticleId searches can accidentally pick identifiers
        # from cited references.
        for article_id in item.findall(
            "./PubmedData/ArticleIdList/ArticleId"
        ):
            kind = (
                article_id.attrib.get(
                    "IdType"
                )
                or ""
            ).lower()

            if kind == "doi":
                doi = text(
                    article_id
                )

            elif kind == "pmc":
                pmc = text(
                    article_id
                )

        mesh = [
            text(n)
            for n in citation.findall(
                ".//MeshHeading/DescriptorName"
            )
            if text(n)
        ]

        areas, confidence = classify(
            title,
            abstract,
            mesh,
        )

        evidence_type = evidence(
            item,
            title,
            abstract,
            mesh,
        )

        date_string = (
            date_value.isoformat()
            if precision == "day"
            else date_value.strftime(
                "%Y-%m"
            )
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
                date_string,
            "date_precision":
                precision,
            "year":
                date_value.year,
            "doi":
                doi,
            "pmc":
                pmc,
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
            "pmc_url":
                (
                    f"https://pmc.ncbi.nlm.nih.gov/articles/{pmc}/"
                    if pmc
                    else ""
                ),
            "areas":
                areas,
            "category_confidence":
                confidence,
            "evidence_type":
                evidence_type,
            "evidence_type_it":
                IT.get(
                    evidence_type,
                    evidence_type,
                ),
            "source":
                "PubMed",
            "first_seen":
                (
                    old_queue
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
                (
                    "new"
                    if (
                        precision == "day"
                        and 0
                        <= (
                            today
                            - date_value
                        ).days
                        <= 14
                    )
                    else "indexed"
                ),
        }

        if (
            latest_cutoff
            <= date_value
            <= today
        ):
            latest.append(
                record
            )

        duplicate = (
            (
                pmid
                and pmid
                in existing[
                    "pmids"
                ]
            )
            or (
                doi
                and norm_doi(
                    doi
                )
                in existing[
                    "dois"
                ]
            )
            or (
                norm_title(
                    title
                )
                in existing[
                    "titles"
                ]
            )
        )

        if not duplicate:
            valid_areas = [
                a
                for a in areas
                if a
                != "Other / General"
            ]

            auto_eligible = bool(
                valid_areas
                and confidence
                >= 2
            )

            queue.append(
                {
                    **record,
                    "auto_eligible":
                        auto_eligible,
                    "curation_status":
                        (
                            "auto-approved"
                            if auto_eligible
                            else
                            "excluded-low-confidence"
                        ),
                }
            )

    latest = sorted(
        latest,
        key=lambda x: (
            x.get(
                "date"
            )
            or "",
            x.get(
                "pmid"
            )
            or "",
        ),
        reverse=True,
    )[:MAX_RECORDS]

    queue = sorted(
        queue,
        key=lambda x: (
            x.get(
                "date"
            )
            or "",
            x.get(
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

    # Keep two dates with different meanings:
    # - verified_at: last successful evidence check (every successful run)
    # - content_updated_at: last time the visible Latest Evidence dataset changed
    previous_latest = {}
    if LATEST_OUT.exists():
        try:
            previous_latest = json.loads(
                LATEST_OUT.read_text(
                    encoding="utf-8"
                )
            )
        except (
            OSError,
            json.JSONDecodeError,
        ):
            previous_latest = {}

    previous_publications = (
        previous_latest.get(
            "publications"
        )
        or []
    )
    content_changed = (
        previous_publications
        != latest
        or int(
            previous_latest.get(
                "window_days",
                WINDOW_DAYS,
            )
            or WINDOW_DAYS
        )
        != WINDOW_DAYS
        or int(
            previous_latest.get(
                "max_records",
                MAX_RECORDS,
            )
            or MAX_RECORDS
        )
        != MAX_RECORDS
    )

    if content_changed:
        content_updated_at = generated
    else:
        content_updated_at = (
            previous_latest.get(
                "content_updated_at"
            )
            or previous_latest.get(
                "generated_at"
            )
            or generated
        )

    LATEST_OUT.write_text(
        json.dumps(
            {
                "generated_at":
                    generated,
                "verified_at":
                    generated,
                "content_updated_at":
                    content_updated_at,
                "window_days":
                    WINDOW_DAYS,
                "max_records":
                    MAX_RECORDS,
                "source":
                    "PubMed / NCBI E-utilities",
                "count":
                    len(latest),
                "publications":
                    latest,
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
                        for x
                        in queue
                    ),
                "excluded_count":
                    sum(
                        not bool(
                            x.get(
                                "auto_eligible"
                            )
                        )
                        for x
                        in queue
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
        f"Wrote {len(latest)} recent records "
        f"to {LATEST_OUT.name}"
    )

    print(
        f"Wrote {len(queue)} non-curated candidates "
        f"to {QUEUE_OUT.name}"
    )


if __name__ == "__main__":
    main()
