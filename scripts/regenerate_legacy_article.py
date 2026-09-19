#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DRAFTS = ROOT / "articles-drafts"
LATEST = ROOT / "latest-publications.json"
GENERATOR = ROOT / "scripts" / "generate_articles.py"

def load_generator():
    spec = importlib.util.spec_from_file_location("kr_generate_articles", GENERATOR)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load scripts/generate_articles.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def parse_meta(text: str) -> dict:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}
    meta = {}
    for line in text[4:end].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        try:
            meta[key] = json.loads(value)
        except Exception:
            meta[key] = value.strip('"')
    return meta

def is_legacy(text: str) -> bool:
    # Old Research Notes used the five-section structure.
    legacy_markers = [
        "## Key finding",
        "## Study design",
        "## Main results",
        "## Risultato chiave",
        "## Disegno dello studio",
        "## Risultati principali",
    ]
    new_markers = [
        "## Study and findings",
        "## Clinical interpretation",
        "## Limitations and open questions",
        "## Studio e risultati",
        "## Interpretazione clinica",
        "## Limiti e questioni aperte",
    ]
    return any(m in text for m in legacy_markers) and not any(m in text for m in new_markers)

def main():
    ga = load_generator()

    latest = json.loads(LATEST.read_text(encoding="utf-8"))
    records = {
        str(p.get("pmid")): p
        for p in latest.get("publications", [])
        if p.get("pmid")
    }

    legacy = []
    for path in sorted(DRAFTS.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        if not is_legacy(text):
            continue
        meta = parse_meta(text)
        pmid = str(meta.get("pmid", "")).strip()
        if pmid:
            legacy.append((path, pmid))

    if not legacy:
        print("No legacy articles require regeneration.")
        return

    # One article per run to stay friendly to free-tier rate limits.
    path, pmid = legacy[0]
    rec = records.get(pmid)

    if not rec:
        raise RuntimeError(
            f"PMID {pmid} is not present in latest-publications.json. "
            "Regeneration was not attempted."
        )

    print(f"Regenerating legacy article PMID {pmid}: {path.name}")

    pubmed = ga.pubmed_xml(pmid)
    extra = ga.extract_pubmed_source(pubmed)

    if not extra.get("abstract"):
        raise RuntimeError("PubMed abstract unavailable; article not regenerated.")

    full_text = ga.pmc_full_text(extra.get("pmcid", ""))
    packet = ga.source_packet(rec, extra, full_text)

    print("Generating V3.5 article...")
    draft = ga.groq_json(
        [
            {
                "role": "system",
                "content": (
                    "Write evidence-grounded scientific editorial content "
                    "with natural expert prose. Return JSON only."
                ),
            },
            {
                "role": "user",
                "content": ga.writer_prompt(packet, bool(full_text)),
            },
        ],
        max_tokens=2800,
        temperature=0.18,
    )

    print("Waiting before verification...")
    time.sleep(75)

    print("Verifying regenerated article...")
    check = ga.groq_json(
        [
            {
                "role": "system",
                "content": (
                    "Act as a conservative scientific fact checker and "
                    "editorial quality controller. Return JSON only."
                ),
            },
            {
                "role": "user",
                "content": ga.verifier_prompt(packet, draft),
            },
        ],
        max_tokens=900,
        temperature=0.0,
    )

    if str(check.get("verdict", "")).upper() != "PASS":
        print("Regenerated article FAILED verification. Existing article was left unchanged.")
        print(json.dumps(check, ensure_ascii=False, indent=2))
        return

    verified_at = datetime.now(timezone.utc).isoformat()
    new_text = ga.markdown(rec, extra, draft, verified_at)

    # Overwrite only after PASS.
    path.write_text(new_text, encoding="utf-8")
    print(f"Regenerated and replaced: {path.name}")
    print("Run this workflow again to regenerate the next legacy article.")

if __name__ == "__main__":
    main()
