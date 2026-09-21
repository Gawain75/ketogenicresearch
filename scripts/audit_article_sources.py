#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from pubmed_record_guard import fetch_pubmed_records, norm_doi, norm_title

ROOT = Path(__file__).resolve().parents[1]
DRAFTS = ROOT / "articles-drafts"
PUBLIC = ROOT / "articles"
QUARANTINE = ROOT / "articles-quarantine"
INDEX = DRAFTS / "generated-index.json"
LATEST = ROOT / "latest-publications.json"
QUEUE = ROOT / "review-queue.json"


def parse_frontmatter(text: str):
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}, text
    raw, body = text[4:end], text[end + 5:]
    meta = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        try:
            meta[k.strip()] = json.loads(v.strip())
        except Exception:
            meta[k.strip()] = v.strip().strip('"')
    return meta, body


def set_frontmatter_value(text: str, key: str, value: str) -> str:
    encoded = json.dumps(value, ensure_ascii=False)
    pattern = re.compile(rf"(?m)^{re.escape(key)}:\s*.*$")
    if pattern.search(text):
        return pattern.sub(f"{key}: {encoded}", text, count=1)
    end = text.find("\n---\n", 4)
    if end < 0:
        return text
    return text[:end] + f"\n{key}: {encoded}" + text[end:]


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def fix_json_record(record: dict, auth: dict):
    record["doi"] = auth.get("doi") or ""
    record["pmc"] = auth.get("pmcid") or ""
    record["pubmed_url"] = auth.get("pubmed_url") or ""
    record["doi_url"] = auth.get("doi_url") or ""
    record["pmc_url"] = auth.get("pmc_url") or ""


def main() -> None:
    drafts = list(DRAFTS.glob("*.md"))
    pmids = []
    parsed = {}
    for path in drafts:
        meta, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
        pmid = str(meta.get("pmid") or "").strip()
        if pmid:
            pmids.append(pmid)
            parsed[path] = meta

    if not pmids:
        print("No generated article drafts to audit.")
        return

    authoritative = fetch_pubmed_records(pmids)
    latest = load_json(LATEST, {"publications": []})
    queue = load_json(QUEUE, {"records": []})
    local_records = {}
    for obj, key in ((latest, "publications"), (queue, "records")):
        for rec in obj.get(key, []):
            pmid = str(rec.get("pmid") or "").strip()
            if pmid:
                local_records.setdefault(pmid, rec)

    idx = load_json(INDEX, {"generated_pmids": [], "failures": []})
    done = {str(x) for x in idx.get("generated_pmids", [])}
    QUARANTINE.mkdir(exist_ok=True)
    bad = []
    passed = 0
    checked_at = datetime.now(timezone.utc).isoformat()

    for path, meta in parsed.items():
        pmid = str(meta.get("pmid") or "").strip()
        auth = authoritative.get(pmid)
        reasons = []
        if not auth:
            raise RuntimeError(f"PubMed did not return authoritative record for generated PMID {pmid}")

        local_rec = local_records.get(pmid)
        if local_rec and norm_title(local_rec.get("title") or "") != auth.get("title_norm"):
            reasons.append("stored source title does not match PubMed")

        draft_doi = norm_doi(str(meta.get("doi") or ""))
        auth_doi = norm_doi(str(auth.get("doi") or ""))
        draft_pmc = str(meta.get("pmcid") or "").strip()
        auth_pmc = str(auth.get("pmcid") or "").strip()

        # Missing local identifiers can legitimately be filled in later by PubMed.
        # A non-empty identifier that disagrees with PubMed is a source-identity failure.
        if draft_doi and draft_doi != auth_doi:
            reasons.append(f"DOI mismatch ({draft_doi} != {auth_doi or '[none]'})")
        if draft_pmc and draft_pmc != auth_pmc:
            reasons.append(f"PMCID mismatch ({draft_pmc} != {auth_pmc or '[none]'})")

        # Always repair latest/queue bibliographic identifiers from PubMed.
        for obj, key in ((latest, "publications"), (queue, "records")):
            for rec in obj.get(key, []):
                if str(rec.get("pmid") or "").strip() == pmid:
                    fix_json_record(rec, auth)

        if reasons:
            target = QUARANTINE / path.name
            shutil.move(str(path), str(target))
            public = PUBLIC / f"{path.stem}.html"
            if public.exists():
                public.unlink()
            done.discard(pmid)
            idx.setdefault("failures", []).append({
                "pmid": pmid,
                "at": checked_at,
                "stage": "source_identity_audit",
                "error": "; ".join(reasons),
            })
            bad.append((pmid, reasons))
            print(f"QUARANTINED PMID {pmid}: {'; '.join(reasons)}")
            continue

        text = path.read_text(encoding="utf-8")
        text = set_frontmatter_value(text, "source_identity", "PASS")
        text = set_frontmatter_value(text, "source_identity_checked_at", checked_at)
        text = set_frontmatter_value(text, "doi", auth_doi)
        text = set_frontmatter_value(text, "pmcid", auth_pmc)
        path.write_text(text, encoding="utf-8")
        passed += 1

    idx["generated_pmids"] = sorted(done)
    idx["updated_at"] = checked_at
    # Keep the diagnostic history bounded.
    idx["failures"] = idx.get("failures", [])[-100:]
    INDEX.write_text(json.dumps(idx, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    LATEST.write_text(json.dumps(latest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    QUEUE.write_text(json.dumps(queue, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Source identity audit complete: {passed} passed; {len(bad)} quarantined.")


if __name__ == "__main__":
    main()
