#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DRAFTS = ROOT / "articles-drafts"
LATEST = ROOT / "latest-publications.json"
GENERATOR = ROOT / "scripts" / "generate_articles.py"

TARGET_VERSION = "4.1"
MAX_REGEN = max(1, min(int(os.environ.get("MAX_REGEN_ARTICLES", "4")), 10))

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

def main():
    ga = load_generator()
    latest = json.loads(LATEST.read_text(encoding="utf-8"))
    records = {
        str(p.get("pmid")): p
        for p in latest.get("publications", [])
        if p.get("pmid")
    }

    pending = []
    for path in sorted(DRAFTS.glob("*.md")):
        meta = parse_meta(path.read_text(encoding="utf-8"))
        pmid = str(meta.get("pmid", "")).strip()
        version = str(meta.get("generator_version", "")).strip()
        if pmid and version != TARGET_VERSION:
            pending.append((path, pmid))

    if not pending:
        print("All article drafts are already on generator version 4.1.")
        return

    pending = pending[:MAX_REGEN]
    print(f"Articles selected for regeneration: {len(pending)}")

    changed = 0

    for index, (path, pmid) in enumerate(pending, start=1):
        rec = records.get(pmid)
        if not rec:
            print(f"[{index}] Skip PMID {pmid}: not present in latest-publications.json")
            continue

        print(f"[{index}] Regenerating PMID {pmid}: {path.name}")

        try:
            pubmed = ga.pubmed_xml(pmid)
            extra = ga.extract_pubmed_source(pubmed)

            if not extra.get("abstract"):
                print(f"[{index}] Skip PMID {pmid}: PubMed abstract unavailable")
                continue

            full_text, source_name, source_url = ga.discover_full_text(rec, extra)
            print(f"[{index}] Source material selected: {source_name}")
            if source_url:
                print(f"[{index}] Source URL: {source_url}")

            packet = ga.source_packet(
                rec,
                extra,
                full_text,
                source_name,
                source_url,
            )

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

            print(f"[{index}] Waiting before verification...")
            time.sleep(75)

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
                print(f"[{index}] Verification FAILED for PMID {pmid}; old article kept.")
                print(json.dumps(check, ensure_ascii=False))
            else:
                verified_at = datetime.now(timezone.utc).isoformat()
                path.write_text(
                    ga.markdown(rec, extra, draft, verified_at),
                    encoding="utf-8",
                )
                changed += 1
                print(f"[{index}] Replaced with V4.1: {path.name}")

        except Exception as exc:
            print(f"[{index}] Error for PMID {pmid}: {exc}")

        if index < len(pending):
            print("Waiting before next article...")
            time.sleep(90)

    print(f"Regenerated articles committed this run: {changed}")
    remaining = max(0, len([
        p for p in DRAFTS.glob("*.md")
        if str(parse_meta(p.read_text(encoding="utf-8")).get("generator_version", "")).strip() != TARGET_VERSION
    ]))
    print(f"Articles still requiring V4.1 regeneration: {remaining}")

if __name__ == "__main__":
    main()
