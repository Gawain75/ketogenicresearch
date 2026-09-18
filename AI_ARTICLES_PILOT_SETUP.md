# AI Articles Pilot — setup

This pilot is intentionally isolated from the public site.

It does not modify:
- index.html
- library.html
- latest.html
- script.js
- styles.css
- the existing literature workflow

It creates up to 3 verified Markdown drafts in `articles-drafts/`.

## Required GitHub secret

Create a Groq API key, then in GitHub:

Settings → Secrets and variables → Actions → New repository secret

Name:
`GROQ_API_KEY`

Value:
your Groq API key

`NCBI_API_KEY` is optional if already configured for the literature workflow.

## Run

GitHub → Actions → AI article pilot → Run workflow.

After completion, inspect `articles-drafts/`.

Only drafts that pass the second AI fact-checking pass are written.
