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

def run(*args):
    subprocess.run(args, cwd=ROOT, check=True)

def patch_renderer():
    s = RENDER.read_text(encoding="utf-8")

    # Stop rendering per-language H1s inside the article body.
    s, n = re.subn(
        r'(\s*if line\.startswith\("# "\):\n'
        r'\s*flush\(\)\n'
        r'\s*if not title:\n'
        r'\s*title = line\[2:\]\.strip\(\)\n)'
        r'\s*out\.append\(f"<h1>\{md_inline\(line\[2:\]\.strip\(\)\)\}</h1>"\)',
        r'\1            # Title rendered once outside language sections.',
        s,
        count=1,
    )
    if n == 0 and 'article-main-title' not in s:
        raise RuntimeError("Could not patch language-specific H1 rendering")

    # Add one shared bilingual H1.
    if 'class="article-main-title"' not in s:
        marker = '  <a class="article-back" href="../articles.html">&larr; <span data-label-en="Articles" data-label-it="Articoli">Articles</span></a>\n'
        if marker not in s:
            raise RuntimeError("Could not locate article back-link marker")
        addition = (
            marker
            + '  <h1 class="article-main-title"\\n'
            + '      data-title-en="{html.escape(en_title, quote=True)}"\\n'
            + '      data-title-it="{html.escape(it_title or en_title, quote=True)}">{html.escape(en_title)}</h1>\\n'
        )
        s = s.replace(marker, addition, 1)

    # Update title when language changes.
    if "const title=document.querySelector('[data-title-en]');" not in s:
        s = s.replace(
            "  const back=document.querySelector('[data-label-en]');\n",
            "  const back=document.querySelector('[data-label-en]');\n"
            "  const title=document.querySelector('[data-title-en]');\n",
            1,
        )
        s = s.replace(
            "    if(back) back.textContent=lang==='it'?back.dataset.labelIt:back.dataset.labelEn;\n",
            "    if(back) back.textContent=lang==='it'?back.dataset.labelIt:back.dataset.labelEn;\n"
            "    if(title) title.textContent=lang==='it'?title.dataset.titleIt:title.dataset.titleEn;\n",
            1,
        )

    # Remove duplicated article-type lines for both Note and Analysis.
    s = s.replace(
        "en_html = re.sub(r'<p><strong>Research Note</strong></p>', '', en_html, count=1)",
        "en_html = re.sub(r'<p><strong>Research (?:Note|Analysis)</strong></p>', '', en_html, count=1)"
    )
    s = s.replace(
        "it_html = re.sub(r'<p><strong>Nota di ricerca</strong></p>', '', it_html, count=1)",
        "it_html = re.sub(r'<p><strong>(?:Nota di ricerca|Analisi di ricerca)</strong></p>', '', it_html, count=1)"
    )

    # Article-page social/SEO metadata.
    if '<meta property="og:image"' not in s:
        s = s.replace(
            '<meta property="og:url" content="https://ketogenicresearch.org/articles/{html.escape(slug)}.html">\\n'
            '<meta name="twitter:card" content="summary">',
            '<meta property="og:url" content="https://ketogenicresearch.org/articles/{html.escape(slug)}.html">\\n'
            '<meta property="og:image" content="https://ketogenicresearch.org/logo-ketogenic-research.png">\\n'
            '<meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1">\\n'
            '<meta name="twitter:card" content="summary_large_image">',
            1,
        )
        s = s.replace(
            '<meta name="twitter:description" content="{html.escape(description, quote=True)}">\\n',
            '<meta name="twitter:description" content="{html.escape(description, quote=True)}">\\n'
            '<meta name="twitter:image" content="https://ketogenicresearch.org/logo-ketogenic-research.png">\\n',
            1,
        )

    # Articles-index social/SEO metadata.
    idx_marker = '<meta property="og:url" content="https://ketogenicresearch.org/articles.html">\\n<link href="favicon.svg" rel="icon">'
    if idx_marker in s:
        s = s.replace(
            idx_marker,
            '<meta property="og:url" content="https://ketogenicresearch.org/articles.html">\\n'
            '<meta property="og:image" content="https://ketogenicresearch.org/logo-ketogenic-research.png">\\n'
            '<meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1">\\n'
            '<meta name="twitter:card" content="summary_large_image">\\n'
            '<meta name="twitter:title" content="Articles | Ketogenic Research">\\n'
            '<meta name="twitter:description" content="Research notes and scientific analyses based on recent peer-reviewed ketogenic literature.">\\n'
            '<meta name="twitter:image" content="https://ketogenicresearch.org/logo-ketogenic-research.png">\\n'
            '<link href="favicon.svg" rel="icon">',
            1,
        )

    RENDER.write_text(s, encoding="utf-8")

def patch_home():
    if not HOME.exists():
        return
    s = HOME.read_text(encoding="utf-8")
    s = s.replace(
        "Un iniziativa di ricerca scientifica dedicato allo studio, alla valutazione critica e all'interpretazione clinica degli interventi chetogenici e metabolici.",
        "Un'iniziativa di ricerca scientifica dedicata allo studio, alla valutazione critica e all'interpretazione clinica degli interventi chetogenici e metabolici."
    )
    HOME.write_text(s, encoding="utf-8")

def verify():
    run(sys.executable, "-m", "py_compile", str(RENDER))

    lib = LIBRARY.read_text(encoding="utf-8")
    if lib.count('id="librarySearch"') != 1:
        raise RuntimeError("Library must contain exactly one librarySearch id")

    js = SCRIPT.read_text(encoding="utf-8")
    for token in ("randomized-clinical-trial", "clinical-trial", "preclinical", "mechanistic"):
        if token not in js:
            raise RuntimeError(f"Evidence filter regression: missing {token}")

    methodology = METHODOLOGY.read_text(encoding="utf-8")
    if "https://ketogenicresearch.org/methodology.html" not in methodology:
        raise RuntimeError("Methodology canonical URL regression")

    sitemap = SITEMAP.read_text(encoding="utf-8")
    for token in ("articles.html", "evidence-trends.html", "methodology.html"):
        if token not in sitemap:
            raise RuntimeError(f"Sitemap missing {token}")

    pages = sorted((ROOT / "articles").glob("*.html"))
    if not pages:
        raise RuntimeError("No public article pages found")

    for p in pages:
        text = p.read_text(encoding="utf-8")
        h1s = len(re.findall(r"<h1\\b", text, flags=re.I))
        if h1s != 1:
            raise RuntimeError(f"{p.name}: expected exactly one H1, found {h1s}")
        if 'property="og:image"' not in text:
            raise RuntimeError(f"{p.name}: og:image missing")
        if 'name="twitter:image"' not in text:
            raise RuntimeError(f"{p.name}: twitter:image missing")

    print(f"Final consistency check passed for {len(pages)} article pages.")

def main():
    patch_renderer()
    patch_home()
    run(sys.executable, "scripts/render_articles.py")
    run(sys.executable, "scripts/sync_publication_counters.py")
    verify()
    print("Final site polish applied successfully.")

if __name__ == "__main__":
    main()
