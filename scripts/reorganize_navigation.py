#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
STYLES = ROOT / "styles.css"

NAV_HTML = r'''
<nav class="site-nav" aria-label="Primary navigation">
<a href="index.html">Home</a>

<div class="nav-group">
<button class="nav-parent" type="button" aria-expanded="false">
<span data-en="Research" data-it="Ricerca">Research</span>
<span class="nav-caret" aria-hidden="true">&#9662;</span>
</button>
<div class="nav-submenu">
<a data-en="Research Areas" data-it="Aree di ricerca" href="research.html">Research Areas</a>
<a data-en="Evidence Trends" data-it="Andamento evidenze" href="evidence-trends.html">Evidence Trends</a>
</div>
</div>

<div class="nav-group">
<button class="nav-parent" type="button" aria-expanded="false">
<span data-en="Evidence" data-it="Evidenze">Evidence</span>
<span class="nav-caret" aria-hidden="true">&#9662;</span>
</button>
<div class="nav-submenu">
<a data-en="Scientific Library" data-it="Biblioteca Scientifica" href="library.html">Scientific Library</a>
<a data-en="Latest Evidence" data-it="Ultime pubblicazioni" href="latest.html">Latest Evidence</a>
</div>
</div>

<a data-en="Articles" data-it="Articoli" href="articles.html">Articles</a>
<a data-en="Scientific Direction" data-it="Direzione scientifica" href="director.html">Scientific Direction</a>

<div class="nav-group">
<button class="nav-parent" type="button" aria-expanded="false">
<span data-en="About" data-it="Informazioni">About</span>
<span class="nav-caret" aria-hidden="true">&#9662;</span>
</button>
<div class="nav-submenu">
<a data-en="Methodology" data-it="Metodologia" href="methodology.html">Methodology</a>
<a data-en="Contact" data-it="Contatti" href="contact.html">Contact</a>
</div>
</div>
</nav>
'''

CSS = r'''
/* Institutional primary navigation */
.site-nav{
  display:flex;
  align-items:center;
  gap:1.15rem;
}
.site-nav>a,
.nav-parent{
  appearance:none;
  border:0;
  background:transparent;
  color:inherit;
  font:inherit;
  font-weight:600;
  text-decoration:none;
  cursor:pointer;
  padding:.65rem 0;
  white-space:nowrap;
}
.nav-group{position:relative}
.nav-parent{display:flex;align-items:center;gap:.35rem}
.nav-caret{font-size:.72em;transition:transform .18s ease}
.nav-submenu{
  position:absolute;
  top:calc(100% + .35rem);
  left:50%;
  transform:translateX(-50%) translateY(-4px);
  min-width:220px;
  padding:.45rem;
  background:#fff;
  border:1px solid rgba(36,71,99,.15);
  border-radius:12px;
  box-shadow:0 12px 32px rgba(26,54,78,.13);
  opacity:0;
  visibility:hidden;
  pointer-events:none;
  transition:opacity .16s ease,transform .16s ease,visibility .16s ease;
  z-index:1000;
}
.nav-submenu a{
  display:block;
  padding:.72rem .85rem;
  border-radius:8px;
  color:#173b5c;
  text-decoration:none;
  font-weight:600;
  line-height:1.25;
}
.nav-submenu a:hover,
.nav-submenu a:focus{background:#f1f6f9}
.nav-group:hover .nav-submenu,
.nav-group:focus-within .nav-submenu,
.nav-group.open .nav-submenu{
  opacity:1;
  visibility:visible;
  pointer-events:auto;
  transform:translateX(-50%) translateY(0);
}
.nav-group.open .nav-caret{transform:rotate(180deg)}

@media(max-width:900px){
  .site-nav{
    display:none;
    position:absolute;
    top:100%;
    left:0;
    right:0;
    padding:1rem 1.1rem 1.25rem;
    background:#fff;
    border-top:1px solid rgba(36,71,99,.12);
    box-shadow:0 14px 28px rgba(26,54,78,.10);
    flex-direction:column;
    align-items:stretch;
    gap:.15rem;
    z-index:999;
  }
  .site-nav.open{display:flex}
  .site-nav>a,
  .nav-parent{width:100%;padding:.78rem .2rem}
  .nav-parent{justify-content:space-between}
  .nav-group{width:100%}
  .nav-submenu{
    position:static;
    transform:none !important;
    min-width:0;
    box-shadow:none;
    border:0;
    border-left:2px solid #d8e4eb;
    border-radius:0;
    margin:0 0 .35rem .35rem;
    padding:.1rem 0 .1rem .65rem;
    display:none;
    opacity:1;
    visibility:visible;
    pointer-events:auto;
    background:transparent;
  }
  .nav-group.open .nav-submenu{display:block}
}
'''

JS = r'''
<script id="kr-dropdown-nav">
(function(){
  function bindNavigation(){
    document.querySelectorAll(".nav-parent").forEach(function(btn){
      btn.addEventListener("click",function(ev){
        var group=btn.closest(".nav-group");
        if(!group)return;
        document.querySelectorAll(".nav-group.open").forEach(function(other){
          if(other!==group){
            other.classList.remove("open");
            var ob=other.querySelector(".nav-parent");
            if(ob)ob.setAttribute("aria-expanded","false");
          }
        });
        var open=group.classList.toggle("open");
        btn.setAttribute("aria-expanded",open?"true":"false");
        ev.stopPropagation();
      });
    });
    document.addEventListener("click",function(){
      document.querySelectorAll(".nav-group.open").forEach(function(group){
        group.classList.remove("open");
        var btn=group.querySelector(".nav-parent");
        if(btn)btn.setAttribute("aria-expanded","false");
      });
    });
    document.querySelectorAll(".nav-submenu").forEach(function(menu){
      menu.addEventListener("click",function(ev){ev.stopPropagation()});
    });
  }
  if(document.readyState==="loading"){
    document.addEventListener("DOMContentLoaded",bindNavigation);
  }else{
    bindNavigation();
  }
})();
</script>
'''

def patch_html(path: Path):
    text = path.read_text(encoding="utf-8")
    new_text, count = re.subn(
        r'<nav(?:\s+class="[^"]*")?>.*?</nav>',
        NAV_HTML,
        text,
        count=1,
        flags=re.S
    )
    if not count:
        print(f"SKIP nav not found: {path.name}")
        return False

    if 'id="kr-dropdown-nav"' not in new_text:
        if "</body>" in new_text:
            new_text = new_text.replace("</body>", JS + "\n</body>", 1)
        else:
            new_text += JS

    path.write_text(new_text, encoding="utf-8")
    print(f"Updated navigation: {path.name}")
    return True

def main():
    changed = 0
    for path in sorted(ROOT.glob("*.html")):
        if patch_html(path):
            changed += 1

    if not STYLES.exists():
        raise RuntimeError("styles.css not found")

    css = STYLES.read_text(encoding="utf-8")
    if "/* Institutional primary navigation */" not in css:
        css += "\n\n" + CSS.strip() + "\n"
        STYLES.write_text(css, encoding="utf-8")
        print("Navigation styles added.")
    else:
        print("Navigation styles already present.")

    print(f"Pages updated: {changed}")

if __name__ == "__main__":
    main()
