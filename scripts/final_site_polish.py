#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RENDER = ROOT / 'scripts' / 'render_articles.py'
HOME = ROOT / 'index.html'

def run(*args):
    subprocess.run(args, cwd=ROOT, check=True)

def replace_once(s, old, new, label):
    if new in s:
        return s
    if old not in s:
        raise RuntimeError(f'Cannot find expected block for {label}')
    return s.replace(old, new, 1)

def main():
    s = RENDER.read_text(encoding='utf-8')

    s = replace_once(
        s,
        '''        if line.startswith("# "):\n            flush()\n            if not title:\n                title = line[2:].strip()\n            out.append(f"<h1>{md_inline(line[2:].strip())}</h1>")''',
        '''        if line.startswith("# "):\n            flush()\n            if not title:\n                title = line[2:].strip()\n            # H1 is rendered once outside the language-specific sections.''',
        'markdown H1 renderer',
    )

    s = replace_once(
        s,
        '''<meta property="og:url" content="https://ketogenicresearch.org/articles/{html.escape(slug)}.html">\n<meta name="twitter:card" content="summary">\n<meta name="twitter:title" content="{html.escape(en_title, quote=True)}">\n<meta name="twitter:description" content="{html.escape(description, quote=True)}">''',
        '''<meta property="og:url" content="https://ketogenicresearch.org/articles/{html.escape(slug)}.html">\n<meta property="og:image" content="https://ketogenicresearch.org/logo-ketogenic-research.png">\n<meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1">\n<meta name="twitter:card" content="summary_large_image">\n<meta name="twitter:title" content="{html.escape(en_title, quote=True)}">\n<meta name="twitter:description" content="{html.escape(description, quote=True)}">\n<meta name="twitter:image" content="https://ketogenicresearch.org/logo-ketogenic-research.png">''',
        'article SEO block',
    )

    s = replace_once(
        s,
        '''<main class="article-shell">\n  <a class="article-back" href="../articles.html">&larr; <span data-label-en="Articles" data-label-it="Articoli">Articles</span></a>\n  <section class="article-language active" data-article-lang="en">''',
        '''<main class="article-shell">\n  <a class="article-back" href="../articles.html">&larr; <span data-label-en="Articles" data-label-it="Articoli">Articles</span></a>\n  <h1 class="article-main-title"\n      data-title-en="{html.escape(en_title, quote=True)}"\n      data-title-it="{html.escape(it_title or en_title, quote=True)}">{html.escape(en_title)}</h1>\n  <section class="article-language active" data-article-lang="en">''',
        'shared bilingual H1',
    )

    s = replace_once(
        s,
        '''  const sections=[...document.querySelectorAll('[data-article-lang]')];\n  const back=document.querySelector('[data-label-en]');\n  function setLang(lang){{\n    document.documentElement.lang=lang;\n    buttons.forEach(b=>b.classList.toggle('active',b.dataset.lang===lang));\n    sections.forEach(s=>s.classList.toggle('active',s.dataset.articleLang===lang));\n    if(back) back.textContent=lang==='it'?back.dataset.labelIt:back.dataset.labelEn;''',
        '''  const sections=[...document.querySelectorAll('[data-article-lang]')];\n  const back=document.querySelector('[data-label-en]');\n  const title=document.querySelector('[data-title-en]');\n  function setLang(lang){{\n    document.documentElement.lang=lang;\n    buttons.forEach(b=>b.classList.toggle('active',b.dataset.lang===lang));\n    sections.forEach(s=>s.classList.toggle('active',s.dataset.articleLang===lang));\n    if(back) back.textContent=lang==='it'?back.dataset.labelIt:back.dataset.labelEn;\n    if(title) title.textContent=lang==='it'?title.dataset.titleIt:title.dataset.titleEn;''',
        'bilingual H1 switch',
    )

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

    s = replace_once(
        s,
        '''<meta property="og:url" content="https://ketogenicresearch.org/articles.html">\n<link href="favicon.svg" rel="icon">''',
        '''<meta property="og:url" content="https://ketogenicresearch.org/articles.html">\n<meta property="og:image" content="https://ketogenicresearch.org/logo-ketogenic-research.png">\n<meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1">\n<meta name="twitter:card" content="summary_large_image">\n<meta name="twitter:title" content="Articles | Ketogenic Research">\n<meta name="twitter:description" content="Research notes and scientific analyses based on recent peer-reviewed ketogenic literature.">\n<meta name="twitter:image" content="https://ketogenicresearch.org/logo-ketogenic-research.png">\n<link href="favicon.svg" rel="icon">''',
        'articles index SEO',
    )

    RENDER.write_text(s, encoding='utf-8')
    run(sys.executable, '-m', 'py_compile', str(RENDER))
    run(sys.executable, 'scripts/render_articles.py')

    pages = list((ROOT / 'articles').glob('*.html'))
    if not pages:
        raise RuntimeError('No public article pages rendered')
    for p in pages:
        txt = p.read_text(encoding='utf-8')
        if txt.lower().count('<h1') != 1:
            raise RuntimeError(f'{p.name}: expected exactly one H1')
        if 'property="og:image"' not in txt:
            raise RuntimeError(f'{p.name}: og:image missing')
        if 'name="twitter:image"' not in txt:
            raise RuntimeError(f'{p.name}: twitter:image missing')

    if HOME.exists():
        h = HOME.read_text(encoding='utf-8')
        h = h.replace(
            "Un iniziativa di ricerca scientifica dedicato allo studio, alla valutazione critica e all'interpretazione clinica degli interventi chetogenici e metabolici.",
            "Un'iniziativa di ricerca scientifica dedicata allo studio, alla valutazione critica e all'interpretazione clinica degli interventi chetogenici e metabolici."
        )
        HOME.write_text(h, encoding='utf-8')

    print(f'Final polish completed for {len(pages)} article pages.')

if __name__ == '__main__':
    main()
