---
pmid: "42951014"
doi: "10.1016/j.mbs.2026.109835"
pmcid: ""
date: "2026-10-28"
journal: "Mathematical biosciences"
article_type: "Research Note"
article_type_it: "Nota di ricerca"
study_type: "Preclinical / mechanistic study"
study_type_it: "Studio preclinico / meccanistico"
conclusion_type: "Mechanistic / hypothesis-generating"
conclusion_type_it: "Meccanistico / generazione di ipotesi"
generator_version: "4.6"
source_identity: "PASS"
source_identity_basis: "PubMed PMID/title/DOI/PMCID"
full_text_source: "PubMed abstract"
full_text_url: ""
editorial_byline: "Ketogenic Research Editorial"
scientific_oversight_en: "Marco Medeot, Scientific Director"
scientific_oversight_it: "Marco Medeot, Direttore Scientifico"
verification: "PASS"
verified_at: "2026-10-29T10:02:31.672266+00:00"
---

# A cancer-inspired metaheuristic applied to optimal control of breast cancer treatment

**Research Note**

**Ketogenic Research Editorial**  
Scientific oversight: **Marco Medeot, Scientific Director**

The authors present the Cancer Improvement Optimizer (CIO), a new bio‑inspired metaheuristic that mimics tumor‑immune dynamics. After benchmarking CIO against standard optimization algorithms, they use it to solve a nonlinear optimal‑control model that integrates chemotherapy, immunotherapy, anti‑cancer drugs and a ketogenic diet for breast cancer. The computational results suggest that the CIO‑driven framework can generate treatment schedules that suppress tumor growth while preserving healthy cells and limiting toxicity.

## Study and findings

The paper describes the development of the Cancer Improvement Optimizer (CIO), a metaheuristic algorithm whose design is motivated by five biological processes: tumor proliferation, immune surveillance, therapeutic intervention, dormancy, and recurrence. CIO balances global exploration and local exploitation to avoid premature convergence. Its performance was first evaluated on a suite of continuous benchmark functions (unimodal, multimodal, separable, non‑separable), where it achieved solution quality and convergence speed comparable to or better than several state‑of‑the‑art algorithms. The authors then applied CIO to an optimal control problem (OCP) for breast cancer. The OCP models tumor‑immune dynamics with ordinary differential equations and includes control variables for chemotherapy, immunotherapy, anti‑cancer drug dosing, and a ketogenic diet. Using a collocation method based on Boubaker scaling functions, the OCP was transformed into a finite‑dimensional nonlinear programming problem solved by CIO. Numerical simulations indicated that the CIO‑derived treatment schedules reduced tumor volume, maintained healthy cell counts, enhanced immune activity, and kept treatment‑related toxicity within acceptable limits.

## Clinical interpretation

Because the study is entirely computational, the findings cannot be directly extrapolated to patient care. Nonetheless, the results illustrate that a metaheuristic grounded in cancer biology can efficiently explore complex, multi‑objective treatment spaces. The inclusion of a ketogenic diet as a control variable demonstrates that dietary interventions can be mathematically integrated with pharmacologic therapies, potentially informing future in‑silico trial designs. The reported ability of CIO to balance tumor suppression with preservation of healthy tissue aligns with clinical goals of maximizing efficacy while minimizing adverse effects, but clinical validation would require prospective studies in animal models or patients.

## Limitations and open questions

The analysis relies on a deterministic ODE model that simplifies many aspects of tumor heterogeneity, patient variability, and pharmacokinetics. No experimental or clinical data were used to calibrate or validate the model parameters, limiting confidence in the quantitative predictions. The study does not compare CIO‑generated schedules with those derived from standard clinical protocols, so the relative clinical advantage remains uncertain. Future work should test the algorithm on validated preclinical models, explore stochastic extensions to capture biological variability, and assess whether the inclusion of a ketogenic diet yields measurable benefits in vivo.

### Source

Ebrahimzadeh et al., Mathematical Biosciences, 2026.

---

# Un metaeuristico ispirato al cancro applicato al controllo ottimale del trattamento del carcinoma mammario

**Nota di ricerca**

**Ketogenic Research Editorial**  
Supervisione scientifica: **Marco Medeot, Direttore Scientifico**

Gli autori introducono il Cancer Improvement Optimizer (CIO), un nuovo metaeuristico ispirato ai processi biologici del cancro. Dopo aver confrontato CIO con algoritmi di ottimizzazione standard, lo impiegano per risolvere un modello di controllo ottimale non lineare che combina chemioterapia, immunoterapia, farmaci anticancro e dieta chetogenica per il carcinoma mammario. I risultati computazionali suggeriscono che il framework basato su CIO può produrre protocolli terapeutici che riducono la crescita tumorale, preservano le cellule sane e limitano la tossicità.

## Studio e risultati

Il lavoro descrive lo sviluppo del Cancer Improvement Optimizer (CIO), un algoritmo metaeuristico ispirato a cinque processi biologici: proliferazione tumorale, sorveglianza immunitaria, intervento terapeutico, dormienza e recidiva. CIO bilancia l'esplorazione globale e lo sfruttamento locale per evitare la convergenza prematura. Le sue prestazioni sono state prima valutate su un insieme di funzioni di benchmark continue (unimodali, multimodali, separabili, non separabili), dove ha ottenuto una qualità della soluzione e una velocità di convergenza pari o superiore a diversi algoritmi all'avanguardia. Gli autori hanno poi applicato CIO a un problema di controllo ottimale (OCP) per il carcinoma mammario. L'OCP modella le dinamiche tumore‑immune con equazioni differenziali ordinarie e include variabili di controllo per chemioterapia, immunoterapia, dosaggio di farmaci anticancro e una dieta chetogenica. Utilizzando un metodo di collocazione basato su funzioni di scaling di Boubaker, l'OCP è stato trasformato in un problema di programmazione non lineare a dimensione finita risolto da CIO. Le simulazioni numeriche hanno mostrato che i protocolli terapeutici derivati da CIO riducono il volume tumorale, mantengono il numero di cellule sane, potenziano l'attività immunitaria e mantengono la tossicità del trattamento entro limiti accettabili.

## Interpretazione clinica

Poiché lo studio è interamente computazionale, i risultati non possono essere direttamente generalizzati alla pratica clinica. Tuttavia, dimostrano che un metaeuristico basato sulla biologia del cancro può esplorare in modo efficiente spazi terapeutici complessi e multi‑obiettivo. L'inclusione della dieta chetogenica come variabile di controllo evidenzia la possibilità di integrare matematicamente interventi dietetici con terapie farmacologiche, potenzialmente utile per la progettazione di futuri studi in silico. La capacità di CIO di bilanciare la soppressione tumorale con la preservazione del tessuto sano corrisponde agli obiettivi clinici di massimizzare l'efficacia riducendo gli effetti avversi, ma la conferma clinica richiederà studi prospettici su modelli animali o pazienti.

## Limiti e questioni aperte

L'analisi si basa su un modello deterministico di equazioni differenziali ordinarie che semplifica l'eterogeneità tumorale, la variabilità tra pazienti e la farmacocinetica, limitando la fiducia nelle previsioni quantitative. Non sono stati utilizzati dati sperimentali o clinici per calibrare o validare i parametri del modello, il che riduce la robustezza dei risultati. Lo studio non confronta le strategie generate da CIO con protocolli clinici standard, quindi il vantaggio clinico relativo rimane incerto. Ricerche future dovrebbero testare l'algoritmo su modelli preclinici validati, introdurre estensioni stochastiche per catturare la variabilità biologica e valutare se l'integrazione della dieta chetogenica apporta benefici misurabili in vivo.

### Fonte

Ebrahimzadeh et al., Mathematical Biosciences, 2026.

