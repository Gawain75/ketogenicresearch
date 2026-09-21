#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
STYLES = ROOT / "styles.css"
RESEARCH = ROOT / "research.html"

NAV_HTML = """
<nav class="site-nav" aria-label="Primary navigation">
  <a href="index.html">Home</a>
  <a class="nav-priority" data-en="Research" data-it="Ricerca" href="research.html">Research</a>
  <a class="nav-priority" data-en="Scientific Library" data-it="Biblioteca Scientifica" href="https://library.ketogenicresearch.org/library">Scientific Library</a>
  <a data-en="Evidence Trends" data-it="Andamento evidenze" href="evidence-trends.html">Evidence Trends</a>
  <a data-en="Articles" data-it="Articoli" href="articles.html">Articles</a>
  <a data-en="Scientific Direction" data-it="Direzione scientifica" href="director.html">Scientific Direction</a>
  <div class="nav-group">
    <button class="nav-parent" type="button" aria-expanded="false">
      <span data-en="More" data-it="Altro">More</span>
      <span class="nav-caret" aria-hidden="true">&#9662;</span>
    </button>
    <div class="nav-submenu">
      <a data-en="Latest Evidence" data-it="Ultime pubblicazioni" href="latest.html">Latest Evidence</a>
      <a data-en="Methodology" data-it="Metodologia" href="methodology.html">Methodology</a>
      <a data-en="Contact" data-it="Contatti" href="contact.html">Contact</a>
    </div>
  </div>
</nav>
"""

AREA_BLOCK = """
<section class="section research-taxonomy" id="research-taxonomy">
<div class="wrap">
  <p class="kicker" data-en="RESEARCH CLASSIFICATION" data-it="CLASSIFICAZIONE DELLA RICERCA">RESEARCH CLASSIFICATION</p>
  <h2 data-en="Clinical areas organized into research domains" data-it="Aree cliniche organizzate in domini di ricerca">Clinical areas organized into research domains</h2>
  <p class="lead"
     data-en="Detailed clinical areas remain available in the Scientific Library. Here they are grouped into broader research domains to make the scientific structure easier to understand."
     data-it="Le singole aree cliniche restano disponibili nella Biblioteca Scientifica. Qui vengono raggruppate in domini di ricerca più ampi per rendere più chiara la struttura scientifica.">
     Detailed clinical areas remain available in the Scientific Library. Here they are grouped into broader research domains to make the scientific structure easier to understand.
  </p>

  <div class="research-domain-grid">
    <article class="research-domain">
      <h3 data-en="Neurology &amp; Brain Metabolism" data-it="Neurologia e metabolismo cerebrale">Neurology &amp; Brain Metabolism</h3>
      <p data-en="Epilepsy, GLUT1 deficiency, cognitive function, Alzheimer’s disease, Parkinson’s disease, migraine, neurotrauma, multiple sclerosis and autism."
         data-it="Epilessia, deficit di GLUT1, funzione cognitiva, malattia di Alzheimer, Parkinson, emicrania, neurotrauma, sclerosi multipla e autismo.">
         Epilepsy, GLUT1 deficiency, cognitive function, Alzheimer’s disease, Parkinson’s disease, migraine, neurotrauma, multiple sclerosis and autism.
      </p>
    </article>

    <article class="research-domain">
      <h3 data-en="Metabolic Health &amp; Endocrinology" data-it="Salute metabolica ed endocrinologia">Metabolic Health &amp; Endocrinology</h3>
      <p data-en="Obesity, diabetes, glucose metabolism, thyroid disorders, metabolic liver disease, PMOS/PCOS and other endocrine-metabolic conditions."
         data-it="Obesità, diabete, metabolismo glucidico, patologie tiroidee, malattia epatica metabolica, PMOS/PCOS e altre condizioni endocrino-metaboliche.">
         Obesity, diabetes, glucose metabolism, thyroid disorders, metabolic liver disease, PMOS/PCOS and other endocrine-metabolic conditions.
      </p>
    </article>

    <article class="research-domain">
      <h3 data-en="Body Composition, Muscle &amp; Performance" data-it="Composizione corporea, muscolo e performance">Body Composition, Muscle &amp; Performance</h3>
      <p data-en="Body composition, sarcopenia, skeletal muscle, exercise, performance and lean-mass preservation."
         data-it="Composizione corporea, sarcopenia, muscolo scheletrico, esercizio, performance e preservazione della massa magra.">
         Body composition, sarcopenia, skeletal muscle, exercise, performance and lean-mass preservation.
      </p>
    </article>

    <article class="research-domain">
      <h3 data-en="Cardiovascular &amp; Lipid Metabolism" data-it="Cardiovascolare e metabolismo lipidico">Cardiovascular &amp; Lipid Metabolism</h3>
      <p data-en="Cardiovascular health, dyslipidemia, lipid metabolism and Lipid Energy Model / LMHR."
         data-it="Salute cardiovascolare, dislipidemia, metabolismo lipidico e Lipid Energy Model / LMHR.">
         Cardiovascular health, dyslipidemia, lipid metabolism and Lipid Energy Model / LMHR.
      </p>
    </article>

    <article class="research-domain">
      <h3 data-en="Oncology &amp; Cancer Metabolism" data-it="Oncologia e metabolismo tumorale">Oncology &amp; Cancer Metabolism</h3>
      <p data-en="Tumor energetics, metabolic interventions in oncology and mechanistic cancer-metabolism research."
         data-it="Energetica tumorale, interventi metabolici in oncologia e ricerca meccanicistica sul metabolismo del cancro.">
         Tumor energetics, metabolic interventions in oncology and mechanistic cancer-metabolism research.
      </p>
    </article>

    <article class="research-domain">
      <h3 data-en="Inflammation &amp; Immunometabolism" data-it="Infiammazione e immunometabolismo">Inflammation &amp; Immunometabolism</h3>
      <p data-en="Inflammatory and immune-metabolic conditions, including rheumatoid arthritis, psoriasis and related disorders."
         data-it="Condizioni infiammatorie e immunometaboliche, comprese artrite reumatoide, psoriasi e patologie correlate.">
         Inflammatory and immune-metabolic conditions, including rheumatoid arthritis, psoriasis and related disorders.
      </p>
    </article>

    <article class="research-domain">
      <h3 data-en="Microbiome &amp; Nutritional Modulation" data-it="Microbioma e modulazione nutrizionale">Microbiome &amp; Nutritional Modulation</h3>
      <p data-en="Gut microbiome, mycobiome, MCT, exogenous ketones, supplementation and nutraceuticals."
         data-it="Microbioma intestinale, micobioma, MCT, chetoni esogeni, supplementazione e nutraceutici.">
         Gut microbiome, mycobiome, MCT, exogenous ketones, supplementation and nutraceuticals.
      </p>
    </article>

    <article class="research-domain">
      <h3 data-en="Renal, Reproductive &amp; Systemic Conditions" data-it="Condizioni renali, riproduttive e sistemiche">Renal, Reproductive &amp; Systemic Conditions</h3>
      <p data-en="Chronic kidney disease, ADPKD, reproduction and fertility, lipedema and other systemic applications."
         data-it="Malattia renale cronica, ADPKD, riproduzione e fertilità, lipedema e altre applicazioni sistemiche.">
         Chronic kidney disease, ADPKD, reproduction and fertility, lipedema and other systemic applications.
      </p>
    </article>
  </div>

  <div class="research-taxonomy-actions">
    <a class="btn-primary" href="https://library.ketogenicresearch.org/library" data-en="Explore all clinical areas" data-it="Esplora tutte le aree cliniche">Explore all clinical areas</a>
    <a class="btn-secondary" href="evidence-trends.html" data-en="View Evidence Trends" data-it="Vedi andamento evidenze">View Evidence Trends</a>
  </div>
</div>
</section>
"""

CSS = """
/* Research-first navigation */
.site-nav{display:flex;align-items:center;gap:1rem}
.site-nav>a,.nav-parent{appearance:none;border:0;background:transparent;color:inherit;font:inherit;font-weight:600;text-decoration:none;cursor:pointer;padding:.65rem 0;white-space:nowrap}
.site-nav .nav-priority{font-weight:800}
.nav-group{position:relative}
.nav-parent{display:flex;align-items:center;gap:.35rem}
.nav-caret{font-size:.72em}
.nav-submenu{position:absolute;top:calc(100% + .35rem);right:0;min-width:210px;padding:.45rem;background:#fff;border:1px solid rgba(36,71,99,.15);border-radius:12px;box-shadow:0 12px 32px rgba(26,54,78,.13);opacity:0;visibility:hidden;pointer-events:none;transform:translateY(-4px);transition:.16s ease;z-index:1000}
.nav-submenu a{display:block;padding:.72rem .85rem;border-radius:8px;color:#173b5c;text-decoration:none;font-weight:600}
.nav-submenu a:hover,.nav-submenu a:focus{background:#f1f6f9}
.nav-group:hover .nav-submenu,.nav-group:focus-within .nav-submenu,.nav-group.open .nav-submenu{opacity:1;visibility:visible;pointer-events:auto;transform:translateY(0)}

.research-domain-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin-top:26px}
.research-domain{border:1px solid #dbe4ec;border-radius:14px;background:#fff;padding:20px}
.research-domain h3{margin-top:0;color:#173b5c}
.research-domain p{margin-bottom:0;color:#526575}
.research-taxonomy-actions{display:flex;gap:12px;flex-wrap:wrap;margin-top:26px}

@media(max-width:900px){
  .site-nav{display:none;position:absolute;top:100%;left:0;right:0;padding:1rem 1.1rem 1.25rem;background:#fff;border-top:1px solid rgba(36,71,99,.12);box-shadow:0 14px 28px rgba(26,54,78,.10);flex-direction:column;align-items:stretch;gap:.1rem;z-index:999}
  .site-nav.open{display:flex}
  .site-nav>a,.nav-parent{width:100%;padding:.78rem .2rem}
  .nav-parent{justify-content:space-between}
  .nav-group{width:100%}
  .nav-submenu{position:static;min-width:0;box-shadow:none;border:0;border-left:2px solid #d8e4eb;border-radius:0;margin:0 0 .35rem .35rem;padding:.1rem 0 .1rem .65rem;display:none;opacity:1;visibility:visible;pointer-events:auto;background:transparent;transform:none}
  .nav-group.open .nav-submenu{display:block}
}
@media(max-width:720px){.research-domain-grid{grid-template-columns:1fr}}
"""

JS = """
<script id="kr-research-nav">
(function(){
  function bind(){
    document.querySelectorAll(".nav-parent").forEach(function(btn){
      btn.addEventListener("click",function(ev){
        var group=btn.closest(".nav-group");
        if(!group)return;
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
  }
  if(document.readyState==="loading"){document.addEventListener("DOMContentLoaded",bind)}else{bind()}
})();
</script>
"""

def patch_nav(path):
    text = path.read_text(encoding="utf-8")
    if 'class="site-nav"' in text:
        text = re.sub(r'<nav[^>]*class="site-nav"[^>]*>.*?</nav>', NAV_HTML, text, count=1, flags=re.S)
    else:
        text = re.sub(r'<nav[^>]*>.*?</nav>', NAV_HTML, text, count=1, flags=re.S)
    if 'id="kr-research-nav"' not in text:
        text = text.replace("</body>", JS + "\n</body>", 1)
    path.write_text(text, encoding="utf-8")

def main():
    for path in ROOT.glob("*.html"):
        patch_nav(path)

    if RESEARCH.exists():
        text = RESEARCH.read_text(encoding="utf-8")
        if 'id="research-taxonomy"' not in text:
            text = text.replace("</main>", AREA_BLOCK + "\n</main>", 1)
            RESEARCH.write_text(text, encoding="utf-8")

    css = STYLES.read_text(encoding="utf-8")
    if "/* Research-first navigation */" not in css:
        css += "\n\n" + CSS.strip() + "\n"
        STYLES.write_text(css, encoding="utf-8")

    print("Research navigation and classification updated.")

if __name__ == "__main__":
    main()
