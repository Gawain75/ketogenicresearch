#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
STYLES = ROOT / "styles.css"

SECTION = r"""
<section class="section home-latest-evidence" id="home-latest-evidence">
<div class="wrap">
  <div class="home-latest-heading">
    <div>
      <p class="kicker" data-en="LATEST EVIDENCE" data-it="ULTIME EVIDENZE">LATEST EVIDENCE</p>
      <h2 data-en="Recently indexed scientific literature" data-it="Letteratura scientifica indicizzata di recente">Recently indexed scientific literature</h2>
      <p data-en="A live view of recent PubMed-indexed publications in ketogenic and metabolic research."
         data-it="Una vista aggiornata delle pubblicazioni recenti indicizzate in PubMed nella ricerca chetogenica e metabolica.">
         A live view of recent PubMed-indexed publications in ketogenic and metabolic research.
      </p>
    </div>
    <div class="home-latest-meta">
      <strong id="homeLatestUpdated">—</strong>
      <span data-en="last literature update" data-it="ultimo aggiornamento">last literature update</span>
    </div>
  </div>

  <div class="home-latest-grid" id="homeLatestGrid">
    <p data-en="Loading recent evidence…" data-it="Caricamento delle evidenze recenti…">Loading recent evidence…</p>
  </div>

  <div class="home-latest-actions">
    <a class="btn-primary" href="latest.html" data-en="View all Latest Evidence" data-it="Vedi tutte le ultime evidenze">View all Latest Evidence</a>
    <a class="btn-secondary" href="https://library.ketogenicresearch.org/library" data-en="Scientific Library" data-it="Biblioteca Scientifica">Scientific Library</a>
  </div>
</div>
</section>
"""

JS = r"""
<script id="kr-home-latest-evidence">
(function(){
  function esc(value){
    return String(value == null ? "" : value).replace(/[&<>"']/g,function(ch){
      return {"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#039;"}[ch];
    });
  }

  function currentLang(){
    return document.documentElement.lang === "it" ? "it" : "en";
  }

  function dateLabel(value){
    if(!value) return "—";
    var lang = currentLang() === "it" ? "it-IT" : "en-GB";
    var d = new Date(value.slice(0,10) + "T00:00:00Z");
    if(isNaN(d.getTime())) return value.slice(0,10);
    return new Intl.DateTimeFormat(lang,{
      year:"numeric",month:"short",day:"2-digit",timeZone:"UTC"
    }).format(d);
  }

  function render(data){
    var host = document.getElementById("homeLatestGrid");
    if(!host) return;

    var rows = (data.publications || []).slice(0,5);
    var lang = currentLang();

    if(!rows.length){
      host.innerHTML = '<p>' + (lang === "it"
        ? "Nessuna pubblicazione recente disponibile."
        : "No recent publications available.") + '</p>';
      return;
    }

    host.innerHTML = rows.map(function(p){
      var evidence = lang === "it"
        ? (p.evidence_type_it || p.evidence_type || "")
        : (p.evidence_type || "");

      var area = (p.areas || [])[0] || "";
      var url = p.pubmed_url || p.doi_url || p.pmc_url || "latest.html";

      return '<article class="home-latest-card">' +
        '<div class="home-latest-card-top">' +
          '<time>' + esc(dateLabel(p.date || "")) + '</time>' +
          (evidence ? '<span class="home-latest-evidence-chip">' + esc(evidence) + '</span>' : '') +
        '</div>' +
        '<h3><a href="' + esc(url) + '" target="_blank" rel="noopener">' + esc(p.title || "") + '</a></h3>' +
        '<p class="home-latest-journal">' + esc(p.journal || "") + (p.year ? " · " + esc(p.year) : "") + '</p>' +
        (area ? '<p class="home-latest-area">' + esc(area) + '</p>' : '') +
      '</article>';
    }).join("");

    var updated = document.getElementById("homeLatestUpdated");
    if(updated){
      updated.textContent = data.generated_at ? dateLabel(data.generated_at) : "—";
    }
  }

  function load(){
    if(!document.getElementById("homeLatestGrid")) return;
    fetch("latest-publications.json?v=70",{cache:"no-store"})
      .then(function(r){ if(!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(render)
      .catch(function(){
        var host = document.getElementById("homeLatestGrid");
        if(host){
          host.innerHTML = '<p>' + (currentLang() === "it"
            ? "Le ultime evidenze non sono disponibili in questo momento."
            : "Latest Evidence is temporarily unavailable.") + '</p>';
        }
      });
  }

  if(document.readyState === "loading"){
    document.addEventListener("DOMContentLoaded", load);
  }else{
    load();
  }

  document.querySelectorAll("[data-lang]").forEach(function(btn){
    btn.addEventListener("click",function(){ setTimeout(load,50); });
  });
})();
</script>
"""

CSS = r"""
/* Latest Evidence on homepage */
.home-latest-evidence{background:linear-gradient(180deg,#f7fafc 0%,#fff 100%)}
.home-latest-heading{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:24px;align-items:end;margin-bottom:24px}
.home-latest-heading h2{margin-bottom:.55rem}
.home-latest-heading p{max-width:760px}
.home-latest-meta{min-width:150px;text-align:right}
.home-latest-meta strong{display:block;color:#173b5c;font-size:1.05rem}
.home-latest-meta span{display:block;color:#637484;font-size:.82rem;margin-top:4px}
.home-latest-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}
.home-latest-card{background:#fff;border:1px solid #dbe4ec;border-radius:14px;padding:18px;min-width:0}
.home-latest-card:nth-child(n+4){grid-column:span 1}
.home-latest-card-top{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px}
.home-latest-card time{font-size:.82rem;color:#607385}
.home-latest-evidence-chip{font-size:.72rem;font-weight:700;padding:.28rem .48rem;border-radius:999px;background:#edf5f7;color:#28596b}
.home-latest-card h3{font-size:1rem;line-height:1.35;margin:.3rem 0 .6rem}
.home-latest-card h3 a{color:#173b5c;text-decoration:none}
.home-latest-card h3 a:hover{text-decoration:underline}
.home-latest-journal{font-size:.86rem;color:#5c6e7e;margin:.2rem 0}
.home-latest-area{font-size:.82rem;color:#1f6f8b;font-weight:700;margin:.55rem 0 0}
.home-latest-actions{display:flex;gap:12px;flex-wrap:wrap;margin-top:24px}
@media(max-width:900px){.home-latest-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:640px){
  .home-latest-heading{grid-template-columns:1fr}
  .home-latest-meta{text-align:left}
  .home-latest-grid{grid-template-columns:1fr}
}
"""

def main():
    html = INDEX.read_text(encoding="utf-8")

    if 'id="home-latest-evidence"' not in html:
        marker = '<section class="section" id="scientific-direction-home">'
        if marker in html:
            html = html.replace(marker, SECTION + "\n" + marker, 1)
        else:
            html = html.replace("</main>", SECTION + "\n</main>", 1)

    if 'id="kr-home-latest-evidence"' not in html:
        html = html.replace("</body>", JS + "\n</body>", 1)

    INDEX.write_text(html, encoding="utf-8")

    css = STYLES.read_text(encoding="utf-8")
    if "/* Latest Evidence on homepage */" not in css:
        css += "\n\n" + CSS.strip() + "\n"
        STYLES.write_text(css, encoding="utf-8")

    print("Latest Evidence section added to homepage.")

if __name__ == "__main__":
    main()
