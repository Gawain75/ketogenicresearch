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

QUERY = """
(
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
        OR "β-hydroxybutyrate"[Title/Abstract]
        OR "ketone bodies"[Title/Abstract]
    )
    AND
    (
        ketogenic[Title/Abstract]
        OR "nutritional ketosis"[Title/Abstract]
        OR "ketogenic therapy"[Title/Abstract]
    )
)
)
"""

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2,
    "mar": 3, "march": 3, "apr": 4, "april": 4,
    "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

TITLE_CORE_TERMS = (
    "ketogenic", "nutritional ketosis", "modified atkins", "vlckd", "vlekt",
    "exogenous ketone", "ketone ester", "ketone esters",
    "ketone salt", "ketone salts",
)

TITLE_SECONDARY_TERMS = (
    "beta-hydroxybutyrate",
    "β-hydroxybutyrate",
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
        "obesity", "obese", "weight loss", "body weight", "bariatric"
    ],
    "Diabetes & Glucose Metabolism": [
        "diabetes", "glycemic", "glycaemic", "glucose",
        "insulin resistance", "prediabetes", "hba1c"
    ],
    "MASLD / Metabolic Liver Disease": [
        "masld", "nafld", "fatty liver", "steatotic liver",
        "hepatic steatosis", "liver disease"
    ],
    "Dyslipidemia & Lipid Metabolism": [
        "ldl", "cholesterol", "lipid", "lipoprotein",
        "triglyceride", "hypercholesterolemia"
    ],
    "Lipid Energy Model / LMHR": [
        "lean mass hyper-responder", "lmhr", "lipid energy model"
    ],
    "Thyroid Disorders": [
        "thyroid", "tsh", "thyroxine", "triiodothyronine"
    ],
    "Cushing Syndrome": [
        "cushing", "hypercortisol", "cortisol"
    ],
    "Polyendocrine Metabolic Ovarian Syndrome (PMOS, formerly PCOS)": [
        "pcos", "polycystic ovary", "polycystic ovarian",
        "pcom", "pomos", "pmos"
    ],
    "Epilepsy": [
        "epilepsy", "epileptic", "seizure",
        "drug-resistant epilepsy", "refractory epilepsy"
    ],
    "Alzheimer’s Disease": [
        "alzheimer", "mild cognitive impairment"
    ],
    "Parkinson
