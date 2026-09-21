#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RENDER = ROOT / "scripts" / "render_articles.py"
HOME = ROOT / "index.html"

def run(*args):
    subprocess.run(args, cwd=ROOT, check=True)

def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise RuntimeError(f"Cannot find expected block for {label}")
    return text.replace(old, new, 1)

def main():
    s = RENDER.read_text(encoding="utf-8")

    # Preserve existing EN/IT buttons and language sections exactly as they are.

    s = s.replace(
        "en_html = re.sub(r'<p><strong>Research Note</strong></p>', '', en_html, count=1)",
        "en_html = re.sub(r'<p><strong>Research (?:Note|Analysis)</strong></p>', '', en_html, count=1)",
        1,
    )
    s = s.replace(
        "it_html = re.sub(r'<p><strong>Nota di ricerca</strong></p>', '', it_html, count=1)",
        "it_html = re.sub(r'<p><strong>(?:Nota di ricerca|Analisi di ricerca)</strong></p>', '', it_html, count=1)",
        1,
    )

    old_article = (
        '<meta property="og:url" content="https://ketogenicresearch.org/articles/{html.escape(slug)}.html">\n'
        '<meta name="twitter:card" content="summary">\n'
        '<meta name="twitter:title" content="{html.escape(en_title, quote=True)}">\n'
        '<meta name="twitter:description" content="{html.escape(description, quote=True)}">'
    )
    new_article = (
        '<meta property="og:url" content="https://ketogenicresearch.org/articles/{html.escape(slug)}.html">\n'
        '<meta property="og:image" content="https://ketogenicresearch.org/logo-ketogenic-research.png">\n'
        '<meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1">\n'
        '<meta name="twitter:card" content="summary_large_image">\n'
        '<meta name="twitter:title" content="{html.escape(en_title, quote=True)}">\n'
        '<meta name="twitter:description" content="{html.escape(description, quote=True)}">\n'
        '<meta name="twitter:image" content="https://ketogenicresearch.org/logo-ketogenic-research.png">'
    )
    s = replace_once(s, old_article, new_article, "article SEO/social metadata")

    old_index = (
        '<meta property="og:url" content="https://ketogenicresearch.org/articles.html">\n'
        '<link href="favicon.svg" rel="icon">'
    )
    new_index = (
        '<meta property="og:url" content="https://ketogenicresearch.org/articles.html">\n'
        '<meta property="og:image" content="https://ketogenicresearch.org/logo-ketogenic-research.png">\n'
        '<meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1">\n'
        '<meta name="twitter:card" content="summary_large_image">\n'
        '<meta name="twitter:title" content="Articles | Ketogenic Research">\n'
        '<meta name="twitter:description" content="Research notes and scientific analyses based on recent peer-reviewed ketogenic literature.">\n'
        '<meta name="twitter:image" content="https://ketogenicresearch.org/logo-ketogenic-research.png">\n'
        '<link href="favicon.svg" rel="icon">'
    )
    s = replace_once(s, old_index, new_index, "articles index SEO/social metadata")

    RENDER.write_text(s, encoding="utf-8")
    run(sys.executable, "-m", "py_compile", str(RENDER))
    run(sys.executable, "scripts/render_articles.py")

    if HOME.exists():
        h = HOME.read_text(encoding="utf-8")
        h = h.replace(
            "Un iniziativa di ricerca scientifica dedicato allo studio, alla valutazione critica e all'interpretazione clinica degli interventi chetogenici e metabolici.",
            "Un'iniziativa di ricerca scientifica dedicata allo studio, alla valutazione critica e all'interpretazione clinica degli interventi chetogenici e metabolici."
        )
        HOME.write_text(h, encoding="utf-8")

    rendered = sorted((ROOT / "articles").glob("*.html"))
    if not rendered:
        raise RuntimeError("No public article pages rendered")

    for p in rendered:
        text = p.read_text(encoding="utf-8")
        for required in (
            'data-lang="en"',
            'data-lang="it"',
            'data-article-lang="en"',
            'data-article-lang="it"',
            'property="og:image"',
            'name="twitter:image"',
        ):
            if required not in text:
                raise RuntimeError(f"{p.name}: missing {required}")

    print(f"Safe final polish completed for {len(rendered)} article pages; EN/IT translation buttons preserved.")

if __name__ == "__main__":
    main()
