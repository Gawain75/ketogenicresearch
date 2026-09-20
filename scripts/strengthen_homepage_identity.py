#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"

text = INDEX.read_text(encoding="utf-8")

replacements = {
    "Ketogenic Research Hub | Clinical &amp; Translational Ketogenic Research":
        "Ketogenic Research | Clinical &amp; Translational Research Center",

    "Ketogenic Research Hub: clinical and translational research in ketogenic nutrition, VLCKD, metabolic health, body composition, neurology and incretin-based therapies.":
        "Ketogenic Research is a scientific research center focused on ketogenic metabolism, clinical nutrition, metabolic health, body composition and neurological applications.",

    '"name": "Ketogenic Research Hub"':
        '"name": "Ketogenic Research"',

    '<meta content="Ketogenic Research Hub | Ricerca sulla nutrizione chetogenica" name="kr-title-it"/>':
        '<meta content="Ketogenic Research | Centro di ricerca clinica e traslazionale" name="kr-title-it"/>',

    '<p class="kicker">KETOGENIC RESEARCH HUB</p>':
        '<p class="kicker" data-en="KETOGENIC RESEARCH CENTER" data-it="CENTRO DI RICERCA CHETOGENICA">KETOGENIC RESEARCH CENTER</p>',

    'data-en="Clinical and translational research in ketogenic metabolism." data-it="Ricerca clinica e traslazionale sul metabolismo chetogenico.">Clinical and translational research in ketogenic metabolism.':
        'data-en="Clinical and translational research in ketogenic and metabolic science." data-it="Ricerca clinica e traslazionale nella scienza chetogenica e metabolica.">Clinical and translational research in ketogenic and metabolic science.',

    'data-en="A scientific research initiative dedicated to metabolic health, clinical nutrition and evidence-based therapeutic applications of ketogenic strategies." data-it="Un\'iniziativa scientifica dedicata alla salute metabolica, alla nutrizione clinica e alle applicazioni terapeutiche delle strategie chetogeniche basate sulle evidenze.">A scientific research initiative dedicated to metabolic health, clinical nutrition and evidence-based therapeutic applications of ketogenic strategies.':
        'data-en="A scientific research center dedicated to the study, critical appraisal and clinical interpretation of ketogenic and metabolic interventions." data-it="Un centro di ricerca scientifica dedicato allo studio, alla valutazione critica e all\'interpretazione clinica degli interventi chetogenici e metabolici.">A scientific research center dedicated to the study, critical appraisal and clinical interpretation of ketogenic and metabolic interventions.',

    'data-en="Research Areas" data-it="Aree di ricerca" href="research.html">Research Areas':
        'data-en="Research Programs" data-it="Programmi di ricerca" href="research.html">Research Programs',

    'data-en="Scientific Direction" data-it="Direzione scientifica" href="director.html">Scientific Direction':
        'data-en="Scientific Method" data-it="Metodo scientifico" href="methodology.html">Scientific Method',

    'data-en="Focused, rigorous and clinically oriented." data-it="Mirata, rigorosa e orientata alla clinica.">Focused, rigorous and clinically oriented.':
        'data-en="From evidence mapping to clinical interpretation." data-it="Dalla mappatura delle evidenze all\'interpretazione clinica.">From evidence mapping to clinical interpretation.',

    'data-en="The Hub studies the role of ketogenic interventions across obesity, body composition, metabolic physiology and neurological fields, with particular attention to clinically relevant outcomes and translational relevance." data-it="Il centro studia il ruolo degli interventi chetogenici in obesità, composizione corporea, fisiologia metabolica e ambiti neurologici, con particolare attenzione agli esiti clinicamente rilevanti e alla traslazione delle evidenze.">The Hub studies the role of ketogenic interventions across obesity, body composition, metabolic physiology and neurological fields, with particular attention to clinically relevant outcomes and translational relevance.':
        'data-en="Ketogenic Research integrates systematic literature surveillance, structured evidence assessment and organization and scientific interpretation across metabolic health, clinical nutrition, body composition and neurological applications. The objective is not simply to collect publications, but to organize evidence according to study design, clinical relevance and translational value." data-it="Ketogenic Research integra sorveglianza sistematica della letteratura, valutazione e organizzazione strutturata delle evidenze scientifiche e interpretazione scientifica nei campi della salute metabolica, nutrizione clinica, composizione corporea e applicazioni neurologiche. L\'obiettivo non è soltanto raccogliere pubblicazioni, ma organizzare le evidenze in base al disegno dello studio, alla rilevanza clinica e al valore traslazionale.">Ketogenic Research integrates systematic literature surveillance, structured evidence assessment and organization and scientific interpretation across metabolic health, clinical nutrition, body composition and neurological applications. The objective is not simply to collect publications, but to organize evidence according to study design, clinical relevance and translational value.',

    "© 2026 Ketogenic Research Hub":
        "© 2026 Ketogenic Research",
}

for old, new in replacements.items():
    if old not in text:
        print(f"Warning: expected text not found: {old[:90]}")
    text = text.replace(old, new)

marker = '<section class="section whats-new">'
if 'data-en="CORE ACTIVITIES"' not in text:
    section = '''<section class="section whats-new">
<div class="wrap">
<p class="kicker" data-en="CORE ACTIVITIES" data-it="ATTIVITÀ SCIENTIFICHE">CORE ACTIVITIES</p>
<h2 data-en="Research, evidence surveillance and scientific interpretation." data-it="Ricerca, sorveglianza delle evidenze e interpretazione scientifica.">Research, evidence surveillance and scientific interpretation.</h2>
<div class="update-grid">
<a class="update-card" href="research.html">
<strong data-en="Research" data-it="Ricerca">Research</strong>
<span data-en="Clinical &amp; translational programs" data-it="Programmi clinici e traslazionali">Clinical &amp; translational programs</span>
<p data-en="Defined research domains spanning ketogenic metabolism, clinical nutrition, metabolic health, body composition and neurological applications." data-it="Aree di ricerca definite che comprendono metabolismo chetogenico, nutrizione clinica, salute metabolica, composizione corporea e applicazioni neurologiche.">Defined research domains spanning ketogenic metabolism, clinical nutrition, metabolic health, body composition and neurological applications.</p>
</a>
<a class="update-card" href="library.html">
<strong data-en="Evidence" data-it="Evidenze">Evidence</strong>
<span data-en="Scientific Library &amp; surveillance" data-it="Biblioteca scientifica e sorveglianza">Scientific Library &amp; surveillance</span>
<p data-en="Continuous PubMed surveillance, bibliographic verification and structured assessment and organization by clinical area and evidence type." data-it="Sorveglianza continua di PubMed, verifica bibliografica e valutazione e organizzazione strutturata per area clinica e tipo di evidenza.">Continuous PubMed surveillance, bibliographic verification and structured assessment and organization by clinical area and evidence type.</p>
</a>
<a class="update-card" href="articles.html">
<strong data-en="Interpretation" data-it="Interpretazione">Interpretation</strong>
<span data-en="Research Articles" data-it="Articoli scientifici">Research Articles</span>
<p data-en="Editorial analyses designed to explain what new findings mean, how strongly they can be interpreted and which questions remain open." data-it="Analisi editoriali pensate per spiegare cosa significano i nuovi risultati, quanto solidamente possono essere interpretati e quali questioni restano aperte.">Editorial analyses designed to explain what new findings mean, how strongly they can be interpreted and which questions remain open.</p>
</a>
</div>
</div>
</section>
'''
    text = text.replace(marker, section + marker, 1)

INDEX.write_text(text, encoding="utf-8")
print("Homepage institutional identity updated.")
