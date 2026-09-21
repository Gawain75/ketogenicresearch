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

def patch_renderer():
    lines = RENDER.read_text(encoding="utf-8").splitlines()
    out = []

    have_shared_h1 = any('class="article-main-title"' in x for x in lines)
    have_title_js = any("const title=document.querySelector('[data-title-en]');" in x for x in lines)
    have_title_switch = any("if(title) title.textContent=" in x for x in lines)
    have_article_og_image = False
    have_index_og_image = False

    for i, line in enumerate(lines):
        # Remove H1 generation from each language-specific markdown block.
        if 'out.append(f"<h1>{md_inline(line[2:].strip())}</h1>")' in line:
            out.append('            # H1 rendered once by article_page(), outside language sections.')
            continue

        # Expand type-line cleanup to Research Analysis / Analisi di ricerca too.
        if "en_html = re.sub(r'<p><strong>Research Note</strong></p>'" in line:
            out.append("        en_html = re.sub(r'<p><strong>Research (?:Note|Analysis)</strong></p>', '', en_html, count=1)")
            continue
        if "it_html = re.sub(r'<p><strong>Nota di ricerca</strong></p>'" in line:
            out.append("        it_html = re.sub(r'<p><strong>(?:Nota di ricerca|Analisi di ricerca)</strong></p>', '', it_html, count=1)")
            continue

        out.append(line)

        # Insert one shared bilingual H1 after the back link.
        if (not have_shared_h1 and
            '<a class="article-back" href="../articles.html"' in line):
            out.extend([
                '  <h1 class="article-main-title"',
                '      data-title-en="{html.escape(en_title, quote=True)}"',
                '      data-title-it="{html.escape(it_title or en_title, quote=True)}">{html.escape(en_title)}</h1>',
            ])
            have_shared_h1 = True

        # Shared H1 follows language switch.
        if (not have_title_js and
            "const back=document.querySelector('[data-label-en]');" in line):
            out.append("  const title=document.querySelector('[data-title-en]');")
            have_title_js = True

        if (not have_title_switch and
            "if(back) back.textContent=lang==='it'?back.dataset.labelIt:back.dataset.labelEn;" in line):
            out.append("    if(title) title.textContent=lang==='it'?title.dataset.titleIt:title.dataset.titleEn;")
            have_title_switch = True

        # Article-page SEO/social additions.
        if ('<meta property="og:url" content="https://ketogenicresearch.org/articles/{html.escape(slug)}.html">' in line):
            have_article_og_image = any(
                'property="og:image"' in x
                for x in lines[max(0, i-8):min(len(lines), i+10)]
            )
            if not have_article_og_image:
                out.extend([
                    '<meta property="og:image" content="https://ketogenicresearch.org/logo-ketogenic-research.png">',
                    '<meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1">',
                ])
                have_article_og_image = True

        # Articles-index SEO/social additions.
        if '<meta property="og:url" content="https://ketogenicresearch.org/articles.html">' in line:
            have_index_og_image = any(
                'property="og:image"' in x
                for x in lines[max(0, i-8):min(len(lines), i+12)]
            )
            if not have_index_og_image:
                out.extend([
                    '<meta property="og:image" content="https://ketogenicresearch.org/logo-ketogenic-research.png">',
                    '<meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1">',
                    '<meta name="twitter:card" content="summary_large_image">',
                    '<meta name="twitter:title" content="Articles | Ketogenic Research">',
                    '<meta name="twitter:description" content="Research notes and scientific analyses based on recent peer-reviewed ketogenic literature.">',
                    '<meta name="twitter:image" content="https://ketogenicresearch.org/logo-ketogenic-research.png">',
                ])
                have_index_og_image = True

    # Second pass for article-specific Twitter tags, because they already exist.
    final = []
    in_article_page_head = False
    twitter_image_added = False
    for line in out:
        if '<meta property="og:url" content="https://ketogenicresearch.org/articles/{html.escape(slug)}.html">' in line:
            in_article_page_head = True

        if in_article_page_head and '<meta name="twitter:card" content="summary">' in line:
            line = line.replace('content="summary"', 'content="summary_large_image"')

        final.append(line)

        if (in_article_page_head and
            '<meta name="twitter:description" content="{html.escape(description, quote=True)}">' in line and
            not twitter_image_added):
            final.append('<meta name="twitter:image" content="https://ketogenicresearch.org/logo-ketogenic-research.png">')
            twitter_image_added = True

        if in_article_page_head and '<link href="../favicon.svg" rel="icon">' in line:
            in_article_page_head = False

    RENDER.write_text("\n".join(final) + "\n", encoding="utf-8")

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
    run(sys.executable, "scripts/render_articles.py")

    pages = sorted((ROOT / "articles").glob("*.html"))
    if not pages:
        raise RuntimeError("No public article pages rendered")

    for p in pages:
        text = p.read_text(encoding="utf-8")
        h1_count = len(re.findall(r"<h1\b", text, flags=re.I))
        if h1_count != 1:
            raise RuntimeError(f"{p.name}: expected exactly one H1, found {h1_count}")
        if 'property="og:image"' not in text:
            raise RuntimeError(f"{p.name}: og:image missing")
        if 'name="twitter:image"' not in text:
            raise RuntimeError(f"{p.name}: twitter:image missing")

    index = (ROOT / "articles.html").read_text(encoding="utf-8")
    if 'property="og:image"' not in index:
        raise RuntimeError("articles.html: og:image missing")
    if 'name="twitter:image"' not in index:
        raise RuntimeError("articles.html: twitter:image missing")

    print(f"Final site polish passed for {len(pages)} article pages.")

def main():
    patch_renderer()
    patch_home()
    verify()

if __name__ == "__main__":
    main()
