#!/usr/bin/env python3
"""
Ketogenic Research — AI article pilot V3.6

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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LATEST = ROOT / "latest-publications.json"
OUT = ROOT / "articles-drafts"
INDEX = OUT / "generated-index.json"

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b").strip()
NCBI_EMAIL = os.environ.get("NCBI_EMAIL", "info@ketogenicresearch.org").strip()
NCBI_API_KEY = os.environ.get("NCBI_API_KEY", "").strip()

# Pilot V2 deliberately handles only one new record per run.
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

def extract_pubmed_source(root: ET.Element) -> dict[str, Any]:
    article = root.find(".//PubmedArticle")
    if article is None:
        return {}

    abstract_parts = []
    for node in article.findall(".//Abstract/AbstractText"):
        label = node.attrib.get("Label", "").strip()
        text = text_content(node)
        if text:
            abstract_parts.append(f"{label}: {text}" if label else text)

    ids: dict[str, str] = {}
    for node in article.findall(".//ArticleIdList/ArticleId"):
        kind = node.attrib.get("IdType", "").lower()
        value = text_content(node)
        if kind and value:
            ids[kind] = value

    mesh = []
    for node in article.findall(".//MeshHeading/DescriptorName"):
        value = text_content(node)
        if value:
            mesh.append(value)

    return {
        "abstract": "\n".join(abstract_parts).strip(),
        "pmcid": ids.get("pmc", ""),
        "doi_from_pubmed": ids.get("doi", ""),
        "mesh": mesh[:30],
    }

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

    chunks: list[str] = []
    for tag in ("abstract", "sec"):
        for node in root.findall(f".//{tag}"):
            value = text_content(node)
            if value and len(value) > 80:
                chunks.append(value)

    # Keep prompt size moderate for free-tier use.
    return "\n\n".join(dict.fromkeys(chunks))[:10000]

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

def source_packet(
    rec: dict[str, Any],
    extra: dict[str, Any],
    full_text: str
) -> str:
    authors = ", ".join(rec.get("authors") or [])
    areas = ", ".join(rec.get("areas") or [])
    access = "PMC FULL TEXT USED" if full_text else "PUBMED ABSTRACT USED"

    return f"""SOURCE ACCESS: {access}

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

PMC FULL-TEXT EXCERPT
{full_text or "[Not available to this workflow]"}
""".strip()

def writer_prompt(packet: str, has_full_text: bool) -> str:
    article_type_en = "Research Analysis" if has_full_text else "Research Note"
    article_type_it = "Analisi di ricerca" if has_full_text else "Nota di ricerca"

    return f"""You are the scientific editorial writer for Ketogenic Research.

Follow this policy exactly:
--- POLICY ---
{POLICY_TEXT}
--- END POLICY ---

Write one bilingual article based ONLY on the SOURCE PACKET.
Do not add background facts that are not explicitly present in the source.

EDITORIAL RULES FOR V3

1. TITLE CAUTION
- Do not use causal or definitive verbs such as "improves", "enhances", "prevents",
  "reduces", "increases", "protects", "causes" in the title unless the supplied
  source itself clearly supports a causal conclusion and the study design justifies it.
- Prefer descriptive formulations such as:
  "was associated with", "was linked to", "showed higher", "showed lower",
  "findings from a randomized crossover trial", or equivalent neutral wording.
- For randomized trials, do not turn one experiment into a general clinical claim.

2. ABSTRACT-ONLY CAUTION
- Never mention AI, automation, workflow, model, generation process, or any technical production method in the published article.
- Describe only the source limitations, not how the article was produced.
- If no PMC full text was supplied to the model, the English article MUST include this exact sentence verbatim:
  "This note is based on the PubMed abstract."
- If no PMC full text was supplied to the model, the Italian article MUST include this exact sentence verbatim:
  "Questa nota si basa sull'abstract di PubMed."
- These sentences describe the source material used for the note. Do not state that a full text does not exist or is unavailable elsewhere.

3. STRUCTURE
For abstract-only Research Notes, use exactly three sections.

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
- every number is supported;
- study design is correct;
- population is correct;
- no unsupported causal claim;
- no unsupported clinical recommendation;
- no invented limitation;
- no external factual claims;
- PMID/DOI/source status are correct;
- abstract-only status is clearly disclosed when applicable.

EDITORIAL CHECKS
- never state or imply that the full text is globally unavailable merely because no PMC full text was supplied;
- when only the PubMed abstract was supplied, describe the note as abstract-based without making claims about publisher availability;
- for abstract-only Research Notes, English headings are exactly: Study and findings; Clinical interpretation; Limitations and open questions;
- for abstract-only Research Notes, Italian headings are exactly: Studio e risultati; Interpretazione clinica; Limiti e questioni aperte;
- no duplicate section headings;
- source identifiers are not redundantly repeated in the article body;
- prose is natural, varied, and not mechanically patterned;
- no stereotyped AI-like filler or formulaic transitions;
- no promotional, journalistic, or unnecessarily emphatic wording;
- ketogenic terminology is specific and not used as an undifferentiated category;
- statistical significance is not presented as clinical importance without support;
- conclusions are proportional to study design and evidence quality;
- there are no redundant repetitions of the same concept across sections;
- the article contains no mention of AI, automation, workflow, model, generation process, or technical production method;
- if the source is abstract-only, the English draft contains exactly:
  "This note is based on the PubMed abstract."
- if the source is abstract-only, the Italian draft contains exactly:
  "Questa nota si basa sull'abstract di PubMed."
- the article contains no mention of AI, automation, workflow, model, generation process, or technical production method;
- titles are descriptive rather than overstated;
- no section heading is duplicated;
- English section headings are exactly:
  Key finding
  Study design
  Main results
  Cautious interpretation
  Limitations of this note
- Italian section headings are exactly:
  Risultato chiave
  Disegno dello studio
  Risultati principali
  Interpretazione cauta
  Limiti della nota
- the Italian is natural scientific Italian, not a literal or awkward translation;
- "throughput" is not translated as "produttività" in a performance-testing context;
- wording distinguishes observed findings from authors' interpretation;
- abstract-only notes do not imply review of the full paper.

If any factual or editorial check fails, verdict must be FAIL.

Return JSON with exactly:
verdict
issues
unsupported_claims

verdict must be PASS or FAIL.
issues and unsupported_claims must be arrays of strings.

SOURCE PACKET:
{packet}

DRAFT:
{json.dumps(draft, ensure_ascii=False)}
"""

def markdown(
    rec: dict[str, Any],
    extra: dict[str, Any],
    draft: dict[str, Any],
    verified_at: str
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

    return f"""---
pmid: {json.dumps(pmid)}
doi: {json.dumps(doi)}
pmcid: {json.dumps(pmcid)}
date: {json.dumps(rec.get("date",""))}
journal: {json.dumps(rec.get("journal",""), ensure_ascii=False)}
article_type: {json.dumps(draft.get("article_type",""))}
article_type_it: {json.dumps(draft.get("article_type_it",""))}
editorial_byline: "Ketogenic Research Editorial"
scientific_oversight_en: "Marco Medeot, Scientific Director"
scientific_oversight_it: "Marco Medeot, Direttore Scientifico"
verification: "PASS"
verified_at: {json.dumps(verified_at)}
---

# {draft.get("title_en","")}

**{draft.get("article_type","Research Note")}**

**Ketogenic Research Editorial**  
Scientific oversight: **Marco Medeot, Scientific Director**

{draft.get("summary_en","")}

{sections(draft.get("sections_en") or [])}

### Source

{draft.get("source_note_en","")}

---

# {draft.get("title_it","")}

**{draft.get("article_type_it","Nota di ricerca")}**

**Ketogenic Research Editorial**  
Supervisione scientifica: **Marco Medeot, Direttore Scientifico**

{draft.get("summary_it","")}

{sections(draft.get("sections_it") or [])}

### Fonte

{draft.get("source_note_it","")}

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

    candidates = [
        p for p in latest.get("publications", [])
        if p.get("pmid")
        and str(p["pmid"]) not in done
        and p.get("status") == "new"
    ][:MAX_ARTICLES]

    if not candidates:
        print("No new eligible record for the pilot.")
        return

    rec = candidates[0]
    pmid = str(rec["pmid"])

    print(f"Processing PMID {pmid}: {rec.get('title','')[:100]}")

    try:
        pubmed = pubmed_xml(pmid)
        extra = extract_pubmed_source(pubmed)

        if not extra.get("abstract"):
            raise RuntimeError(
                "PubMed abstract unavailable; pilot skips this record."
            )

        full_text = pmc_full_text(extra.get("pmcid", ""))
        packet = source_packet(rec, extra, full_text)

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

        # Give the free tier time before the verification request.
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
            print("Verification FAILED; no article file created.")
        else:
            verified_at = datetime.now(timezone.utc).isoformat()
            date_prefix = (rec.get("date") or verified_at[:10])[:7]
            filename = (
                f"{date_prefix}-{pmid}-"
                f"{slugify(rec.get('title',''))}.md"
            )

            (OUT / filename).write_text(
                markdown(rec, extra, draft, verified_at),
                encoding="utf-8",
            )

            done.add(pmid)
            print(f"Verified article created: {filename}")

    except Exception as exc:
        idx.setdefault("failures", []).append({
            "pmid": pmid,
            "at": datetime.now(timezone.utc).isoformat(),
            "stage": "generation",
            "error": str(exc),
        })
        print(f"Pilot error for PMID {pmid}: {exc}")

    idx["generated_pmids"] = sorted(done)
    idx["updated_at"] = datetime.now(timezone.utc).isoformat()

    INDEX.write_text(
        json.dumps(idx, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

if __name__ == "__main__":
    main()
