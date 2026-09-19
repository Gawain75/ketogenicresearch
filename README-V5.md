# Scientific Library V5

Files to replace/add in the repository:

- `scripts/update_latest.py` — replaces the current file.
- `scripts/library_v5.py` — new file.
- `.github/workflows/update-literature.yml` — replaces the current daily workflow.
- `.github/workflows/expand-scientific-library-v5.yml` — new weekly/manual workflow.
- `library-backfill-state.json` — new state file.

## What V5 does

1. Corrects evidence classification so clearly preclinical/animal randomized experiments are not labeled clinical RCTs.
2. Reconciles up to 50 old library cards per run with exact PubMed title matches and adds direct PMID/DOI/PMC links.
3. Backfills PubMed three publication years per run, starting with 2022–2024 and moving backwards.
4. Deduplicates by PMID, DOI, then normalized title.
5. Uses the existing area classifier and existing `promote_auto.py`.
6. Writes a machine-readable `library-v5-report.json`.
7. Persists progress in `library-backfill-state.json`.
8. Adds commit/rebase/push to the daily literature workflow.
9. Uses a shared GitHub Actions concurrency group for the daily and historical library writers.

## First run

After uploading/committing all files, run:

Actions → Expand Scientific Library V5 → Run workflow

The first run processes 2022–2024 and reconciles up to 50 older cards.

Do not run the old and V5 library workflows manually at the same time.
