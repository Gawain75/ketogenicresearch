#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
STYLES = ROOT / "styles.css"

NAV = r'''
<nav class="site-nav" aria-label="Primary navigation">
  <a href="index.html">Home</a>
  <a data-en="Research" data-it="Ricerca" href="research.html">Research</a>
  <a data-en="Scientific Library" data-it="Biblioteca Scientifica" href="https://library.ketogenicresearch.org">Scientific Library</a>
  <a data-en="Latest Evidence" data-it="Ultime evidenze" href="latest.html">Latest Evidence</a>
  <a data-en="Evidence Trends" data-it="Andamento evidenze" href="evidence-trends.html">Evidence Trends</a>
  <a data-en="Articles" data-it="Articoli" href="articles.html">Articles</a>
  <a data-en="Scientific Direction" data-it="Direzione scientifica" href="director.html">Scientific Direction</a>
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
</nav>
'''

CSS = r'''
/* FORCE-NATIVE-MORE-MENU */
.nav-more{position:relative}
.nav-more summary{
  list-style:none;
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:.35rem;
  cursor:pointer;
  font-weight:600;
  padding:.65rem 0;
  white-space:nowrap;
}
.nav-more summary::-webkit-details-marker{display:none}
.nav-more .nav-caret{font-size:.72em;transition:transform .18s ease}
.nav-more[open] .nav-caret{transform:rotate(180deg)}
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
'''

def patch_html(path: Path):
    text = path.read_text(encoding="utf-8")

    new_text, n = re.subn(
        r'<nav\b[^>]*>.*?</nav>',
        NAV,
        text,
        count=1,
        flags=re.S | re.I
    )

    if not n:
        print(f"NO NAV FOUND: {path.name}")
        return False

    new_text = re.sub(
        r'<script[^>]*id="(?:kr-dropdown-nav|kr-research-nav)"[^>]*>.*?</script>\s*',
        '',
        new_text,
        flags=re.S | re.I
    )

    path.write_text(new_text, encoding="utf-8")
    print(f"FORCED NAV REPLACEMENT: {path.name}")
    return True

def main():
    changed = 0
    for path in sorted(ROOT.glob("*.html")):
        if patch_html(path):
            changed += 1

    css = STYLES.read_text(encoding="utf-8")
    if "/* FORCE-NATIVE-MORE-MENU */" not in css:
        css += "\n\n" + CSS.strip() + "\n"
        STYLES.write_text(css, encoding="utf-8")
        print("Added native More CSS.")
    else:
        print("Native More CSS already present.")

    print(f"TOTAL HTML PAGES REWRITTEN: {changed}")

if __name__ == "__main__":
    main()
