# V40 — Automated Latest Evidence

This release adds an automated PubMed literature feed without changing the manually curated Scientific Library.

## Files added

- `latest.html` — public Latest Evidence page.
- `latest-publications.json` — generated literature feed.
- `scripts/update_latest.py` — PubMed / NCBI E-utilities updater.
- `.github/workflows/update-literature.yml` — daily GitHub Actions workflow.

## One-time GitHub setup

1. Upload the complete V40 contents to the repository root, preserving the `.github/workflows/` and `scripts/` folders.
2. In GitHub, open **Settings → Actions → General**.
3. Under **Workflow permissions**, allow **Read and write permissions** so the workflow can commit the updated JSON file.
4. Optional but recommended: create an NCBI API key and add it in **Settings → Secrets and variables → Actions → New repository secret** as `NCBI_API_KEY`.
5. Open the **Actions** tab, select **Update latest scientific literature**, then click **Run workflow** once.
6. After the workflow commits `latest-publications.json`, GitHub Pages will serve the updated feed from `latest.html`.

The workflow also runs every day at 03:17 UTC.

## Behaviour

- PubMed publication-date window: 90 days.
- Maximum visible records: 100.
- Records are deduplicated by PMID.
- Each paper can be assigned to multiple clinical areas.
- Papers first detected within 14 days receive a `New` badge.
- DOI and PubMed links are taken directly from PubMed XML.
- The automatic feed is intentionally separate from the curated Scientific Library.

## Tuning

Edit these environment values in `.github/workflows/update-literature.yml`:

- `WINDOW_DAYS`
- `MAX_RECORDS`

The clinical-area search terms are defined in `AREA_TERMS` inside `scripts/update_latest.py`.
