# DOI Guard

Replace/add these files:

- `scripts/pubmed_record_guard.py` — new
- `scripts/promote_auto.py` — replace current daily promoter
- `scripts/promote_auto_v5.py` — replace current V5.1 promoter
- `.github/workflows/update-literature.yml` — replace current daily workflow
- `.github/workflows/expand-scientific-library-v5_1.yml` — replace current V5.1 workflow

Every publication is now re-fetched from PubMed by PMID immediately before promotion.
The public DOI is taken ONLY from `PubmedData/ArticleIdList` of that same PMID.
Queue DOI/DOI URL values are ignored and overwritten.
If PubMed has no DOI, no DOI link is published.
If the queue title does not exactly match the PubMed title after normalization, the record is not promoted.
