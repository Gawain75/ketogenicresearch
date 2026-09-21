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
OUT = ROOT / "latest-publications.json"

TOOL = "ketogenicresearch-literature-monitor"
EMAIL = os.getenv("NCBI_EMAIL", "info@ketogenicresearch.org")
API_KEY = os.getenv("NCBI_API_KEY", "")
WINDOW_DAYS = int(os.getenv("WINDOW_DAYS", "90"))
MAX_RECORDS = int(os.getenv("MAX_RECORDS", "100"))

BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

CORE = (
    '("ketogenic diet"[Title/Abstract] OR "ketogenic diets"[Title/Abstract] '
    'OR "ketogenic therapy"[Title/Abstract] OR "ketogenic metabolic therapy"[Title/Abstract] '
    'OR "nutritional ketosis"[Title/Abstract] OR "very low calorie ketogenic diet"[Title/Abstract] '
    'OR "very-low-calorie ketogenic diet"[Title/Abstract] OR VLCKD[Title/Abstract] '
    'OR "very low energy ketogenic"[Title/Abstract] OR VLEKT[Title/Abstract] '
    'OR "beta-hydroxybutyrate"[Title/Abstract] OR "β-hydroxybutyrate"[Title/Abstract] '
    'OR "ketone bodies"[Title/Abstract])'
)

AREA_TERMS = {
    "Obesity": '(obesity[Title/Abstract] OR overweight[Title/Abstract] OR "body composition"[Title/Abstract])',
    "Diabetes & Glucose Metabolism": '(diabetes[Title/Abstract] OR glycemic[Title/Abstract] OR insulin[Title/Abstract])',
    "MASLD / Metabolic Liver Disease": '(MASLD[Title/Abstract] OR NAFLD[Title/Abstract] OR "fatty liver"[Title/Abstract] OR steatosis[Title/Abstract])
