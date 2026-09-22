#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import re
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
DRAFTS = ROOT / "articles-drafts"
PUBLIC = ROOT / "articles"
INDEX = ROOT / "articles.html"
SITEMAP = ROOT / "sitemap.xml"
LATEST = ROOT / "latest-publications.json"

def parse_frontmatter(text: str):
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    raw = text[4:end]
    body = text[end + 5:]
    meta = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        try:
            meta[key] = json.loads(value)
        except Exception:
            meta[key] = value.strip('"')
    return meta, body.strip()

def split_languages(body: str):
    parts = re.split(r"\n---\n", body, maxsplit=1)
    return parts[0].strip(), (parts[1].strip() if len(parts) > 1 else "")

def md_inline(s: str) -> str:
    s = html.escape(s, quote=True)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    return s

def markdown_to_html(md: str):
    lines = md.splitlines()
    out = []
    title = ""
    paragraph = []

    def flush():
        nonlocal paragraph
        if paragraph:
            out.append("<p>" + md_inline(" ".join(paragraph).strip()) + "</p>")
            paragraph = []

    for raw in lines:
        line = raw.strip()
        if not line:
            flush()
            continue
        if line.startswith("# "):
            flush()
            if not title:
                title = line[2:].strip()
            # H1 rendered once by article_page(), outside language sections.
        elif line.startswith("## "):
            flush()
            out.append(f"<h2>{md_inline(line[3:].strip())}</h2>")
        elif line.startswith("### "):
            flush()
            out.append(f"<h3>{md_inline(line[4:].strip())}</h3>")
        else:
            paragraph.append(line)
    flush()
    return title, "\n".join(out)

def pretty_date(value: str, lang: str) -> str:
    try:
        d = datetime.strptime(value[:10], "%Y-%m-%d")
        en = ["January","February","March","April","May","June","July","August","September","October","November","December"]
        it = ["gennaio","febbraio","marzo","aprile","maggio","giugno","luglio","agosto","settembre","ottobre","novembre","dicembre"]
        return f"{d.day} {it[d.month-1]} {d.year}" if lang == "it" else f"{en[d.month-1]} {d.day}, {d.year}"
    except Exception:
        return value

def plain_description(md: str, limit: int = 158) -> str:
    paragraphs = []
    current = []
    for raw in md.splitlines():
        line = raw.strip()
        if not line:
            if current:
                paragraphs.append(" ".join(current))
                current = []
            continue
        if line.startswith("#") or line.startswith("**Ketogenic Research Hub Editorial") or line.startswith("**Ketogenic Research Editorial") or line.startswith("Scientific oversight:"):
            continue
        if line in {"**Research Note**", "**Research Analysis**", "**Nota di ricerca**", "**Analisi di ricerca**"}:
            continue
        current.append(re.sub(r"\*\*", "", line))
    if current:
        paragraphs.append(" ".join(current))
    value = next((p for p in paragraphs if len(p) > 40), "")
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) <= limit:
        return value
    return value[:limit - 1].rsplit(" ", 1)[0] + "…"

def date_sort_key(meta: dict) -> tuple:
    value = str(meta.get("date") or "")
    try:
        if re.fullmatch(r"\d{4}-\d{2}", value):
            value += "-01"
        d = datetime.strptime(value[:10], "%Y-%m-%d")
        return (d, str(meta.get("pmid") or ""))
    except Exception:
        return (datetime.min, str(meta.get("pmid") or ""))



def load_latest_lookup() -> dict[str, dict]:
    if not LATEST.exists():
        return {}
    try:
        data = json.loads(LATEST.read_text(encoding="utf-8"))
        return {str(x.get("pmid")): x for x in data.get("publications", []) if x.get("pmid")}
    except Exception:
        return {}


def evidence_descriptors(meta: dict, en_md: str, latest_record: dict | None = None) -> dict[str, str]:
    latest_record = latest_record or {}
    evidence = str(latest_record.get("evidence_type") or meta.get("evidence_type") or "").strip()
    body = (en_md or "").lower()
    title = re.search(r'^#\s+(.+)$', en_md or "", re.M)
    title_l = title.group(1).lower() if title else ""

    # Explicit study-design signals in the verified article text take precedence
    # when very recent PubMed indexing is incomplete or overly broad.
    explicit_case = any(x in body for x in (
        "single-case report", "single case report", "single‑case report",
        "single patient", "single-patient", "single‑patient",
        "case report", "case series"
    ))
    explicit_preclinical = any(x in body for x in (
        "mouse model", "mice", "murine", "rat model", "rats",
        "in vitro", "cell culture", "cell line"
    ))
    if explicit_case and not explicit_preclinical:
        evidence = "Case report / case series"
    elif explicit_preclinical:
        evidence = "Preclinical / mechanistic"
    elif not evidence or evidence == "Other":
        if any(x in title_l for x in ("systematic review", "meta-analysis", "meta‑analysis")):
            evidence = "Systematic review / meta-analysis"
        elif any(x in body for x in ("randomized", "randomised", "placebo-controlled", "placebo‑controlled")):
            evidence = "Randomized clinical trial"
        elif any(x in body for x in ("retrospective cohort", "prospective cohort", "observational study", "cross-sectional", "cross‑sectional")):
            evidence = "Observational human study"
        else:
            evidence = "Other"

    design_it = {
        "Systematic review / meta-analysis": "Revisione sistematica / meta-analisi",
        "Guideline / consensus": "Linea guida / consensus",
        "Randomized clinical trial": "Trial clinico randomizzato",
        "Clinical trial / intervention": "Trial clinico / intervento",
        "Observational human study": "Studio osservazionale umano",
        "Case report / case series": "Case report / case series",
        "Review": "Revisione",
        "Preclinical / mechanistic": "Preclinico / meccanicistico",
        "Other": "Altro",
    }.get(evidence, evidence)

    if evidence == "Preclinical / mechanistic":
        species=[]
        if re.search(r'\b(mouse|mice|murine)\b', body): species.append(("Mouse", "Topo"))
        elif re.search(r'\b(rat|rats|rodent|rodents)\b', body): species.append(("Rat", "Ratto"))
        if any(x in body for x in ("in vitro", "cell culture", "cell line")): species.append(("In vitro", "In vitro"))
        if species:
            pop_en=" + ".join(x[0] for x in species)
            pop_it=" + ".join(x[1] for x in species)
        else:
            pop_en, pop_it = "Preclinical model", "Modello preclinico"
    else:
        if any(x in body for x in ("infant", "infants", "neonate", "neonatal")):
            pop_en, pop_it = "Human · infants", "Umano · lattanti"
        elif any(x in body for x in ("children", "pediatric", "paediatric", "adolescents")):
            pop_en, pop_it = "Human · pediatric", "Umano · pediatrico"
        elif any(x in body for x in ("older adults", "elderly", "alzheimer’s disease", "alzheimer's disease")) and evidence == "Systematic review / meta-analysis":
            pop_en, pop_it = "Human · older adults", "Umano · adulti anziani"
        elif evidence in {"Randomized clinical trial", "Clinical trial / intervention", "Observational human study", "Case report / case series", "Systematic review / meta-analysis", "Guideline / consensus"}:
            pop_en, pop_it = "Human", "Umano"
        else:
            pop_en, pop_it = "Not specified", "Non specificata"

    status_map={
        "Systematic review / meta-analysis": ("Evidence synthesis", "Sintesi delle evidenze"),
        "Guideline / consensus": ("Guidance / consensus evidence", "Evidenza da linee guida / consensus"),
        "Randomized clinical trial": ("Controlled clinical evidence", "Evidenza clinica controllata"),
        "Clinical trial / intervention": ("Interventional clinical evidence", "Evidenza clinica interventistica"),
        "Observational human study": ("Observational clinical evidence", "Evidenza clinica osservazionale"),
        "Case report / case series": ("Hypothesis-generating", "Generazione di ipotesi"),
        "Review": ("Narrative evidence synthesis", "Sintesi narrativa delle evidenze"),
        "Preclinical / mechanistic": ("No clinical efficacy evidence", "Nessuna evidenza di efficacia clinica"),
        "Other": ("Exploratory evidence", "Evidenza esplorativa"),
    }
    status_en,status_it=status_map.get(evidence,("Exploratory evidence","Evidenza esplorativa"))
    return {
        "design_en": evidence,
        "design_it": design_it,
        "population_en": pop_en,
        "population_it": pop_it,
        "status_en": status_en,
        "status_it": status_it,
    }


def article_page(meta, en_title, en_html, it_title, it_html, slug, description, descriptors):
    date = str(meta.get("date", ""))
    journal = str(meta.get("journal", ""))
    pmid = str(meta.get("pmid", ""))
    doi = str(meta.get("doi", ""))
    article_type = str(meta.get("article_type", "Research Note"))
    article_type_it = str(meta.get("article_type_it", "Nota di ricerca"))

    meta_en = " · ".join(x for x in [pretty_date(date, "en"), journal] if x)
    meta_it = " · ".join(x for x in [pretty_date(date, "it"), journal] if x)

    links = []
    if pmid:
        links.append(f'<a href="https://pubmed.ncbi.nlm.nih.gov/{html.escape(pmid)}/" target="_blank" rel="noopener">PubMed</a>')
    if doi:
        links.append(f'<a href="https://doi.org/{html.escape(doi)}" target="_blank" rel="noopener">DOI</a>')

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(en_title)} | Ketogenic Research Hub</title>
<meta name="description" content="{html.escape(description, quote=True)}">
<link rel="canonical" href="https://ketogenicresearch.org/articles/{html.escape(slug)}.html">
<meta property="og:type" content="article">
<meta property="og:site_name" content="Ketogenic Research Hub">
<meta property="og:title" content="{html.escape(en_title, quote=True)}">
<meta property="og:description" content="{html.escape(description, quote=True)}">
<meta property="og:url" content="https://ketogenicresearch.org/articles/{html.escape(slug)}.html">
<meta property="og:image" content="https://ketogenicresearch.org/logo-ketogenic-research.png">
<meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{html.escape(en_title, quote=True)}">
<meta name="twitter:description" content="{html.escape(description, quote=True)}">
<meta name="twitter:image" content="https://ketogenicresearch.org/logo-ketogenic-research.png">
<link href="../favicon.svg" rel="icon">
<link href="../styles.css?v=70" rel="stylesheet">
<link href="../articles.css?v=1" rel="stylesheet">
</head>
<body class="article-page">
<header class="header">
<div class="wrap nav">
<a aria-label="Ketogenic Research Hub" class="brand" href="../index.html">
<img alt="Ketogenic Research Hub" class="site-logo" src="../logo-ketogenic-research.png"/>
</a>
<nav aria-label="Primary navigation" class="site-nav">
<a href="../index.html">Home</a>
<a data-en="Research" data-it="Ricerca" href="../research.html">Research</a>
<a data-en="Scientific Library" data-it="Biblioteca Scientifica" href="https://library.ketogenicresearch.org/library">Scientific Library</a>
<a data-en="Latest Evidence" data-it="Ultime evidenze" href="../latest.html">Latest Evidence</a>
<a data-en="Evidence Trends" data-it="Andamento evidenze" href="../evidence-trends.html">Evidence Trends</a>
<a data-en="Articles" data-it="Articoli" href="../articles.html">Articles</a>
<a data-en="Scientific Direction" data-it="Direzione scientifica" href="../director.html">Scientific Direction</a>
<details class="nav-more">
<summary>
<span data-en="More" data-it="Altro">More</span>
<span aria-hidden="true" class="nav-caret">▾</span>
</summary>
<div class="nav-submenu">
<a data-en="Methodology" data-it="Metodologia" href="../methodology.html">Methodology</a>
<a data-en="Contact" data-it="Contatti" href="../contact.html">Contact</a>
</div>
</details>
</nav>
<div class="actions">
<div class="lang"><button aria-label="English" aria-pressed="false" class="active" data-lang="en">EN</button><button aria-label="Italiano" aria-pressed="false" data-lang="it">IT</button></div>
<button aria-label="Menu" class="menu">☰</button>
</div>
</div>
</header>

<main class="article-shell">
  <a class="article-back" href="../articles.html">&larr; <span data-label-en="Articles" data-label-it="Articoli">Articles</span></a>
  <h1 class="article-main-title"
      data-title-en="{html.escape(en_title, quote=True)}"
      data-title-it="{html.escape(it_title or en_title, quote=True)}">{html.escape(en_title)}</h1>

  <section class="article-language active" data-article-lang="en">
    <div class="article-kicker">{html.escape(article_type)}</div>
    <div class="article-meta">{html.escape(meta_en)}</div>
    <div class="article-evidence-grid">
      <div><span>Study design</span><strong>{html.escape(descriptors["design_en"])}</strong></div>
      <div><span>Population / species</span><strong>{html.escape(descriptors["population_en"])}</strong></div>
      <div><span>Evidence status</span><strong>{html.escape(descriptors["status_en"])}</strong></div>
    </div>
    <div class="article-content">{en_html}</div>
    <div class="article-byline article-byline-top">
      <strong>Ketogenic Research Hub Editorial</strong>
      <span>Scientific oversight: Marco Medeot, Scientific Director</span>
    </div>
  </section>

  <section class="article-language" data-article-lang="it">
    <div class="article-kicker">{html.escape(article_type_it)}</div>
    <div class="article-meta">{html.escape(meta_it)}</div>
    <div class="article-evidence-grid">
      <div><span>Disegno dello studio</span><strong>{html.escape(descriptors["design_it"])}</strong></div>
      <div><span>Popolazione / specie</span><strong>{html.escape(descriptors["population_it"])}</strong></div>
      <div><span>Stato dell’evidenza</span><strong>{html.escape(descriptors["status_it"])}</strong></div>
    </div>
    <div class="article-content">{it_html}</div>
    <div class="article-byline article-byline-top">
      <strong>Ketogenic Research Hub Editorial</strong>
      <span>Supervisione scientifica: Marco Medeot, Direttore Scientifico</span>
    </div>
  </section>

  <div class="article-source-links">{' '.join(links)}</div>
</main>
<footer><div class="wrap footer"><span>KETOGENIC RESEARCH HUB</span><nav class="footer-links" aria-label="Footer"><a href="../privacy.html" data-en="Privacy" data-it="Privacy">Privacy</a><a href="../contact.html" data-en="Contact" data-it="Contatti">Contact</a><a href="../methodology.html" data-en="Methodology" data-it="Metodologia">Methodology</a></nav><span>© 2026 Ketogenic Research Hub</span></div></footer>

<script>
(function(){{
  const buttons=[...document.querySelectorAll('[data-lang]')];
  const sections=[...document.querySelectorAll('[data-article-lang]')];
  const back=document.querySelector('[data-label-en]');
  const title=document.querySelector('[data-title-en]');
  function setLang(lang){{
    document.documentElement.lang=lang;
    buttons.forEach(b=>b.classList.toggle('active',b.dataset.lang===lang));
    sections.forEach(s=>s.classList.toggle('active',s.dataset.articleLang===lang));
    document.querySelectorAll('[data-en]').forEach(el=>{{
      const v=lang==='it'?el.dataset.it:el.dataset.en;
      if(v!==undefined) el.textContent=v;
    }});
    if(back) back.textContent=lang==='it'?back.dataset.labelIt:back.dataset.labelEn;
    if(title) title.textContent=lang==='it'?title.dataset.titleIt:title.dataset.titleEn;
    try{{localStorage.setItem('kr-lang',lang)}}catch(e){{}}
  }}
  buttons.forEach(b=>b.addEventListener('click',()=>setLang(b.dataset.lang)));
  let initial='en';
  try{{if(localStorage.getItem('kr-lang')==='it') initial='it'}}catch(e){{}}

  const menu=document.querySelector('.header .menu');
  const nav=document.querySelector('.header nav');
  if(menu && nav){{
    menu.setAttribute('aria-expanded','false');
    menu.addEventListener('click',event=>{{
      event.preventDefault();
      event.stopPropagation();
      const open=nav.classList.toggle('open');
      menu.setAttribute('aria-expanded',open?'true':'false');
    }});
    nav.querySelectorAll('a').forEach(link=>{{
      link.addEventListener('click',()=>{{
        nav.classList.remove('open');
        menu.setAttribute('aria-expanded','false');
      }});
    }});
  }}
  setLang(initial);
}})();
</script>
</body>
</html>'''

def index_page(cards):
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Articles | Ketogenic Research Hub</title>
<meta name="description" content="Research notes and scientific analyses based on recent peer-reviewed ketogenic literature.">
<link rel="canonical" href="https://ketogenicresearch.org/articles.html">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Ketogenic Research Hub">
<meta property="og:title" content="Articles | Ketogenic Research Hub">
<meta property="og:description" content="Research notes and scientific analyses based on recent peer-reviewed ketogenic literature.">
<meta property="og:url" content="https://ketogenicresearch.org/articles.html">
<meta property="og:image" content="https://ketogenicresearch.org/logo-ketogenic-research.png">
<meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="Articles | Ketogenic Research Hub">
<meta name="twitter:description" content="Research notes and scientific analyses based on recent peer-reviewed ketogenic literature.">
<meta name="twitter:image" content="https://ketogenicresearch.org/logo-ketogenic-research.png">
<link href="favicon.svg" rel="icon">
<link href="styles.css?v=70" rel="stylesheet">
<link href="articles.css?v=1" rel="stylesheet">
</head>
<body class="article-index-page">
<header class="header">
<div class="wrap nav">
<a aria-label="Ketogenic Research Hub" class="brand" href="index.html">
<img alt="Ketogenic Research Hub" class="site-logo" src="logo-ketogenic-research.png"/>
</a>
<nav aria-label="Primary navigation" class="site-nav">
<a href="index.html">Home</a>
<a data-en="Research" data-it="Ricerca" href="research.html">Research</a>
<a data-en="Scientific Library" data-it="Biblioteca Scientifica" href="https://library.ketogenicresearch.org/library">Scientific Library</a>
<a data-en="Latest Evidence" data-it="Ultime evidenze" href="latest.html">Latest Evidence</a>
<a data-en="Evidence Trends" data-it="Andamento evidenze" href="evidence-trends.html">Evidence Trends</a>
<a data-en="Articles" data-it="Articoli" href="articles.html">Articles</a>
<a data-en="Scientific Direction" data-it="Direzione scientifica" href="director.html">Scientific Direction</a>
<details class="nav-more">
<summary>
<span data-en="More" data-it="Altro">More</span>
<span aria-hidden="true" class="nav-caret">▾</span>
</summary>
<div class="nav-submenu">
<a data-en="Methodology" data-it="Metodologia" href="methodology.html">Methodology</a>
<a data-en="Contact" data-it="Contatti" href="contact.html">Contact</a>
</div>
</details>
</nav>
<div class="actions">
<div class="lang"><button aria-label="English" aria-pressed="false" class="active" data-lang="en">EN</button><button aria-label="Italiano" aria-pressed="false" data-lang="it">IT</button></div>
<button aria-label="Menu" class="menu">☰</button>
</div>
</div>
</header>

<main class="article-shell">
  <div class="article-index-intro">
    <p class="article-kicker" data-en="EDITORIAL" data-it="EDITORIALE">EDITORIAL</p>
    <h1 data-en="Articles" data-it="Articoli">Articles</h1>
    <p data-en="Research notes and scientific analyses based on recent peer-reviewed literature."
       data-it="Note di ricerca e analisi scientifiche basate sulla letteratura peer-reviewed recente.">
       Research notes and scientific analyses based on recent peer-reviewed literature.
    </p>
  </div>
  <div class="article-list">{''.join(cards)}</div>
</main>
<footer><div class="wrap footer"><span>KETOGENIC RESEARCH HUB</span><nav class="footer-links" aria-label="Footer"><a href="privacy.html" data-en="Privacy" data-it="Privacy">Privacy</a><a href="contact.html" data-en="Contact" data-it="Contatti">Contact</a><a href="methodology.html" data-en="Methodology" data-it="Metodologia">Methodology</a></nav><span>© 2026 Ketogenic Research Hub</span></div></footer>

<script>
(function(){{
  const buttons=[...document.querySelectorAll('[data-lang]')];
  function setLang(lang){{
    document.documentElement.lang=lang;
    buttons.forEach(b=>b.classList.toggle('active',b.dataset.lang===lang));
    document.querySelectorAll('[data-en]').forEach(el=>{{
      const v=lang==='it'?el.dataset.it:el.dataset.en;
      if(v!==undefined) el.textContent=v;
    }});
    document.querySelectorAll('[data-card-lang]').forEach(el=>{{
      el.classList.toggle('active',el.dataset.cardLang===lang);
    }});
    try{{localStorage.setItem('kr-lang',lang)}}catch(e){{}}
  }}
  buttons.forEach(b=>b.addEventListener('click',()=>setLang(b.dataset.lang)));
  let initial='en';
  try{{if(localStorage.getItem('kr-lang')==='it') initial='it'}}catch(e){{}}

  const menu=document.querySelector('.header .menu');
  const nav=document.querySelector('.header nav');
  if(menu && nav){{
    menu.setAttribute('aria-expanded','false');
    menu.addEventListener('click',event=>{{
      event.preventDefault();
      event.stopPropagation();
      const open=nav.classList.toggle('open');
      menu.setAttribute('aria-expanded',open?'true':'false');
    }});
    nav.querySelectorAll('a').forEach(link=>{{
      link.addEventListener('click',()=>{{
        nav.classList.remove('open');
        menu.setAttribute('aria-expanded','false');
      }});
    }});
  }}
  setLang(initial);
}})();
</script>
</body>
</html>'''

def main():
    PUBLIC.mkdir(exist_ok=True)
    cards = []
    latest_lookup = load_latest_lookup()

    entries = []
    for path in DRAFTS.glob("*.md"):
        meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        if str(meta.get("verification", "")).upper() != "PASS":
            continue
        entries.append((date_sort_key(meta), path, meta, body))

    for _, path, meta, body in sorted(entries, key=lambda x: x[0], reverse=True):
        en_md, it_md = split_languages(body)
        en_title, en_html = markdown_to_html(en_md)
        it_title, it_html = markdown_to_html(it_md)

        # Remove duplicated article type and duplicated editorial byline from the Markdown body.
        en_html = re.sub(r'<p><strong>Research (?:Note|Analysis)</strong></p>', '', en_html, count=1)
        it_html = re.sub(r'<p><strong>(?:Nota di ricerca|Analisi di ricerca)</strong></p>', '', it_html, count=1)

        en_html = re.sub(
            r'<p><strong>Ketogenic Research(?: Hub)? Editorial</strong>\s*Scientific oversight:\s*<strong>Marco Medeot, Scientific Director</strong></p>',
            '',
            en_html,
            count=1,
            flags=re.I
        )
        it_html = re.sub(
            r'<p><strong>Ketogenic Research(?: Hub)? Editorial</strong>\s*Supervisione scientifica:\s*<strong>Marco Medeot, Direttore Scientifico</strong></p>',
            '',
            it_html,
            count=1,
            flags=re.I
        )

        if not en_title:
            continue

        slug = path.stem
        descriptors = evidence_descriptors(meta, en_md, latest_lookup.get(str(meta.get("pmid") or "")))
        (PUBLIC / f"{slug}.html").write_text(
            article_page(
                meta, en_title, en_html, it_title, it_html, slug,
                plain_description(en_md), descriptors,
            ),
            encoding="utf-8"
        )

        date = str(meta.get("date", ""))
        journal = str(meta.get("journal", ""))
        en_meta = " · ".join(x for x in [pretty_date(date, "en"), journal] if x)
        it_meta = " · ".join(x for x in [pretty_date(date, "it"), journal] if x)

        cards.append(f'''
<article class="article-card">
  <a href="articles/{slug}.html">
    <div class="article-card-language active" data-card-lang="en">
      <span class="article-card-type">{html.escape(str(meta.get("article_type", "Research Note")))}</span>
      <div class="article-card-evidence">{html.escape(descriptors["design_en"])} · {html.escape(descriptors["population_en"])} · {html.escape(descriptors["status_en"])}</div>
      <h2>{html.escape(en_title)}</h2>
      <p>{html.escape(en_meta)}</p>
    </div>
    <div class="article-card-language" data-card-lang="it">
      <span class="article-card-type">{html.escape(str(meta.get("article_type_it", "Nota di ricerca")))}</span>
      <div class="article-card-evidence">{html.escape(descriptors["design_it"])} · {html.escape(descriptors["population_it"])} · {html.escape(descriptors["status_it"])}</div>
      <h2>{html.escape(it_title or en_title)}</h2>
      <p>{html.escape(it_meta)}</p>
    </div>
  </a>
</article>''')

    INDEX.write_text(index_page(cards), encoding="utf-8")

    static_urls = [
        ("https://ketogenicresearch.org/", "weekly", "1.0"),
        ("https://ketogenicresearch.org/research.html", "monthly", "0.9"),
        ("https://ketogenicresearch.org/library.html", "weekly", "1.0"),
        ("https://ketogenicresearch.org/latest.html", "daily", "0.9"),
        ("https://ketogenicresearch.org/articles.html", "daily", "0.9"),
        ("https://ketogenicresearch.org/evidence-trends.html", "weekly", "0.8"),
        ("https://ketogenicresearch.org/methodology.html", "monthly", "0.8"),
        ("https://ketogenicresearch.org/director.html", "monthly", "0.8"),
        ("https://ketogenicresearch.org/contact.html", "yearly", "0.6"),
    ]
    urls = [
        f"  <url>\n    <loc>{loc}</loc>\n    <changefreq>{freq}</changefreq>\n    <priority>{priority}</priority>\n  </url>"
        for loc, freq, priority in static_urls
    ]
    for _, path, meta, _ in sorted(entries, key=lambda x: x[0], reverse=True):
        slug = path.stem
        urls.append(
            "  <url>\n"
            f"    <loc>https://ketogenicresearch.org/articles/{slug}.html</loc>\n"
            "    <changefreq>monthly</changefreq>\n"
            "    <priority>0.7</priority>\n"
            "  </url>"
        )
    SITEMAP.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>\n",
        encoding="utf-8",
    )

    print(f"Rendered {len(cards)} public article(s) and updated sitemap.xml.")

if __name__ == "__main__":
    main()
