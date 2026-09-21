#!/usr/bin/env python3
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RENDER = ROOT / "scripts" / "render_articles.py"
HOME = ROOT / "index.html"

def run(*args):
    subprocess.run(args, cwd=ROOT, check=True)

def must_replace(s, old, new, label):
    if new in s:
        return s
    if old not in s:
        raise RuntimeError(f"Cannot find current block for {label}")
    return s.replace(old, new, 1)

def main():
    s = RENDER.read_text(encoding="utf-8")

    old = '            out.append(f"<h1>{md_inline(line[2:].strip())}</h1>")'
    new = '            # H1 rendered once by article_page(), outside language sections.'
    s = must_replace(s, old, new, "Markdown H1")

    old = '  <a class="article-back" href="../articles.html">&larr; <span data-label-en="Articles" data-label-it="Articoli">Articles</span></a>\n  <section class="article-language active" data-article-lang="en">'
    new = '  <a class="article-back" href="../articles.html">&larr; <span data-label-en="Articles" data-label-it="Articoli">Articles</span></a>\n  <h1 class="article-main-title" data-title-en="{html.escape(en_title, quote=True)}" data-title-it="{html.escape(it_title or en_title, quote=True)}">{html.escape(en_title)}</h1>\n  <section class="article-language active" data-article-lang="en">'
    s = must_replace(s, old, new, "shared bilingual H1")

    old = "  const back=document.querySelector('[data-label-en]');\n  function setLang(lang){{"
    new = "  const back=document.querySelector('[data-label-en]');\n  const title=document.querySelector('[data-title-en]');\n  function setLang(lang){{"
    s = must_replace(s, old, new, "title JS declaration")

    old = "    if(back) back.textContent=lang==='it'?back.dataset.labelIt:back.dataset.labelEn;\n    try{{localStorage.setItem('kr-lang',lang)}}catch(e){{}}"
    new = "    if(back) back.textContent=lang==='it'?back.dataset.labelIt:back.dataset.labelEn;\n    if(title) title.textContent=lang==='it'?title.dataset.titleIt:title.dataset.titleEn;\n    try{{localStorage.setItem('kr-lang',lang)}}catch(e){{}}"
    s = must_replace(s, old, new, "title JS switch")

    old = '<meta property="og:url" content="https://ketogenicresearch.org/articles/{html.escape(slug)}.html">\n<meta name="twitter:card" content="summary">\n<meta name="twitter:title" content="{html.escape(en_title, quote=True)}">\n<meta name="twitter:description" content="{html.escape(description, quote=True)}">'
    new = '<meta property="og:url" content="https://ketogenicresearch.org/articles/{html.escape(slug)}.html">\n<meta property="og:image" content="https://ketogenicresearch.org/logo-ketogenic-research.png">\n<meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1">\n<meta name="twitter:card" content="summary_large_image">\n<meta name="twitter:title" content="{html.escape(en_title, quote=True)}">\n<meta name="twitter:description" content="{html.escape(description, quote=True)}">\n<meta name="twitter:image" content="https://ketogenicresearch.org/logo-ketogenic-research.png">'
    s = must_replace(s, old, new, "article SEO")

    old = '<meta property="og:url" content="https://ketogenicresearch.org/articles.html">\n<link href="favicon.svg" rel="icon">'
    new = '<meta property="og:url" content="https://ketogenicresearch.org/articles.html">\n<meta property="og:image" content="https://ketogenicresearch.org/logo-ketogenic-research.png">\n<meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1">\n<meta name="twitter:card" content="summary_large_image">\n<meta name="twitter:title" content="Articles | Ketogenic Research">\n<meta name="twitter:description" content="Research notes and scientific analyses based on recent peer-reviewed ketogenic literature.">\n<meta name="twitter:image" content="https://ketogenicresearch.org/logo-ketogenic-research.png">\n<link href="favicon.svg" rel="icon">'
    s = must_replace(s, old, new, "articles index SEO")

    s = s.replace("en_html = re.sub(r\'<p><strong>Research Note</strong></p>\', \'\', en_html, count=1)", "en_html = re.sub(r\'<p><strong>Research (?:Note|Analysis)</strong></p>\', \'\', en_html, count=1)")
    s = s.replace("it_html = re.sub(r\'<p><strong>Nota di ricerca</strong></p>\', \'\', it_html, count=1)", "it_html = re.sub(r\'<p><strong>(?:Nota di ricerca|Analisi di ricerca)</strong></p>\', \'\', it_html, count=1)")

    RENDER.write_text(s, encoding="utf-8")
    run(sys.executable, "-m", "py_compile", str(RENDER))
    run(sys.executable, "scripts/render_articles.py")

    pages = sorted((ROOT / "articles").glob("*.html"))
    if not pages:
        raise RuntimeError("No public article pages rendered")
    for p in pages:
        t = p.read_text(encoding="utf-8")
        if len(re.findall(r"<h1\\b", t, flags=re.I)) != 1:
            raise RuntimeError(f"{p.name}: expected exactly one H1")
        if 'property="og:image"' not in t or 'name="twitter:image"' not in t:
            raise RuntimeError(f"{p.name}: social image metadata missing")

    if HOME.exists():
        h = HOME.read_text(encoding="utf-8")
        h = h.replace("Un iniziativa di ricerca scientifica dedicato allo studio, alla valutazione critica e all\'interpretazione clinica degli interventi chetogenici e metabolici.", "Un\'iniziativa di ricerca scientifica dedicata allo studio, alla valutazione critica e all\'interpretazione clinica degli interventi chetogenici e metabolici.")
        HOME.write_text(h, encoding="utf-8")

    print(f"Final site polish completed for {len(pages)} article pages.")

if __name__ == "__main__":
    main()
