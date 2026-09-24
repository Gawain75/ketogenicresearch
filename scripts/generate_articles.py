#!/usr/bin/env python3
"""
Ketogenic Research Hub — AI article pilot V4.1

V3 editorial-quality pilot:
- processes ONE article per run
- requests structured JSON output
- retries Groq HTTP 429 automatically with exponential backoff
- waits longer between generation and verification
- keeps the pilot isolated in articles-drafts/
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from io import BytesIO
from html.parser import HTMLParser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pubmed_citation import extract_citation_metadata, format_citation
ROOT = Path(__file__).resolve().parents[1]
LATEST = ROOT / "latest-publications.json"
OUT = ROOT / "articles-drafts"
INDEX = OUT / "generated-index.json"

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b").strip()
NCBI_EMAIL = os.environ.get("NCBI_EMAIL", "info@ketogenicresearch.org").strip()
NCBI_API_KEY = os.environ.get("NCBI_API_KEY", "").strip()
TARGET_PMID = os.environ.get("TARGET_PMID", "").strip()

# Publish at most one VERIFIED article per run; the fallback loop may scan multiple records.
MAX_ARTICLES = 1

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

POLICY_FILE = ROOT / "ARTICLE_EDITORIAL_POLICY.md"
POLICY_TEXT = POLICY_FILE.read_text(encoding="utf-8") if POLICY_FILE.exists() else """
Use only the supplied source.
Do not invent data.
Use neutral scientific language.
Distinguish findings from interpretation.
Do not make unsupported clinical recommendations.
For abstract-only records, explicitly disclose that the interpretation is based on the PubMed abstract.
"""

def http_request(
    url: str,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 60
) -> bytes:
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()

def pubmed_xml(pmid: str) -> ET.Element:
    params = {
        "db": "pubmed",
        "id": pmid,
        "retmode": "xml",
        "tool": "ketogenicresearch",
        "email": NCBI_EMAIL,
    }
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY

    url = f"{EUTILS}/efetch.fcgi?{urllib.parse.urlencode(params)}"
    return ET.fromstring(http_request(url))

def text_content(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return " ".join("".join(node.itertext()).split())

def norm_title(value: str) -> str:
    value = (value or "").lower().replace("β", "beta")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()

def norm_doi(value: str) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value)
    return value.rstrip(".,; ")

def extract_pubmed_source(root: ET.Element) -> dict[str, Any]:
    record = root.find(".//PubmedArticle")
    if record is None:
        return {}

    citation = record.find("MedlineCitation")
    article = citation.find("Article") if citation is not None else None
    if citation is None or article is None:
        return {}

    abstract_parts = []
    for node in article.findall("Abstract/AbstractText"):
        label = node.attrib.get("Label", "").strip()
        value = text_content(node)
        if value:
            abstract_parts.append(f"{label}: {value}" if label else value)

    ids: dict[str, str] = {}
    # CRITICAL: identifiers must come only from this record's PubmedData.
    # A descendant-wide lookup can pick DOI/PMCID values from references.
    for node in record.findall("./PubmedData/ArticleIdList/ArticleId"):
        kind = (node.attrib.get("IdType") or "").lower()
        value = text_content(node)
        if kind and value:
            ids[kind] = value

    mesh = []
    for node in citation.findall("MeshHeadingList/MeshHeading/DescriptorName"):
        value = text_content(node)
        if value:
            mesh.append(value)

    return {
        "pmid": text_content(citation.find("PMID")),
        "title": text_content(article.find("ArticleTitle")),
        "abstract": "\n".join(abstract_parts).strip(),
        "pmcid": ids.get("pmc", ""),
        "doi_from_pubmed": norm_doi(ids.get("doi", "")),
        "mesh": mesh[:30],
        "citation_meta": extract_citation_metadata(record),
    }

def verify_source_identity(rec: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    """Return a record corrected to authoritative PubMed identifiers.

    The generator must never use a DOI/PMCID from local JSON unless it agrees
    with the PubMed record selected by PMID. Title mismatch is treated as fatal.
    """
    expected_pmid = str(rec.get("pmid") or "").strip()
    pubmed_pmid = str(extra.get("pmid") or "").strip()
    if not expected_pmid or expected_pmid != pubmed_pmid:
        raise RuntimeError(
            f"PubMed identity mismatch: requested PMID {expected_pmid}, returned {pubmed_pmid or '[missing]'}"
        )

    local_title = norm_title(str(rec.get("title") or ""))
    pubmed_title = norm_title(str(extra.get("title") or ""))
    if not local_title or not pubmed_title or local_title != pubmed_title:
        raise RuntimeError(
            "PubMed identity mismatch: local title does not match the authoritative PMID title."
        )

    authoritative_doi = norm_doi(str(extra.get("doi_from_pubmed") or ""))
    authoritative_pmc = str(extra.get("pmcid") or "").strip()
    local_doi = norm_doi(str(rec.get("doi") or ""))
    local_pmc = str(rec.get("pmc") or "").strip()

    if local_doi and local_doi != authoritative_doi:
        print(
            f"Correcting stale DOI for PMID {expected_pmid}: "
            f"{local_doi} -> {authoritative_doi or '[none in PubMed]'}"
        )
    if local_pmc and local_pmc != authoritative_pmc:
        print(
            f"Correcting stale PMCID for PMID {expected_pmid}: "
            f"{local_pmc} -> {authoritative_pmc or '[none in PubMed]'}"
        )

    corrected = dict(rec)
    corrected["title"] = extra.get("title") or rec.get("title")
    corrected["doi"] = authoritative_doi
    corrected["pmc"] = authoritative_pmc
    corrected["doi_url"] = f"https://doi.org/{authoritative_doi}" if authoritative_doi else ""
    corrected["pmc_url"] = (
        f"https://pmc.ncbi.nlm.nih.gov/articles/{authoritative_pmc}/"
        if authoritative_pmc else ""
    )
    return corrected

def pmc_full_text(pmcid: str) -> str:
    if not pmcid:
        return ""

    params = {
        "db": "pmc",
        "id": pmcid,
        "retmode": "xml",
        "tool": "ketogenicresearch",
        "email": NCBI_EMAIL,
    }
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY

    url = f"{EUTILS}/efetch.fcgi?{urllib.parse.urlencode(params)}"

    try:
        root = ET.fromstring(http_request(url))
    except Exception:
        return ""

    def section_title(sec: ET.Element) -> str:
        title = sec.find("./title")
        return text_content(title).strip() if title is not None else ""

    def classify_section(title: str) -> int:
        t = title.lower()
        if any(k in t for k in ("limitation", "strengths and limitations")):
            return 0
        if any(k in t for k in ("discussion", "interpretation")):
            return 1
        if any(k in t for k in ("result", "finding")):
            return 2
        if any(k in t for k in ("method", "materials", "experimental", "procedure")):
            return 3
        if any(k in t for k in ("conclusion", "summary")):
            return 4
        if any(k in t for k in ("introduction", "background")):
            return 5
        return 6

    sections: list[tuple[int, str, str]] = []
    seen: set[str] = set()

    for sec in root.findall(".//body//sec"):
        title = section_title(sec) or "Untitled section"
        value = text_content(sec).strip()
        if len(value) < 120:
            continue

        key = re.sub(r"\s+", " ", value).strip().lower()
        if key in seen:
            continue
        seen.add(key)

        sections.append((classify_section(title), title, value[:6500]))

    sections.sort(key=lambda item: item[0])

    selected: list[str] = []
    total = 0
    max_chars = 30000

    for _, title, value in sections:
        block = f"### {title}\n{value}".strip()
        if total + len(block) > max_chars:
            remaining = max_chars - total
            if remaining >= 1200:
                block = block[:remaining]
            else:
                continue

        selected.append(block)
        total += len(block) + 2
        if total >= max_chars:
            break

    return "\n\n".join(selected).strip()

def groq_json(
    messages: list[dict[str, str]],
    max_tokens: int,
    temperature: float,
    attempts: int = 5
) -> dict[str, Any]:
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is missing.")

    payload = {
        "model": GROQ_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_completion_tokens": max_tokens,
        "reasoning_effort": "low",
        "reasoning_format": "hidden",
        "response_format": {"type": "json_object"},
    }

    encoded = json.dumps(payload).encode("utf-8")

    for attempt in range(1, attempts + 1):
        try:
            raw = http_request(
                GROQ_URL,
                data=encoded,
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                    "User-Agent": "KetogenicResearch/AI-Articles-Pilot-V2",
                },
                timeout=120,
            )

            obj = json.loads(raw)
            content = obj["choices"][0]["message"]["content"].strip()

            # Normal case: valid JSON content.
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                # Fallback extraction in case the model wraps JSON.
                start = content.find("{")
                end = content.rfind("}")
                if start >= 0 and end > start:
                    return json.loads(content[start:end + 1])
                raise RuntimeError("Model response was not valid JSON.")

        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt >= attempts:
                body = ""
                try:
                    body = exc.read().decode("utf-8", errors="replace")
                except Exception:
                    pass
                raise RuntimeError(
                    f"Groq HTTP {exc.code}: {body[:500]}"
                ) from exc

            retry_after = exc.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                wait_seconds = max(30, int(retry_after))
            else:
                wait_seconds = 45 * attempt

            print(
                f"Groq rate limit reached (429). "
                f"Waiting {wait_seconds}s before retry {attempt + 1}/{attempts}..."
            )
            time.sleep(wait_seconds)

    raise RuntimeError("Groq request failed after retries.")

def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")[:80] or "research-note"


class _ReadableHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in {"script", "style", "nav", "header", "footer", "noscript", "svg"}:
            self.skip += 1

    def handle_endtag(self, tag):
        if tag.lower() in {"script", "style", "nav", "header", "footer", "noscript", "svg"} and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            value = " ".join(data.split())
            if value:
                self.parts.append(value)

    def text(self):
        return "\n".join(self.parts)


def unpaywall_locations(doi: str) -> list[dict[str, Any]]:
    doi = (doi or "").strip()
    if not doi:
        return []

    url = (
        "https://api.unpaywall.org/v2/"
        + urllib.parse.quote(doi, safe="")
        + "?email="
        + urllib.parse.quote(NCBI_EMAIL)
    )

    try:
        raw = http_request(
            url,
            headers={"User-Agent": "KetogenicResearch/FullTextDiscovery"},
            timeout=45,
        )
        data = json.loads(raw)
    except Exception as exc:
        print(f"Unpaywall lookup unavailable for DOI {doi}: {exc}")
        return []

    locations = []
    best = data.get("best_oa_location")
    if isinstance(best, dict):
        locations.append(best)

    for item in data.get("oa_locations") or []:
        if isinstance(item, dict) and item not in locations:
            locations.append(item)

    return locations


def extract_pdf_text(raw: bytes) -> str:
    try:
        from pypdf import PdfReader
    except Exception:
        return ""

    try:
        reader = PdfReader(BytesIO(raw))
        chunks = []
        for page in reader.pages[:80]:
            value = page.extract_text() or ""
            value = " ".join(value.split())
            if value:
                chunks.append(value)
            if sum(len(x) for x in chunks) >= 18000:
                break
        return "\n\n".join(chunks)[:18000]
    except Exception as exc:
        print(f"PDF text extraction failed: {exc}")
        return ""


def fetch_oa_location_text(location: dict[str, Any]) -> tuple[str, str]:
    pdf_url = (location.get("url_for_pdf") or "").strip()
    landing_url = (location.get("url_for_landing_page") or location.get("url") or "").strip()

    if pdf_url:
        try:
            raw = http_request(
                pdf_url,
                headers={
                    "User-Agent": "Mozilla/5.0 KetogenicResearch/FullTextDiscovery",
                    "Accept": "application/pdf,text/html;q=0.8,*/*;q=0.5",
                },
                timeout=75,
            )
            if raw[:4] == b"%PDF":
                text = extract_pdf_text(raw)
                if len(text) >= 3000:
                    return text[:18000], pdf_url
        except Exception as exc:
            print(f"OA PDF retrieval failed: {exc}")

    if landing_url:
        try:
            raw = http_request(
                landing_url,
                headers={
                    "User-Agent": "Mozilla/5.0 KetogenicResearch/FullTextDiscovery",
                    "Accept": "text/html,application/xhtml+xml,*/*;q=0.5",
                },
                timeout=75,
            )
            decoded = raw.decode("utf-8", errors="replace")
            parser = _ReadableHTML()
            parser.feed(decoded)
            value = parser.text()
            if len(value) >= 5000:
                return value[:18000], landing_url
        except Exception as exc:
            print(f"OA HTML retrieval failed: {exc}")

    return "", ""


def discover_full_text(
    rec: dict[str, Any],
    extra: dict[str, Any],
) -> tuple[str, str, str]:
    # 1. Prefer structured PMC/Europe-PMC-compatible full text when a PMCID exists.
    pmcid = (extra.get("pmcid") or "").strip()
    if pmcid:
        text = pmc_full_text(pmcid)
        if len(text) >= 3000:
            return text[:30000], "PMC full text", f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"

    # 2. Look for a legal OA copy registered by Unpaywall.
    doi = (rec.get("doi") or extra.get("doi_from_pubmed") or "").strip()
    for location in unpaywall_locations(doi):
        text, source_url = fetch_oa_location_text(location)
        if len(text) >= 3000:
            version = location.get("version") or "open-access version"
            host = location.get("host_type") or "open-access host"
            return text[:30000], f"Unpaywall OA ({host}, {version})", source_url

    # 3. Try the DOI landing page itself. This does not bypass paywalls:
    #    it only uses content that the publisher returns without authentication.
    doi = (rec.get("doi") or extra.get("doi_from_pubmed") or "").strip()
    if doi:
        doi_url = "https://doi.org/" + urllib.parse.quote(doi, safe="/().;:-_")
        try:
            raw = http_request(
                doi_url,
                headers={
                    "User-Agent": "Mozilla/5.0 KetogenicResearch/FullTextDiscovery",
                    "Accept": "text/html,application/xhtml+xml,application/pdf,*/*;q=0.5",
                },
                timeout=75,
            )

            if raw[:4] == b"%PDF":
                value = extract_pdf_text(raw)
                if len(value) >= 6000:
                    return value[:30000], "Publisher full text via DOI", doi_url
            else:
                decoded = raw.decode("utf-8", errors="replace")
                parser = _ReadableHTML()
                parser.feed(decoded)
                value = parser.text()

                # Be conservative: require substantial article-like text and
                # multiple scientific section signals before calling it full text.
                lower = value.lower()
                section_hits = sum(
                    marker in lower
                    for marker in (
                        "introduction",
                        "methods",
                        "materials and methods",
                        "results",
                        "discussion",
                        "conclusion",
                        "references",
                    )
                )
                if len(value) >= 9000 and section_hits >= 3:
                    return value[:30000], "Publisher full text via DOI", doi_url

        except Exception as exc:
            print(f"Publisher DOI full-text retrieval failed: {exc}")

    # 4. No usable full text was retrieved. This says nothing about whether
    #    a full text exists elsewhere; the note simply uses the PubMed abstract.
    return "", "PubMed abstract", ""


def source_packet(
    rec: dict[str, Any],
    extra: dict[str, Any],
    full_text: str,
    full_text_source: str = "",
    full_text_url: str = "",
) -> str:
    authors = ", ".join(rec.get("authors") or [])
    areas = ", ".join(rec.get("areas") or [])
    source_used = full_text_source or ("Full text" if full_text else "PubMed abstract")

    return f"""SOURCE MATERIAL USED: {source_used}
SOURCE URL: {full_text_url or "[not applicable]"}

PUBMED METADATA
PMID: {rec.get('pmid','')}
DOI: {rec.get('doi') or extra.get('doi_from_pubmed','')}
PMCID: {extra.get('pmcid','')}
Title: {rec.get('title','')}
Authors: {authors}
Journal: {rec.get('journal','')}
Publication date: {rec.get('date','')}
Evidence type: {rec.get('evidence_type','')}
Clinical areas: {areas}
MeSH: {", ".join(extra.get("mesh") or [])}

PUBMED ABSTRACT
{extra.get("abstract") or "[No abstract supplied by PubMed]"}

FULL-TEXT MATERIAL USED FOR THIS NOTE
{full_text or "[No full-text material was supplied; use the PubMed abstract only.]"}

SOURCE-HIERARCHY RULE
{("A usable full text is present. Treat the full text as the primary scientific source. "
  "Use the PubMed abstract only as a concise cross-check; do not describe evidence gaps "
  "in terms of what the abstract does or does not report.")
 if full_text else
 ("No usable full text was retrieved. The PubMed abstract is the only scientific content "
  "available in this packet.")}
""".strip()

def writer_prompt(packet: str, has_full_text: bool) -> str:
    article_type_en = "Research Analysis" if has_full_text else "Research Note"
    article_type_it = "Analisi di ricerca" if has_full_text else "Nota di ricerca"

    return f"""You are the scientific editorial writer for Ketogenic Research Hub.

Follow this policy exactly:
--- POLICY ---
{POLICY_TEXT}
--- END POLICY ---

Write one bilingual article based ONLY on the SOURCE PACKET.
Do not add background facts that are not explicitly present in the source.

READER-FIRST EDITORIAL TRANSFORMATION — V4.1

The published article must NOT read like a translated, expanded, or reordered abstract.

Treat the source as evidence to interpret, not as prose to reproduce.

- Do not follow the abstract's sentence order.
- Do not mirror the sequence Objective → Methods → Results → Conclusion unless it is genuinely the clearest way to explain the study.
- Do not paraphrase every sentence or every numerical result from the abstract.
- Select only the methodological details necessary to understand the credibility and meaning of the findings.
- Prefer one clear explanation of the central finding over several technically similar statements.
- Translate specialist terminology into precise but readable scientific language when this can be done without loss of meaning.
- Define an acronym only when it materially helps the reader; avoid dense acronym clusters.
- Avoid strings of percentages, p-values, biomarkers, genes, molecular targets, or subgroup statistics unless they are essential to interpretation.
- Keep the direct description of the study to roughly 20–30% of the article. The majority should explain what the findings mean, how confidently they can be interpreted, and what question remains unresolved.
- Interpretation must still remain strictly within what the supplied source supports. Do not invent external literature, mechanisms, prevalence estimates, clinical guidelines, or background facts.
- Write for clinicians, researchers, dietitians, and scientifically informed readers who may not be specialists in the paper's narrow subfield.
- If a technical term is unavoidable, explain its practical meaning in the same sentence or immediately after it.
- The article should sound like an experienced scientific editor explaining a paper to another professional, not like a manuscript abstract.
- Avoid redundant numerical precision. When several numbers express the same finding, retain the one or two that best convey magnitude.
- A methodological detail belongs in the article only if omitting it would change the interpretation of the result.
- Do not make "Clinical interpretation" a restatement of the results. It must answer: what does this result actually tell us, and what does it not tell us?
- Do not make "Limitations and open questions" a generic checklist. Include only limitations that materially affect confidence, applicability, or causality.
- End on the unresolved scientific question, not on a formulaic conclusion.

EDITORIAL RULES FOR V4.1

1. TITLE CAUTION
- Do not use causal or definitive verbs such as "improves", "enhances", "prevents",
  "reduces", "increases", "protects", "causes" in the title unless the supplied
  source itself clearly supports a causal conclusion and the study design justifies it.
- Prefer descriptive formulations such as:
  "was associated with", "was linked to", "showed higher", "showed lower",
  "findings from a randomized crossover trial", or equivalent neutral wording.
- For randomized trials, do not turn one experiment into a general clinical claim.

2. SOURCE-HIERARCHY AND ABSTRACT CAUTION
- Never state in the article body whether the note was based on an abstract, full text, PMC, publisher text, or any retrieval source.
- Source-acquisition details are internal metadata only and must not appear in reader-facing prose.
- Never mention AI, automation, workflow, model, generation process, or any technical production method in the published article.
- Describe only the scientific limitations of the study, not how the article was produced.
- When usable full text is supplied, treat it as the PRIMARY source and the PubMed abstract only as a cross-check.
- When usable full text is supplied, never write phrases such as "the abstract does not indicate", "the abstract does not report", "the abstract does not clarify", "dall'abstract non emerge", "l'abstract non indica", "l'abstract non riporta", or equivalent wording.
- If an issue is genuinely unresolved after checking the supplied full text, phrase it as a STUDY limitation: e.g. "the study does not establish...", "the study does not clarify...", "it remains uncertain whether...", or the natural Italian equivalent.
- Before stating that the study did not assess, report, clarify, or establish something, check the supplied Methods, Results, Discussion, Limitations and Conclusions material first.

3. STRUCTURE
For Research Notes, use exactly three sections.

English headings, once each and in this order:
- Study and findings
- Clinical interpretation
- Limitations and open questions

Italian headings, once each and in this order:
- Studio e risultati
- Interpretazione clinica
- Limiti e questioni aperte

Do not use a separate "Key finding" section in short Research Notes.
Integrate the principal result naturally into the opening paragraph or the first section.
Do not force every paragraph into the same length or rhetorical pattern.
Avoid repeating the same quantitative result in the summary and again in multiple sections.

For full-text Research Analyses, a more detailed structure is allowed when justified by the source.

3A. LENGTH AND DENSITY
- Prefer approximately 650–1000 words total across the English and Italian versions combined only if the source supports that amount of content; do not pad thin evidence.
- Keep paragraphs compact, usually 2–5 sentences.
- Avoid paragraphs that consist mainly of measurements, percentages, molecular labels, or methodological terminology.
- Do not repeat the same finding in the summary, first section, interpretation, and limitations.
- The summary should be editorial: 2–3 sentences explaining the question and the main finding, not a compressed abstract.
- In the first section, explain the study in plain scientific prose before giving technical detail.
- In the interpretation section, prioritize meaning over mechanics.
- In the limitations section, prioritize applicability and uncertainty over procedural minutiae.

4. ITALIAN QUALITY
- Use natural scientific Italian, not literal machine translation.
- Preserve technical terms when a forced Italian translation would be misleading.
- Do not translate "throughput" as "produttività" in performance-testing contexts.
  Prefer "prestazione complessiva", "rendimento operativo", or retain "throughput"
  with a short clarification when needed.
- Use "studio crossover randomizzato" rather than awkward alternatives.
- Keep numerical formatting appropriate for Italian prose, while preserving the exact values.

5. CLAIM DISCIPLINE
- Every quantitative claim must be present in the source packet.
- Distinguish what the study observed from what the authors concluded.
- Do not convert association into causation.
- Do not make clinical recommendations.
- Do not use promotional language.
- If the supplied source does not support a statement, omit it.
- Prefer wording such as "was associated with", "was linked to", "the study reported",
  "the authors found", "the pooled analysis showed", or "the results suggest".
- Avoid phrases such as "can improve", "can reduce", "improves", "reduces",
  "enhances", "protects", "prevents", or "causes" unless the supplied source
  explicitly supports that wording and the study design justifies it.
- In retrospective or observational studies, causal language is prohibited.


6. SCIENTIFIC AUTHOR STYLE
- Write as an experienced scientific author in clinical nutrition, metabolism, and ketogenic dietary therapy.
- The prose must be rigorous, current, documented, and suitable for healthcare professionals, while remaining understandable to an informed non-specialialist reader.
- Use a sober, authoritative scientific register without sounding artificially academic.
- Prefer short-to-medium sentences; split overloaded sentences while preserving logical continuity.
- Vary sentence length and paragraph rhythm naturally.
- Avoid mechanically regular paragraph structure and repetitive claim-explanation-conclusion patterns.
- Avoid stereotyped formulae unless genuinely necessary, including equivalents of:
  "emerge", "emerge clearly", "a picture emerges", "scenario", "overall",
  "in conclusion", "in summary", "it is important to emphasize",
  "it is worth noting", "a crucial aspect", "a key element", "in this context".
- Avoid journalistic, promotional, emphatic, or superlative language unsupported by data.
- Enter the scientific problem directly; avoid generic introductory padding.
- Use titled sections only when they improve readability, and avoid excessive subsectioning.
- Prefer continuous scientific narrative over bullet lists unless a list is genuinely functional.
- Do not repeat the same concept in introduction, interpretation, and conclusions with minor rewording.
- Competence should be conveyed through precision and interpretation, not ornate prose.

7. SCIENTIFIC INTERPRETATION
- Distinguish explicitly between experimental data, observational findings, clinical trials,
  reviews/meta-analyses, expert consensus, and pathophysiological hypotheses.
- Do not infer causality from association.
- Do not equate statistical significance with clinical relevance; consider effect size,
  study design, and population.
- Do not generalize animal or cellular findings to humans.
- If one group differs from control but not directly from the main comparator, do not present
  this as evidence of superiority.
- Highlight methodological limitations when they materially change interpretation.
- Explain physiological and clinical meaning when the supplied source supports it.
- Separate what the study demonstrates, what it suggests, and what remains hypothetical.
- Do not overstate conclusions beyond the study design.

8. KETOGENIC TERMINOLOGY
- Distinguish classical ketogenic diet, VLCKD/VLEKT, ketogenic low-carbohydrate diets,
  and generic high-fat diets.
- Never use "ketogenic diet" as an undifferentiated category when composition, energy intake,
  protein intake, or therapeutic purpose differs.
- When available in the source, report energy intake and macronutrient distribution.
- A high-fat diet is not automatically ketogenic, and a ketogenic diet must not be described
  merely as a high-fat diet.
- In obesity and VLCKD/VLEKT contexts, consider body composition, lean mass, protein intake,
  safety, concomitant medications, and quality of weight loss when the source provides such data.

9. CONCLUSIONS
- Conclusions must be proportional to evidence quality.
- Avoid generic endings such as "more research is needed" as the only closing statement.
- When possible from the source, specify what question remains open, what study design would
  address it, and what limitation prevents a stronger conclusion.
- For preliminary findings prefer wording such as:
  "supports the hypothesis", "is consistent with", "suggests a potential effect",
  "does not establish", "cannot distinguish between".
- Never use "proves" unless the design genuinely permits that level of causal inference.

10. SOURCE PRESENTATION
- Include only one concise source note in the article body.
- Do not repeat PMID, DOI, or PMCID in multiple places.
- Public page rendering will provide PubMed and DOI links separately.

10. FINAL SELF-CHECK
Before returning the draft, verify:
- scientific accuracy;
- terminology consistency;
- absence of redundancy;
- absence of claims stronger than the evidence;
- natural prose and varied syntax;
- smooth transitions between paragraphs;
- no stereotyped AI-like phrasing;
- source identifiers and citations are correct.

Return JSON with exactly these top-level keys:
article_type
article_type_it
title_en
title_it
summary_en
summary_it
sections_en
sections_it
source_note_en
source_note_it

sections_en and sections_it must be arrays of objects with:
heading
text

Set:
article_type = "{article_type_en}"
article_type_it = "{article_type_it}"

SOURCE PACKET:
{packet}
"""

def verifier_prompt(packet: str, draft: dict[str, Any]) -> str:
    return f"""You are a strict scientific fact checker and editorial quality controller.

Compare the DRAFT only against the SOURCE PACKET.

FACTUAL CHECKS
- Every quantitative claim must be supported by the supplied source.
- Study design and population must be described accurately.
- Do not allow unsupported causal claims.
- Do not allow unsupported clinical recommendations.
- Do not allow invented limitations.
- Do not allow external factual claims absent from the supplied source.
- PMID, DOI, PMCID and source status must be correct.
- Statistical significance must not be presented as clinical importance without support.

EDITORIAL CHECKS
- Prose must be natural, varied, sober and scientifically precise.
- Do not allow stereotyped filler, repetitive transitions, promotional wording, or journalistic emphasis.
- FAIL the draft if it reads primarily as a translated/paraphrased abstract rather than an editorial scientific article.
- FAIL the draft if it follows the source abstract sentence-by-sentence or reproduces Objective/Methods/Results/Conclusion mechanically.
- FAIL the draft if excessive methodological or molecular detail obscures the central finding.
- FAIL the draft if the Clinical interpretation section mostly repeats results instead of explaining their meaning and evidentiary limits.
- FAIL the draft if numerical detail is repeated without adding interpretive value.
- Prefer accessible scientific language when an equally accurate simpler formulation is possible.
- Ketogenic terminology must be specific when relevant.
- Conclusions must be proportional to study design and evidence quality.
- Do not repeat the same concept unnecessarily across sections.
- The reader-facing article must not mention whether the source used was an abstract, full text, PMC text, publisher text, Unpaywall, or any retrieval workflow.
- Source-acquisition details are internal metadata only.
- If the SOURCE PACKET contains usable full text, FAIL any draft that frames a scientific limitation as "the abstract does not indicate/report/clarify/show" or any equivalent English/Italian wording.
- When full text is available, limitations must be phrased as limitations or unresolved questions of the STUDY itself, after checking the supplied Methods, Results, Discussion, Limitations and Conclusions material.

STRUCTURE CHECKS FOR RESEARCH NOTES
For Research Notes, the English section headings must be exactly:
1. Study and findings
2. Clinical interpretation
3. Limitations and open questions

The Italian section headings must be exactly:
1. Studio e risultati
2. Interpretazione clinica
3. Limiti e questioni aperte

No duplicate section headings are allowed.

STRUCTURE CHECKS FOR FULL-TEXT RESEARCH ANALYSES
For Research Analyses, a more detailed structure is allowed when justified by the source.

SOURCE PRESENTATION
- Source identifiers must not be redundantly repeated in the article body.
- Public page rendering provides separate PubMed/DOI links.

Return JSON with exactly:
{{
  "verdict": "PASS" or "FAIL",
  "issues": ["..."],
  "unsupported_claims": ["..."]
}}

SOURCE PACKET:
{packet}

DRAFT:
{json.dumps(draft, ensure_ascii=False)}
"""

def markdown(
    rec: dict[str, Any],
    extra: dict[str, Any],
    draft: dict[str, Any],
    verified_at: str,
    full_text_source: str = "PubMed abstract",
    full_text_url: str = "",
) -> str:
    def sections(items: list[dict[str, str]]) -> str:
        blocks = []
        for item in items:
            heading = str(item.get("heading", "")).strip()
            text = str(item.get("text", "")).strip()
            if heading and text:
                blocks.append(f"## {heading}\n\n{text}")
        return "\n\n".join(blocks)

    pmid = rec.get("pmid", "")
    doi = rec.get("doi") or extra.get("doi_from_pubmed", "")
    pmcid = extra.get("pmcid", "")

    source_citation = format_citation(extra.get("citation_meta") or {})
    if not source_citation:
        raise RuntimeError(f"Unable to build authoritative PubMed citation for PMID {pmid}")
    return f"""---
pmid: {json.dumps(pmid)}
doi: {json.dumps(doi)}
pmcid: {json.dumps(pmcid)}
date: {json.dumps(rec.get("date",""))}
journal: {json.dumps(rec.get("journal",""), ensure_ascii=False)}
article_type: {json.dumps(draft.get("article_type",""))}
article_type_it: {json.dumps(draft.get("article_type_it",""))}
generator_version: "4.5"
source_identity: "PASS"
source_identity_basis: "PubMed PMID/title/DOI/PMCID"
full_text_source: {json.dumps(full_text_source)}
full_text_url: {json.dumps(full_text_url)}
editorial_byline: "Ketogenic Research Hub Editorial"
scientific_oversight_en: "Marco Medeot, Scientific Director"
scientific_oversight_it: "Marco Medeot, Direttore Scientifico"
verification: "PASS"
verified_at: {json.dumps(verified_at)}
---

# {draft.get("title_en","")}

**{draft.get("article_type","Research Note")}**

**Ketogenic Research Hub Editorial**  
Scientific oversight: **Marco Medeot, Scientific Director**

{draft.get("summary_en","")}

{sections(draft.get("sections_en") or [])}

### Source

{source_citation}

---

# {draft.get("title_it","")}

**{draft.get("article_type_it","Nota di ricerca")}**

**Ketogenic Research Hub Editorial**  
Supervisione scientifica: **Marco Medeot, Direttore Scientifico**

{draft.get("summary_it","")}

{sections(draft.get("sections_it") or [])}

### Fonte

{source_citation}

"""

def load_index() -> dict[str, Any]:
    if INDEX.exists():
        try:
            return json.loads(INDEX.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"generated_pmids": [], "failures": []}

def main() -> None:
    if not LATEST.exists():
        raise SystemExit("latest-publications.json not found.")
    if not GROQ_API_KEY:
        raise SystemExit("GROQ_API_KEY GitHub secret is required.")

    OUT.mkdir(exist_ok=True)

    latest = json.loads(LATEST.read_text(encoding="utf-8"))
    idx = load_index()
    done = set(str(x) for x in idx.get("generated_pmids", []))

    # MAX_ARTICLES remains the number of articles to PUBLISH per run.
    # We scan several candidates so an unusable first PMID cannot block the day.
    try:
        max_candidate_scan = max(
            MAX_ARTICLES,
            int(os.environ.get("MAX_CANDIDATE_SCAN", "12"))
        )
    except ValueError:
        max_candidate_scan = 12

    source_unavailable = set(
        str(x) for x in idx.get("source_unavailable_pmids", [])
    )

    publications = latest.get("publications", [])

    if TARGET_PMID:
        if not re.fullmatch(r"\d{6,9}", TARGET_PMID):
            raise SystemExit("TARGET_PMID must contain a valid numeric PMID.")

        target = next(
            (
                p for p in publications
                if str(p.get("pmid") or "") == TARGET_PMID
            ),
            None,
        )

        if target is None:
            raise SystemExit(
                f"TARGET_PMID {TARGET_PMID} is not present in latest-publications.json."
            )

        # Explicit regeneration takes precedence over the normal generated/
        # unavailable guards. Only this PMID is eligible in this run.
        done.discard(TARGET_PMID)
        source_unavailable.discard(TARGET_PMID)
        candidates = [target]
        print(f"Forced regeneration target: PMID {TARGET_PMID}")

    else:
        eligible = [
            p for p in publications
            if p.get("pmid")
            and str(p["pmid"]) not in done
            and str(p["pmid"]) not in source_unavailable
            and p.get("status") in {"new", "indexed"}
        ]

        # Prefer genuinely new records. If none of them can produce a
        # publishable article, fall back to still-unpublished indexed records.
        new_candidates = [p for p in eligible if p.get("status") == "new"]
        indexed_candidates = [p for p in eligible if p.get("status") == "indexed"]
        candidates = (new_candidates + indexed_candidates)[:max_candidate_scan]

    if not candidates:
        print("No eligible unpublished record available.")
        return

    published = 0
    attempted = 0

    for rec in candidates:
        if published >= MAX_ARTICLES:
            break

        attempted += 1
        pmid = str(rec["pmid"])
        print(
            f"Candidate {attempted}/{len(candidates)} "
            f"[{rec.get('status', 'unknown')}] — PMID {pmid}: "
            f"{rec.get('title', '')[:100]}"
        )

        try:
            pubmed = pubmed_xml(pmid)
            extra = extract_pubmed_source(pubmed)
            rec = verify_source_identity(rec, extra)

            if not extra.get("abstract"):
                if pmid not in source_unavailable:
                    idx.setdefault("failures", []).append({
                        "pmid": pmid,
                        "at": datetime.now(timezone.utc).isoformat(),
                        "stage": "source",
                        "error": "PubMed abstract unavailable",
                    })
                    source_unavailable.add(pmid)

                print(
                    f"Skipping PMID {pmid}: PubMed abstract unavailable. "
                    "Trying next candidate."
                )
                continue

            full_text, full_text_source, full_text_url = discover_full_text(rec, extra)
            packet = source_packet(
                rec,
                extra,
                full_text,
                full_text_source,
                full_text_url,
            )

            print("Generating bilingual article...")
            draft = groq_json(
                [
                    {
                        "role": "system",
                        "content": (
                            "Write only evidence-grounded scientific editorial content. "
                            "Return JSON only."
                        ),
                    },
                    {
                        "role": "user",
                        "content": writer_prompt(packet, bool(full_text)),
                    },
                ],
                max_tokens=2600,
                temperature=0.1,
            )

            print("Waiting before verification...")
            time.sleep(75)

            print("Verifying draft against source...")
            check = groq_json(
                [
                    {
                        "role": "system",
                        "content": (
                            "Act as a conservative scientific fact checker. "
                            "Return JSON only."
                        ),
                    },
                    {
                        "role": "user",
                        "content": verifier_prompt(packet, draft),
                    },
                ],
                max_tokens=700,
                temperature=0.0,
            )

            if str(check.get("verdict", "")).upper() != "PASS":
                idx.setdefault("failures", []).append({
                    "pmid": pmid,
                    "at": datetime.now(timezone.utc).isoformat(),
                    "stage": "verification",
                    "issues": check.get("issues", []),
                    "unsupported_claims": check.get("unsupported_claims", []),
                })
                print(
                    f"Verification FAILED for PMID {pmid}; "
                    "trying next candidate."
                )
                continue

            verified_at = datetime.now(timezone.utc).isoformat()
            date_prefix = (rec.get("date") or verified_at[:10])[:7]
            filename = (
                f"{date_prefix}-{pmid}-"
                f"{slugify(rec.get('title', ''))}.md"
            )

            (OUT / filename).write_text(
                markdown(
                    rec,
                    extra,
                    draft,
                    verified_at,
                    full_text_source,
                    full_text_url,
                ),
                encoding="utf-8",
            )

            done.add(pmid)
            published += 1
            print(f"Verified article created: {filename}")

        except Exception as exc:
            idx.setdefault("failures", []).append({
                "pmid": pmid,
                "at": datetime.now(timezone.utc).isoformat(),
                "stage": "generation",
                "error": str(exc),
            })
            print(
                f"Error for PMID {pmid}: {exc}. "
                "Trying next candidate."
            )
            continue

    idx["generated_pmids"] = sorted(done)
    idx["source_unavailable_pmids"] = sorted(source_unavailable)
    idx["updated_at"] = datetime.now(timezone.utc).isoformat()
    idx["last_run"] = {
        "attempted_candidates": attempted,
        "published_articles": published,
        "status": "published" if published else "no_article_published",
    }

    INDEX.write_text(
        json.dumps(idx, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    if published:
        print(
            f"ARTICLE PUBLISHED: {published} verified article(s) created "
            f"after checking {attempted} candidate(s)."
        )
    else:
        print(
            f"NO ARTICLE PUBLISHED: checked {attempted} candidate(s); "
            "none had sufficient source/verification quality."
        )

if __name__ == "__main__":
    main()
