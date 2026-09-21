#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
STYLES = ROOT / "styles.css"

DETAILS_BLOCK = """
<details class="nav-more">
  <summary>
    <span data-en="More" data-it="Altro">More</span>
    <span class="nav-caret" aria-hidden="true">&#9662;</span>
  </summary>
  <div class="nav-submenu">
    <a data-en="Methodology" data-it="Metodologia" href="methodology.html">Methodology</a>
    <a data-en="Contact" data-it="Contatti" href="contact.html">Contact</a>
  </div>
</details>
"""

CSS = """
/* Native More menu: reliable on mobile without JavaScript */
.nav-more{position:relative}
.nav-more summary{
  list-style:none;
  display:flex;
  align-items:center;
  gap:.35rem;
  cursor:pointer;
  font-weight:600;
  padding:.65rem 0;
  white-space:nowrap;
}
.nav-more summary::-webkit-details-marker{display:none}
.nav-more[open] .nav-caret{transform:rotate(180deg)}
.nav-more .nav-caret{font-size:.72em;transition:transform .18s ease}
.nav-more .nav-submenu{
  position:absolute;
  top:calc(100% + .35rem);
  right:0;
  min-width:210px;
  padding:.45rem;
  background:#fff;
  border:1px solid rgba(36,71,99,.15);
  border-radius:12px;
  box-shadow:0 12px 32px rgba(26,54,78,.13);
  z-index:1000;
}
.nav-more .nav-submenu a{
  display:block;
  padding:.72rem .85rem;
  border-radius:8px;
  color:#173b5c;
  text-decoration:none;
  font-weight:600;
}
.nav-more .nav-submenu a:hover,
.nav-more .nav-submenu a:focus{background:#f1f6f9}

@media(max-width:900px){
  .nav-more{width:100%}
  .nav-more summary{
    width:100%;
    justify-content:space-between;
    padding:.78rem .2rem;
  }
  .nav-more .nav-submenu{
    position:static;
    min-width:0;
    box-shadow:none;
    border:0;
    border-left:2px solid #d8e4eb;
    border-radius:0;
    margin:0 0 .35rem .35rem;
    padding:.1rem 0 .1rem .65rem;
    background:transparent;
  }
}
"""

def patch_html(path: Path):
    text = path.read_text(encoding="utf-8")
    m = re.search(r'<nav[^>]*class="site-nav"[^>]*>.*?</nav>', text, flags=re.S|re.I)
    if not m:
        return False

    nav = m.group(0)
    if 'class="nav-more"' in nav:
        return False

    # Replace the old More dropdown block.
    pattern = re.compile(
        r'<div class="nav-group">\s*'
        r'<button class="nav-parent"[^>]*>.*?</button>\s*'
        r'<div class="nav-submenu">.*?</div>\s*'
        r'</div>',
        flags=re.S|re.I
    )
    new_nav, n = pattern.subn(DETAILS_BLOCK, nav, count=1)
    if not n:
        print(f"SKIP: {path.name}")
        return False

    # Ensure Latest Evidence is a top-level item.
    nav_without_more = re.sub(r'<details class="nav-more">.*?</details>', '', new_nav, flags=re.S)
    if 'href="latest.html"' not in nav_without_more:
        latest = '<a data-en="Latest Evidence" data-it="Ultime evidenze" href="latest.html">Latest Evidence</a>\n'
        if '<a data-en="Evidence Trends"' in new_nav:
            new_nav = new_nav.replace('<a data-en="Evidence Trends"', latest + '<a data-en="Evidence Trends"', 1)

    text = text[:m.start()] + new_nav + text[m.end():]

    # Remove old dropdown JS that can interfere.
    text = re.sub(r'<script id="kr-dropdown-nav">.*?</script>\s*', '', text, flags=re.S|re.I)
    text = re.sub(r'<script id="kr-research-nav">.*?</script>\s*', '', text, flags=re.S|re.I)

    path.write_text(text, encoding="utf-8")
    print(f"Patched: {path.name}")
    return True

def main():
    changed = 0
    for path in sorted(ROOT.glob("*.html")):
        if patch_html(path):
            changed += 1

    css = STYLES.read_text(encoding="utf-8")
    if "/* Native More menu: reliable on mobile without JavaScript */" not in css:
        css += "\n\n" + CSS.strip() + "\n"
        STYLES.write_text(css, encoding="utf-8")

    print(f"Pages updated: {changed}")

if __name__ == "__main__":
    main()
