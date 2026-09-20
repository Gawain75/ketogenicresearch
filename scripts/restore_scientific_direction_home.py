#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "index.html"

html = TARGET.read_text(encoding="utf-8")

SECTION_ID = 'id="scientific-direction-home"'

section = r'''
<section class="section" id="scientific-direction-home">
<div class="wrap">
<div class="methodology-two-col">

<div>
<p class="kicker" data-en="SCIENTIFIC DIRECTION" data-it="DIREZIONE SCIENTIFICA">SCIENTIFIC DIRECTION</p>
<h2 data-en="Scientific oversight and methodological direction" data-it="Supervisione scientifica e indirizzo metodologico">Scientific oversight and methodological direction</h2>
<p data-en="Scientific direction provides methodological oversight, defines research priorities and ensures that evidence is interpreted in proportion to study design, clinical relevance and methodological limitations."
   data-it="La Direzione scientifica assicura la supervisione metodologica, definisce le priorità di ricerca e garantisce che le evidenze siano interpretate in proporzione al disegno dello studio, alla rilevanza clinica e ai limiti metodologici.">
Scientific direction provides methodological oversight, defines research priorities and ensures that evidence is interpreted in proportion to study design, clinical relevance and methodological limitations.
</p>
<a class="btn-primary" href="director.html" data-en="Scientific Direction" data-it="Direzione scientifica">Scientific Direction</a>
</div>

<article class="method-card">
<p class="kicker" data-en="SCIENTIFIC DIRECTOR" data-it="DIRETTORE SCIENTIFICO">SCIENTIFIC DIRECTOR</p>
<h3>Marco Medeot</h3>
<p class="role" data-en="Scientific Director - Ketogenic Research" data-it="Direttore Scientifico - Ketogenic Research">
Scientific Director - Ketogenic Research
</p>
<p data-en="Scientific focus: ketogenic metabolic therapies, clinical nutrition, obesity, body composition, lean-mass preservation and metabolic physiology."
   data-it="Focus scientifico: terapie metaboliche chetogeniche, nutrizione clinica, obesità, composizione corporea, preservazione della massa magra e fisiologia metabolica.">
Scientific focus: ketogenic metabolic therapies, clinical nutrition, obesity, body composition, lean-mass preservation and metabolic physiology.
</p>
<a class="btn-secondary" href="director.html" data-en="View profile and responsibilities" data-it="Profilo e responsabilità">View profile and responsibilities</a>
</article>

</div>
</div>
</section>
'''

if SECTION_ID in html:
    print("Scientific Direction homepage section already present; no changes needed.")
else:
    if "</main>" not in html:
        raise RuntimeError("Closing </main> tag not found in index.html")

    html = html.replace("</main>", section + "\n</main>", 1)
    TARGET.write_text(html, encoding="utf-8")
    print("Scientific Direction homepage section restored.")
