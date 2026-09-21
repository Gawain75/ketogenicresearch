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
        if line.startswith("#") or line.startswith("**Ketogenic Research Editorial") or line.startswith("Scientific oversight:"):
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

def article_page(meta, en_title, en_html, it_title, it_html, slug, description):
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
<title>{html.escape(en_title)} | Ketogenic Research</title>
<meta name="description" content="{html.escape(description, quote=True)}">
<link rel="canonical" href="https://ketogenicresearch.org/articles/{html.escape(slug)}.html">
<meta property="og:type" content="article">
<meta property="og:site_name" content="Ketogenic Research">
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
<header class="article-topbar">
  <a href="../index.html" class="article-brand" aria-label="Ketogenic Research">
    <img src="../logo-ketogenic-research.png" alt="Ketogenic Research" class="article-logo">
  </a>
  <div class="article-lang">
    <button type="button" class="active" data-lang="en">EN</button>
    <button type="button" data-lang="it">IT</button>
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
    <div class="article-content">{en_html}</div>
    <div class="article-byline article-byline-top">
      <strong>Ketogenic Research Editorial</strong>
      <span>Scientific oversight: Marco Medeot, Scientific Director</span>
    </div>
  </section>

  <section class="article-language" data-article-lang="it">
    <div class="article-kicker">{html.escape(article_type_it)}</div>
    <div class="article-meta">{html.escape(meta_it)}</div>
    <div class="article-content">{it_html}</div>
    <div class="article-byline article-byline-top">
      <strong>Ketogenic Research Editorial</strong>
      <span>Supervisione scientifica: Marco Medeot, Direttore Scientifico</span>
    </div>
  </section>

  <div class="article-source-links">{' '.join(links)}</div>
</main>

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
    if(back) back.textContent=lang==='it'?back.dataset.labelIt:back.dataset.labelEn;
    if(title) title.textContent=lang==='it'?title.dataset.titleIt:title.dataset.titleEn;
    try{{localStorage.setItem('kr-lang',lang)}}catch(e){{}}
  }}
  buttons.forEach(b=>b.addEventListener('click',()=>setLang(b.dataset.lang)));
  let initial='en';
  try{{if(localStorage.getItem('kr-lang')==='it') initial='it'}}catch(e){{}}
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
<title>Articles | Ketogenic Research</title>
<meta name="description" content="Research notes and scientific analyses based on recent peer-reviewed ketogenic literature.">
<link rel="canonical" href="https://ketogenicresearch.org/articles.html">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Ketogenic Research">
<meta property="og:title" content="Articles | Ketogenic Research">
<meta property="og:description" content="Research notes and scientific analyses based on recent peer-reviewed ketogenic literature.">
<meta property="og:url" content="https://ketogenicresearch.org/articles.html">
<meta property="og:image" content="https://ketogenicresearch.org/logo-ketogenic-research.png">
<meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="Articles | Ketogenic Research">
<meta name="twitter:description" content="Research notes and scientific analyses based on recent peer-reviewed ketogenic literature.">
<meta name="twitter:image" content="https://ketogenicresearch.org/logo-ketogenic-research.png">
<link href="favicon.svg" rel="icon">
<link href="styles.css?v=70" rel="stylesheet">
<link href="articles.css?v=1" rel="stylesheet">
</head>
<body class="article-index-page">
<header class="article-topbar">
  <a href="index.html" class="article-brand" aria-label="Ketogenic Research">
    <img src="logo-ketogenic-research.png" alt="Ketogenic Research" class="article-logo">
  </a>
  <div class="article-lang">
    <button type="button" class="active" data-lang="en">EN</button>
    <button type="button" data-lang="it">IT</button>
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
  setLang(initial);
}})();
</script>
</body>
</html>'''

def main():
    PUBLIC.mkdir(exist_ok=True)
    cards = []

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
            r'<p><strong>Ketogenic Research Editorial</strong>\s*Scientific oversight:\s*<strong>Marco Medeot, Scientific Director</strong></p>',
            '',
            en_html,
            count=1,
            flags=re.I
        )
        it_html = re.sub(
            r'<p><strong>Ketogenic Research Editorial</strong>\s*Supervisione scientifica:\s*<strong>Marco Medeot, Direttore Scientifico</strong></p>',
            '',
            it_html,
            count=1,
            flags=re.I
        )

        if not en_title:
            continue

        slug = path.stem
        (PUBLIC / f"{slug}.html").write_text(
            article_page(
                meta, en_title, en_html, it_title, it_html, slug,
                plain_description(en_md),
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
      <h2>{html.escape(en_title)}</h2>
      <p>{html.escape(en_meta)}</p>
    </div>
    <div class="article-card-language" data-card-lang="it">
      <span class="article-card-type">{html.escape(str(meta.get("article_type_it", "Nota di ricerca")))}</span>
      <h2>{html.escape(it_title or en_title)}</h2>
      <p>{html.escape(it_meta)}</p>
    </div>
  </a>
</article>''')

    INDEX.write_text(index_page(cards), encoding="utf-8")

    static_urls = [
        ("https://ketogenicresearch.org/", "weekly", "1.0"),
        ("https://ketogenicresearch.org/research.html", "monthly", "0.9"),
        ("https://library.ketogenicresearch.org/library", "weekly", "1.0"),
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
