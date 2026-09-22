#!/usr/bin/env python3
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / ".github" / "workflows"
ARCHIVE = ROOT / "workflow-archive"
ARCHIVE.mkdir(exist_ok=True)

# Workflow operativi da mantenere in GitHub Actions.
KEEP = {
    "update-literature-with-title-translation.yml": "01 · Daily literature update",
    "generate-articles-auto-v3_7.yml": "02 · Generate research article",
    "expand-scientific-library-v5_1-doi-guard.yml": "03 · Weekly Scientific Library expansion",
    "maintain-obesity-glp1-keto.yml": "04 · Maintain GLP-1 + ketogenic folder",
    "build-evidence-trends.yml": "05 · Build evidence trends",
    "repair-fulltext-links.yml": "06 · Repair full-text links",
    "synchronize-publication-counters.yml": "07 · Synchronize publication counters",
    "deploy-cloudflare-library.yml": "08 · Deploy Scientific Library to Cloudflare",
    "audit-all-article-sources.yml": "Maintenance · Audit published article sources",
    "workflow-cleanup.yml": "Maintenance · Workflow cleanup",
}

# File tecnici che non devono stare nella cartella workflows.
TECHNICAL = {
    "generate_articles.py",
    "sanitize_article_sources_v3_5.py",
    "library_v5.cpython-313.pyc",
    "update_latest.cpython-313.pyc",
}

def set_workflow_name(path: Path, name: str):
    text = path.read_text(encoding="utf-8", errors="replace")
    new, n = re.subn(r"(?m)^name:\s*.*$", f"name: {name}", text, count=1)
    if n == 0:
        new = f"name: {name}\n" + text
    if new != text:
        path.write_text(new, encoding="utf-8")

def archive(path: Path):
    target = ARCHIVE / path.name
    if target.exists():
        # Non sovrascrivere una copia precedente: mantieni l'ultima con suffisso.
        stem, suffix = path.stem, path.suffix
        i = 2
        while (ARCHIVE / f"{stem}-{i}{suffix}").exists():
            i += 1
        target = ARCHIVE / f"{stem}-{i}{suffix}"
    shutil.move(str(path), str(target))
    return target

kept = []
archived = []

# Mantieni soltanto i workflow operativi nell'interfaccia Actions.
for path in sorted(WF.glob("*.yml")):
    if path.name in KEEP:
        set_workflow_name(path, KEEP[path.name])
        kept.append(path.name)
    else:
        archived.append((path.name, archive(path).name))

# Archivia anche eventuali YAML .yaml non previsti.
for path in sorted(WF.glob("*.yaml")):
    archived.append((path.name, archive(path).name))

# Sposta fuori da .github/workflows i file Python/pyc impropri.
for name in TECHNICAL:
    path = WF / name
    if path.exists():
        archived.append((path.name, archive(path).name))

# La sottocartella scripts dentro workflows è legacy: archiviala.
legacy_scripts = WF / "scripts"
if legacy_scripts.exists():
    target = ARCHIVE / "workflow-scripts-legacy"
    if target.exists():
        shutil.rmtree(target)
    shutil.move(str(legacy_scripts), str(target))
    archived.append(("scripts/", "workflow-scripts-legacy/"))

readme = ARCHIVE / "README.md"
readme.write_text(
    """# Archived GitHub Actions

Questi file sono stati rimossi da `.github/workflows/` per ridurre duplicati,
workflow one-shot e vecchie versioni nell'interfaccia GitHub Actions.

Non sono stati cancellati: restano qui come storico e possono essere ripristinati
spostandoli nuovamente in `.github/workflows/`.

## Workflow operativi mantenuti

- 01 · Daily literature update
- 02 · Generate research article
- 03 · Weekly Scientific Library expansion
- 04 · Maintain GLP-1 + ketogenic folder
- 05 · Build evidence trends
- 06 · Repair full-text links
- 07 · Synchronize publication counters
- 08 · Deploy Scientific Library to Cloudflare
- Maintenance · Audit published article sources
- Maintenance · Workflow cleanup
""",
    encoding="utf-8",
)

print("WORKFLOWS MANTENUTI:")
for name in kept:
    print(" -", name)

print("\nARCHIVIATI:")
for old, new in archived:
    print(f" - {old} -> workflow-archive/{new}")
