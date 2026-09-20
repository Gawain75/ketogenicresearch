#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "index.html"

html = TARGET.read_text(encoding="utf-8")

replacements = {
    "Ketogenic Research Hub | Clinical &amp; Translational Ketogenic Research":
        "Ketogenic Research | Clinical &amp; Translational Research",
    "Ketogenic Research Hub | Ricerca sulla nutrizione chetogenica":
        "Ketogenic Research | Ricerca clinica e traslazionale",
    "Ketogenic Research Hub: clinical and translational research in ketogenic nutrition, VLCKD, metabolic health, body composition, neurology and incretin-based therapies.":
        "Clinical and translational research in ketogenic nutrition, metabolic health, body composition, neurology and related metabolic interventions.",
    '"@type": "ResearchOrganization"':
        '"@type": "Organization"',
    '"name": "Ketogenic Research Hub"':
        '"name": "Ketogenic Research"',
    "KETOGENIC RESEARCH HUB":
        "KETOGENIC RESEARCH",
    "© 2026 Ketogenic Research Hub":
        "© 2026 Ketogenic Research",
    'data-en="Transparent curation" data-it="Curatela trasparente">Transparent curation':
        'data-en="Evidence assessment" data-it="Valutazione delle evidenze">Evidence assessment',
    'data-en="Selection criteria, evidence hierarchy and link policy are documented separately." data-it="Criteri di selezione, gerarchia delle evidenze e criteri di collegamento bibliografico sono descritti nella sezione Metodologia.">Selection criteria, evidence hierarchy and link policy are documented separately.':
        'data-en="Selection criteria, study-design classification and bibliographic verification are documented in the scientific methodology." data-it="Criteri di selezione, classificazione del disegno degli studi e verifica bibliografica sono descritti nella metodologia scientifica.">Selection criteria, study-design classification and bibliographic verification are documented in the scientific methodology.',
}
for old, new in replacements.items():
    html = html.replace(old, new)

html = re.sub(
    r'<h1 data-en="Clinical and translational research in ketogenic metabolism\.".*?</h1>',
    '<h1 data-en="Ketogenic and metabolic research, from evidence to clinical interpretation." data-it="Ricerca chetogenica e metabolica, dalle evidenze all’interpretazione clinica.">Ketogenic and metabolic research, from evidence to clinical interpretation.</h1>',
    html,
    count=1,
    flags=re.S
)

html = re.sub(
    r'<p class="lead clean-lead" data-en="A scientific research initiative dedicated to metabolic health, clinical nutrition and evidence-based therapeutic applications of ketogenic strategies\.".*?</p>',
    '<p class="lead clean-lead" data-en="Clinical and translational work focused on ketogenic metabolism, metabolic health and clinical nutrition, supported by continuous literature surveillance and structured evidence assessment." data-it="Attività clinica e traslazionale focalizzata su metabolismo chetogenico, salute metabolica e nutrizione clinica, supportata da sorveglianza continua della letteratura e valutazione strutturata delle evidenze.">Clinical and translational work focused on ketogenic metabolism, metabolic health and clinical nutrition, supported by continuous literature surveillance and structured evidence assessment.</p>',
    html,
    count=1,
    flags=re.S
)

html = html.replace(
    '<a class="btn-primary" data-en="Research Areas" data-it="Aree di ricerca" href="research.html">Research Areas</a>',
    '<a class="btn-primary" data-en="Research Programs" data-it="Programmi di ricerca" href="research.html">Research Programs</a>'
)
html = html.replace(
    '<a class="btn-secondary" data-en="Scientific Direction" data-it="Direzione scientifica" href="director.html">Scientific Direction</a>',
    '<a class="btn-secondary" data-en="Scientific Method" data-it="Metodo scientifico" href="methodology.html">Scientific Method</a>',
    1
)

html = re.sub(
    r'<h2 data-en="Focused, rigorous and clinically oriented\.".*?</h2>\s*<p data-en="The Hub studies the role of ketogenic interventions.*?</p>',
    '<h2 data-en="A structured approach to ketogenic and metabolic evidence." data-it="Un approccio strutturato alle evidenze chetogeniche e metaboliche.">A structured approach to ketogenic and metabolic evidence.</h2><p data-en="Research questions are approached through literature surveillance, bibliographic verification, study-design classification and critical interpretation, with particular attention to clinical relevance and translational value." data-it="Le domande di ricerca vengono affrontate attraverso sorveglianza della letteratura, verifica bibliografica, classificazione del disegno degli studi e interpretazione critica, con particolare attenzione alla rilevanza clinica e al valore traslazionale.">Research questions are approached through literature surveillance, bibliographic verification, study-design classification and critical interpretation, with particular attention to clinical relevance and translational value.</p>',
    html,
    count=1,
    flags=re.S
)

activity = """
<section class="section scientific-activity" id="scientific-activity">
<div class="wrap">
<p class="kicker" data-en="SCIENTIFIC ACTIVITY" data-it="ATTIVITÀ SCIENTIFICA">SCIENTIFIC ACTIVITY</p>
<h2 data-en="Research, evidence surveillance and interpretation." data-it="Ricerca, sorveglianza delle evidenze e interpretazione.">Research, evidence surveillance and interpretation.</h2>
<div class="update-grid">
<a class="update-card" href="research.html">
<strong data-en="Research" data-it="Ricerca">Research</strong>
<span data-en="Clinical and translational questions" data-it="Domande cliniche e traslazionali">Clinical and translational questions</span>
<p data-en="Research areas organized around metabolic physiology, clinical nutrition and therapeutic applications of ketogenic strategies." data-it="Aree di ricerca organizzate attorno a fisiologia metabolica, nutrizione clinica e applicazioni terapeutiche delle strategie chetogeniche.">Research areas organized around metabolic physiology, clinical nutrition and therapeutic applications of ketogenic strategies.</p>
</a>
<a class="update-card" href="library.html">
<strong data-en="Evidence" data-it="Evidenze">Evidence</strong>
<span data-en="Scientific Library" data-it="Biblioteca Scientifica">Scientific Library</span>
<p data-en="A structured evidence map organized by clinical area and study design, with bibliographic identifiers verified against source records." data-it="Una mappa strutturata delle evidenze organizzata per area clinica e disegno dello studio, con identificatori bibliografici verificati sui record di origine.">A structured evidence map organized by clinical area and study design, with bibliographic identifiers verified against source records.</p>
</a>
<a class="update-card" href="latest.html">
<strong data-en="Surveillance" data-it="Sorveglianza">Surveillance</strong>
<span data-en="Latest Evidence" data-it="Ultime pubblicazioni">Latest Evidence</span>
<p data-en="Continuous monitoring of newly indexed literature to keep the evidence landscape current." data-it="Monitoraggio continuo della letteratura di nuova indicizzazione per mantenere aggiornato il quadro delle evidenze.">Continuous monitoring of newly indexed literature to keep the evidence landscape current.</p>
</a>
<a class="update-card" href="articles.html">
<strong data-en="Interpretation" data-it="Interpretazione">Interpretation</strong>
<span data-en="Research Articles" data-it="Articoli scientifici">Research Articles</span>
<p data-en="Scientific analyses focused on what studies add, what can reasonably be inferred and which questions remain open." data-it="Analisi scientifiche focalizzate su cosa aggiungono gli studi, cosa è ragionevole dedurre e quali questioni restano aperte.">Scientific analyses focused on what studies add, what can reasonably be inferred and which questions remain open.</p>
</a>
</div>
</div>
</section>
"""

if 'id="scientific-activity"' not in html:
    marker = '<section class="focus-band">'
    if marker not in html:
        raise RuntimeError("Could not locate focus-band insertion point in index.html")
    html = html.replace(marker, activity + marker, 1)

html = html.replace(
    'data-en="Metabolic Health" data-it="Salute metabolica">Metabolic Health',
    'data-en="Metabolic Physiology" data-it="Fisiologia metabolica">Metabolic Physiology'
)
html = html.replace(
    'data-en="Neurological Applications" data-it="Applicazioni neurologiche">Neurological Applications',
    'data-en="Neurological Metabolism" data-it="Metabolismo neurologico">Neurological Metabolism'
)

TARGET.write_text(html, encoding="utf-8")
print("Homepage updated.")
