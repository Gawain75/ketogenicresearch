#!/usr/bin/env python3
"""
Pilot generator for Ketogenic Research AI-assisted research articles.

Reads latest-publications.json, fetches PubMed abstracts and optional PMC full text,
generates bilingual Markdown drafts with Groq, then performs a second verification pass.

PILOT SAFETY:
- maximum PILOT_MAX_ARTICLES drafts per run (default 3)
- drafts go to articles-drafts/ only
- no public HTML page is modified
- records are tracked in articles-drafts/generated-index.json
"""

from __future__ import annotations

import json
import os
import re
import time
import html
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
MAX_ARTICLES = max(1, min(int(os.environ.get("PILOT_MAX_ARTICLES", "3")), 5))
NCBI_EMAIL = os.environ.get("NCBI_EMAIL", "info@ketogenicresearch.org").strip()
NCBI_API_KEY = os.environ.get("NCBI_API_KEY", "").strip()

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

POLICY_TEXT = (ROOT / "ARTICLE_EDITORIAL_POLICY.md").read_text(encoding="utf-8")

def request(url: str, data: bytes | None = None, headers: dict[str, str] | None = None, timeout: int = 45) -> bytes:
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

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
    return ET.fromstring(request(url))

def text_content(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return " ".join("".join(node.itertext()).split())

def extract_pubmed_source(root: ET.Element) -> dict[str, Any]:
    article = root.find(".//PubmedArticle")
    if article is None:
        return {}

    abstract_parts = []
    for a in article.findall(".//Abstract/AbstractText"):
        label = a.attrib.get("Label", "").strip()
        txt = text_content(a)
        if txt:
            abstract_parts.append(f"{label}: {txt}" if label else txt)

    ids = {}
    for node in article.findall(".//ArticleIdList/ArticleId"):
        kind = node.attrib.get("IdType", "").lower()
        val = text_content(node)
        if kind and val:
            ids[kind] = val

    mesh = []
    for node in article.findall(".//MeshHeading/DescriptorName"):
        val = text_content(node)
        if val:
            mesh.append(val)

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
        root = ET.fromstring(request(url))
    except Exception:
        return ""

    chunks: list[str] = []
    for tag in ("abstract", "sec"):
        for node in root.findall(f".//{tag}"):
            txt = text_content(node)
            if txt and len(txt) > 80:
                chunks.append(txt)

    cleaned = "\n\n".join(dict.fromkeys(chunks))
    # Keep the free-tier request modest and deterministic.
    return cleaned[:14000]

def groq(messages: list[dict[str, str]], max_tokens: int = 2500, temperature: float = 0.15) -> str:
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is missing.")

    payload = json.dumps({
        "model": GROQ_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }).encode("utf-8")

    raw = request(
        GROQ_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "KetogenicResearch/AI-Articles-Pilot",
        },
        timeout=90,
    )
    obj = json.loads(raw)
    return obj["choices"][0]["message"]["content"].strip()

def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")[:80] or "research-note"

def source_packet(rec: dict[str, Any], extra: dict[str, Any], full_text: str) -> str:
    authors = ", ".join(rec.get("authors") or [])
    areas = ", ".join(rec.get("areas") or [])
    abstract = extra.get("abstract", "")
    pmcid = extra.get("pmcid", "")
    access = "PMC FULL TEXT AVAILABLE" if full_text else "ABSTRACT ONLY"

    return f"""SOURCE ACCESS: {access}

PUBMED METADATA
PMID: {rec.get('pmid','')}
DOI: {rec.get('doi') or extra.get('doi_from_pubmed','')}
PMCID: {pmcid}
Title: {rec.get('title','')}
Authors: {authors}
Journal: {rec.get('journal','')}
Publication date: {rec.get('date','')}
Evidence type: {rec.get('evidence_type','')}
Clinical areas: {areas}
MeSH: {", ".join(extra.get("mesh") or [])}

PUBMED ABSTRACT
{abstract or "[No abstract supplied by PubMed]"}

PMC FULL-TEXT EXCERPT
{full_text or "[Not available to this workflow]"}
""".strip()

def writer_prompt(packet: str, has_full_text: bool) -> str:
    article_type = "Research Analysis" if has_full_text else "Research Note"
    return f"""You are the scientific editorial writer for Ketogenic Research.

Follow this editorial policy exactly:
--- POLICY ---
{POLICY_TEXT}
--- END POLICY ---

Write one bilingual {article_type} based ONLY on SOURCE PACKET below.
Do not use background knowledge that is not explicitly in the packet.
If information is absent, say it is not reported in the supplied source.

Return valid JSON only, with this exact schema:
{{
  "article_type": "{article_type}",
  "title_en": "...",
  "title_it": "...",
  "summary_en": "...",
  "summary_it": "...",
  "sections_en": [
    {{"heading":"Key finding","text":"..."}}
  ],
  "sections_it": [
    {{"heading":"Risultato principale","text":"..."}}
  ],
  "source_note_en": "...",
  "source_note_it": "..."
}}

For abstract-only records, keep each language concise (roughly 450-700 words total)
and explicitly state that the interpretation is based on the PubMed abstract.
For PMC full-text records, roughly 800-1200 words per language is acceptable.

SOURCE PACKET:
{packet}
"""

def parse_json_model_output(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
    raw = re.sub(r"\s*```$", "", raw)
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Model did not return a JSON object.")
    return json.loads(raw[start:end+1])

def verifier_prompt(packet: str, draft: dict[str, Any]) -> str:
    return f"""You are a strict scientific fact checker.

Compare the DRAFT only against the SOURCE PACKET. Apply these rules:
- Every number and quantitative claim must be in the source.
- Study design and population must match the source.
- No unsupported causal statement.
- No unsupported clinical recommendation.
- No invented limitation.
- No external facts or background knowledge.
- PMID/DOI/source status must be correct.
- If only an abstract is supplied, the draft must explicitly disclose that limitation.

Return valid JSON only:
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

def markdown(rec: dict[str, Any], extra: dict[str, Any], draft: dict[str, Any], verified_at: str) -> str:
    def section_block(items: list[dict[str, str]]) -> str:
        blocks = []
        for s in items:
            heading = str(s.get("heading", "")).strip()
            text = str(s.get("text", "")).strip()
            if heading and text:
                blocks.append(f"## {heading}\n\n{text}")
        return "\n\n".join(blocks)

    pmid = rec.get("pmid", "")
    doi = rec.get("doi") or extra.get("doi_from_pubmed", "")
    pmcid = extra.get("pmcid", "")
    front = {
        "pmid": pmid,
        "doi": doi,
        "pmcid": pmcid,
        "date": rec.get("date", ""),
        "journal": rec.get("journal", ""),
        "article_type": draft.get("article_type", ""),
        "verification": "PASS",
        "verified_at": verified_at,
    }

    meta = "\n".join(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in front.items())

    return f"""---
{meta}
---

# {draft.get("title_en","")}

{draft.get("summary_en","")}

{section_block(draft.get("sections_en") or [])}

### Source

{draft.get("source_note_en","")}

PMID: {pmid}  
DOI: {doi or "Not available"}  
PMCID: {pmcid or "Not available"}

---

# {draft.get("title_it","")}

{draft.get("summary_it","")}

{section_block(draft.get("sections_it") or [])}

### Fonte

{draft.get("source_note_it","")}

PMID: {pmid}  
DOI: {doi or "Non disponibile"}  
PMCID: {pmcid or "Non disponibile"}
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
        print("No new eligible records for the pilot.")
        return

    generated = 0
    for rec in candidates:
        pmid = str(rec["pmid"])
        print(f"Processing PMID {pmid}: {rec.get('title','')[:90]}")

        try:
            px = pubmed_xml(pmid)
            extra = extract_pubmed_source(px)
            if not extra.get("abstract"):
                raise RuntimeError("PubMed abstract unavailable; pilot skips this record.")

            full_text = pmc_full_text(extra.get("pmcid", ""))
            packet = source_packet(rec, extra, full_text)

            raw_draft = groq([
                {"role": "system", "content": "Write only evidence-grounded scientific editorial content."},
                {"role": "user", "content": writer_prompt(packet, bool(full_text))}
            ], max_tokens=3200, temperature=0.12)
            draft = parse_json_model_output(raw_draft)

            # Space calls to make pilot friendlier to free-tier token/rate limits.
            time.sleep(12)

            raw_check = groq([
                {"role": "system", "content": "Act as a conservative scientific fact checker. Return JSON only."},
                {"role": "user", "content": verifier_prompt(packet, draft)}
            ], max_tokens=900, temperature=0.0)
            check = parse_json_model_output(raw_check)

            if check.get("verdict") != "PASS":
                idx.setdefault("failures", []).append({
                    "pmid": pmid,
                    "at": datetime.now(timezone.utc).isoformat(),
                    "issues": check.get("issues", []),
                    "unsupported_claims": check.get("unsupported_claims", []),
                })
                print(f"Verification FAILED for PMID {pmid}; not writing draft.")
                continue

            verified_at = datetime.now(timezone.utc).isoformat()
            date_prefix = (rec.get("date") or verified_at[:10])[:7]
            filename = f"{date_prefix}-{pmid}-{slugify(rec.get('title',''))}.md"
            (OUT / filename).write_text(
                markdown(rec, extra, draft, verified_at),
                encoding="utf-8"
            )
            done.add(pmid)
            generated += 1
            print(f"Generated verified draft: {filename}")

        except Exception as exc:
            idx.setdefault("failures", []).append({
                "pmid": pmid,
                "at": datetime.now(timezone.utc).isoformat(),
                "error": str(exc),
            })
            print(f"Skipped PMID {pmid}: {exc}")

        time.sleep(4)

    idx["generated_pmids"] = sorted(done)
    idx["updated_at"] = datetime.now(timezone.utc).isoformat()
    INDEX.write_text(json.dumps(idx, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Pilot complete. Verified drafts generated: {generated}")

if __name__ == "__main__":
    main()
