#!/usr/bin/env python3
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RENDER = ROOT / "scripts" / "render_articles.py"
HOME = ROOT / "index.html"
LIBRARY = ROOT / "library.html"
SCRIPT = ROOT / "script.js"
METHODOLOGY = ROOT / "methodology.html"
SITEMAP = ROOT / "sitemap.xml"


def replace_once(text, old, new, label):
    if new in text:
        return text
    if old not in text:
        raise RuntimeError(f"Cannot find expected block for {label}")
    return text.replace(old, new, 1)


def patch_renderer():
    s = RENDER.read_text(encoding="utf-8")

    old = """        if line.startswith("# "):
            flush()
            if not title:
                title = line[2:].strip()
            out.append(f"<h1>{md_inline(line[2:].strip())}</h1>")"""
    new = """        if line.startswith("# "):
            flush()
            if not title:
                title = line[2:].strip()
            # The public page renders one shared bilingual H1 outside the
            # language-specific bodies. Do not duplicate H1 elements here."""
    s = replace_once(s, old, new, "single H1 rendering")

    old = """<meta property="og:url" content="https://ketogenicresearch.org/articles/{html.escape(slug)}.html">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{html.escape(en_title, quote=True)}">
<meta name="twitter:description" content="{html.escape(description, quote=True)}">"""
    new = """<meta property="og:url" content="https://ketogenicresearch.org/articles/{html.escape(slug)}.html">
<meta property="og:image" content="https://ketogenicresearch.org/logo-ketogenic-research.png">
<meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{html.escape(en_title, quote=True)}">
<meta name="twitter:description" content="{html.escape(description, quote=True)}">
<meta name="twitter:image" content="https://ketogenicresearch.org/logo-ketogenic-research.png">"""
    s = replace_once(s, old, new, "article social/SEO metadata")

    old = """<main class="article-shell">
  <a class="article-back" href="../articles.html">&larr; <span data-label-en="Articles" data-label-it="Articoli">Articles</span></a>
  <section class="article-language active" data-article-lang="en">"""
    new = """<main class="article-shell">
  <a class="article-back" href="../articles.html">&larr; <span data-label-en="Articles" data-label-it="Articoli">Articles</span></a>
  <h1 class="article-main-title"
      data-title-en="{html.escape(en_title, quote=True)}"
      data-title-it="{html.escape(it_title or en_title, quote=True)}">{html.escape(en_title)}</h1>
  <section class="article-language active" data-article-lang="en">"""
    s = replace_once(s, old, new, "shared bilingual article H1")

    old = """  const sections=[...document.querySelectorAll('[data-article-lang]')];
  const back=document.querySelector('[data-label-en]');
  function setLang(lang){{
    document.documentElement.lang=lang;
    buttons.forEach(b=>b.classList.toggle('active',b.dataset.lang===lang));
    sections.forEach(s=>s.classList.toggle('active',s.dataset.articleLang===lang));
    if(back) back.textContent=lang==='it'?back.dataset.labelIt:back.dataset.labelEn;"""
    new = """  const sections=[...document.querySelectorAll('[data-article-lang]')];
  const back=document.querySelector('[data-label-en]');
  const title=document.querySelector('[data-title-en]');
  function setLang(lang){{
    document.documentElement.lang=lang;
    buttons.forEach(b=>b.classList.toggle('active',b.dataset.lang===lang));
    sections.forEach(s=>s.classList.toggle('active',s.dataset.articleLang===lang));
    if(back) back.textContent=lang==='it'?back.dataset.labelIt:back.dataset.labelEn;
    if(title) title.textContent=lang==='it'?title.dataset.titleIt:title.dataset.titleEn;"""
    s = replace_once(s, old, new, "bilingual shared H1 switch")

    s = s.replace(
        "en_html = re.sub(r'<p><strong>Research Note</strong></p>', '', en_html, count=1)",
        "en_html = re.sub(r'<p><strong>Research (?:Note|Analysis)</strong></p>', '', en_html, count=1)"
    )
    s = s.replace(
        "it_html = re.sub(r'<p><strong>Nota di ricerca</strong></p>', '', it_html, count=1)",
        "it_html = re.sub(r'<p><strong>(?:Nota di ricerca|Analisi di ricerca)</strong></p>', '', it_html, count=1)"
    )

    old = """<meta property="og:url" content="https://ketogenicresearch.org/articles.html">
<link href="favicon.svg" rel="icon">"""
    new = """<meta property="og:url" content="https://ketogenicresearch.org/articles.html">
<meta property="og:image" content="https://ketogenicresearch.org/logo-ketogenic-research.png">
<meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="Articles | Ketogenic Research">
<meta name="twitter:description" content="Research notes and scientific analyses based on recent peer-reviewed ketogenic literature.">
<meta name="twitter:image" content="https://ketogenicresearch.org/logo-ketogenic-research.png">
<link href="favicon.svg" rel="icon">"""
    s = replace_once(s, old, new, "articles index SEO metadata")

    RENDER.write_text(s, encoding="utf-8")


def patch_home_copy():
    s = HOME.read_text(encoding="utf-8")
    s = s.replace(
        "Un iniziativa di ricerca scientifica dedicato allo studio, alla valutazione critica e all'interpretazione clinica degli interventi chetogenici e metabolici.",
        "Un'iniziativa di ricerca scientifica dedicata allo studio, alla valutazione critica e all'interpretazione clinica degli interventi chetogenici e metabolici."
    )
    HOME.write_text(s, encoding="utf-8")


def run(*args):
    subprocess.run(args, cwd=ROOT, check=True)


def verify():
    run(sys.executable, "-m", "py_compile", str(RENDER))

    js = SCRIPT.read_text(encoding="utf-8")
    for token in (
        "randomized-clinical-trial",
        "clinical-trial",
        "preclinical",
        "mechanistic",
    ):
        if token not in js:
            raise RuntimeError(f"Evidence filter regression: {token} missing from script.js")

    library = LIBRARY.read_text(encoding="utf-8")
    if library.count('id="librarySearch"') != 1:
        raise RuntimeError("Scientific Library must contain exactly one librarySearch id")

    methodology = METHODOLOGY.read_text(encoding="utf-8")
    if 'href="https://ketogenicresearch.org/methodology.html" rel="canonical"' not in methodology:
        raise RuntimeError("Methodology canonical URL regression")

    sitemap = SITEMAP.read_text(encoding="utf-8")
    for url in ("articles.html", "evidence-trends.html", "methodology.html"):
        if url not in sitemap:
            raise RuntimeError(f"Sitemap missing {url}")

    articles = sorted((ROOT / "articles").glob("*.html"))
    if not articles:
        raise RuntimeError("No public article pages found")

    for p in articles:
        text = p.read_text(encoding="utf-8")
        h1_count = len(re.findall(r"<h1\b", text, flags=re.I))
        if h1_count != 1:
            raise RuntimeError(f"{p.name}: expected 1 H1, found {h1_count}")
        if re.search(r"<p><strong>Research (?:Note|Analysis)</strong></p>", text):
            raise RuntimeError(f"{p.name}: duplicate English article-type line remains")
        if re.search(r"<p><strong>(?:Nota di ricerca|Analisi di ricerca)</strong></p>", text):
            raise RuntimeError(f"{p.name}: duplicate Italian article-type line remains")
        if 'name="description"' not in text or 'rel="canonical"' not in text:
            raise RuntimeError(f"{p.name}: essential SEO metadata missing")
        if 'property="og:image"' not in text or 'name="twitter:image"' not in text:
            raise RuntimeError(f"{p.name}: social preview metadata missing")

    print(f"Final consistency check passed for {len(articles)} article pages.")


def main():
    patch_renderer()
    patch_home_copy()
    run(sys.executable, "scripts/render_articles.py")
    run(sys.executable, "scripts/sync_publication_counters.py")
    verify()
    print("Final site polish applied successfully.")


if __name__ == "__main__":
    main()
