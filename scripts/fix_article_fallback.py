#!/usr/bin/env python3
"""
Ketogenic Research — fix article fallback

Patches scripts/generate_articles.py so that a run still publishes at most ONE
verified article, but scans subsequent "new" PubMed records when a candidate:
- has no PubMed abstract;
- fails verification;
- raises a source/generation error.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "scripts" / "generate_articles.py"

NEW_MAIN = r"""def main() -> None:
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

    candidates = [
        p for p in latest.get("publications", [])
        if p.get("pmid")
        and str(p["pmid"]) not in done
        and p.get("status") == "new"
    ][:max_candidate_scan]

    if not candidates:
        print("No new eligible record for the pilot.")
        return

    published = 0
    attempted = 0
    source_unavailable = set(
        str(x) for x in idx.get("source_unavailable_pmids", [])
    )

    for rec in candidates:
        if published >= MAX_ARTICLES:
            break

        attempted += 1
        pmid = str(rec["pmid"])
        print(
            f"Candidate {attempted}/{len(candidates)} — PMID {pmid}: "
            f"{rec.get('title', '')[:100]}"
        )

        try:
            pubmed = pubmed_xml(pmid)
            extra = extract_pubmed_source(pubmed)

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
                markdown(rec, extra, draft, verified_at),
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
"""

def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f"Target not found: {TARGET}")

    text = TARGET.read_text(encoding="utf-8")

    text = text.replace(
        "# Pilot V2 deliberately handles only one new record per run.\nMAX_ARTICLES = 1",
        "# Publish at most one VERIFIED article per run; the fallback loop may scan multiple records.\nMAX_ARTICLES = 1",
    )

    pattern = re.compile(
        r'def main\(\) -> None:\n.*?(?=\nif __name__ == ["\']__main__["\']:\n)',
        re.DOTALL,
    )

    updated, count = pattern.subn(lambda _m: NEW_MAIN.rstrip() + "\n", text, count=1)
    if count != 1:
        raise SystemExit(
            "Could not locate the current main() block in scripts/generate_articles.py. "
            "No file was changed."
        )

    compile(updated, str(TARGET), "exec")

    if updated == text:
        print("generate_articles.py is already patched.")
        return

    TARGET.write_text(updated, encoding="utf-8")
    print("Patched scripts/generate_articles.py successfully.")
    print("New behavior: skip unusable PMID -> try next candidate -> publish first verified article.")

if __name__ == "__main__":
    main()
