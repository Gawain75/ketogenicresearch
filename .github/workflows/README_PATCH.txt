Patch based on ketogenicresearch-main (8).zip

Purpose:
- leave ONE automatic "Generate research article":
  generate-articles-auto-v112.yml
- leave ONE scheduled "Update latest scientific literature":
  update-literature.yml
- leave ONE scheduled Scientific Library expansion:
  expand-scientific-library-v5_1-doi-guard.yml
- keep older variants available only for manual runs
- correct maintain-obesity-glp1-keto workflow_run target

Apply:
Extract this ZIP in the repository root and overwrite existing files.
Then commit/push once.

Expected result in GitHub Actions:
- Generate research article: only the v112 workflow auto-triggers
- Update latest scientific literature: only update-literature.yml is scheduled
- Expand Scientific Library V5.1 DOI Guard: only scheduled Library expansion
- old variants are labelled LEGACY and manual only
