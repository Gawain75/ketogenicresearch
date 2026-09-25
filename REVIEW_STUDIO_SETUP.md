# Review Studio MVP — setup

This patch adds a private `/review-studio` workspace to Ketogenic Research Hub.

## What the MVP does

- starts from a free-text scientific question;
- generates an editable PICO/PECO-style protocol draft;
- freezes the protocol before screening;
- searches PubMed from the approved query;
- records Include / Exclude / Uncertain decisions;
- builds basic PRISMA-style counts;
- provides a validated quantitative extraction table;
- performs a deterministic continuous-outcome mean-difference meta-analysis:
  - fixed effect;
  - DerSimonian–Laird random effects;
  - Q;
  - I²;
  - τ²;
  - 95% CI;
  - forest plot;
- generates a manuscript draft only from the frozen protocol, included study metadata,
  investigator-validated extraction table and calculated meta-analysis results;
- exports the complete project as JSON and the extraction table as CSV.

## Security

`review-studio` and `/api/review/*` are protected by the existing Supabase login plus
an administrator email allow-list in Cloudflare.

Set this Cloudflare Pages/Workers environment variable:

`REVIEW_ADMIN_EMAILS`

Example:

`your-admin-login@example.com`

For more than one administrator, use a comma-separated list.

## AI service

The protocol and manuscript draft endpoints require:

`GROQ_API_KEY`

Optional:

`GROQ_MODEL=openai/gpt-oss-120b`

The key must be configured as a Cloudflare secret/environment variable. It is never
sent to the browser.

## PubMed

PubMed search works without an NCBI key. For a higher rate limit you can also set:

`NCBI_API_KEY`

## Installation

Copy these files to the repository root, replacing `_worker.js`:

- `_worker.js`
- `review-studio.html`
- `review-studio.css`
- `review-studio.js`

Deploy to Cloudflare.

Then sign in with the administrator Supabase account and open:

`https://ketogenicresearch.org/review-studio`

## Important MVP limitation

Project data are stored in the administrator browser (`localStorage`) in this first
version. Use **Export project JSON** regularly.

A production v2 should persist projects, screening decisions, extraction provenance
and audit history in Supabase so that projects are available across devices and can
support dual-reviewer workflows.

The meta-analysis engine in this MVP pools continuous outcomes using mean difference.
It should not be used to pool incompatible outcome definitions, units, time points or
comparators. Additional effect measures (SMD, RR, OR, HR), risk-of-bias modules,
GRADE, duplicate screening and full PRISMA 2020 exports belong in the next phase.
