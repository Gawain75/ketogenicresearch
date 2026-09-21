#!/usr/bin/env python3
from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "library.html"
SCRIPT = ROOT / "script.js"
STYLES = ROOT / "styles.css"

SUBFOLDER_ID = "obesity-glp1-keto"
HELPER_JS = "function isGlp1KetoIntersection(paper) {\n  const titleEl = paper.querySelector('h4');\n  const text = [\n    paper.dataset.search || '',\n    titleEl?.dataset?.en || '',\n    titleEl?.dataset?.it || '',\n    titleEl?.textContent || ''\n  ].join(' ').toLowerCase();\n\n  const glpTerms = [\n    'glp-1', 'glp1', 'glp-1ra', 'glp1ra', 'glp-1 receptor agonist',\n    'glucagon-like peptide-1', 'incretin',\n    'semaglutide', 'liraglutide', 'dulaglutide', 'exenatide',\n    'lixisenatide', 'tirzepatide', 'retatrutide', 'survodutide',\n    'orforglipron', 'cagrisema'\n  ];\n\n  const ketoTerms = [\n    'ketogenic', 'ketosis', 'ketone', 'ketones',\n    'ketonemia', 'ketonaemia', 'beta-hydroxybutyrate',\n    'β-hydroxybutyrate', 'b-hydroxybutyrate', 'bhb',\n    'ketone ester', 'exogenous ketone',\n    'vlckd', 'vlekt', 'low-energy ketogenic',\n    'very low-calorie ketogenic', 'very-low-calorie ketogenic',\n    'keto diet'\n  ];\n\n  return (\n    glpTerms.some(term => text.includes(term)) &&\n    ketoTerms.some(term => text.includes(term))\n  );\n}\n\nfunction populateObesityGlp1Keto() {\n  const obesity = document.getElementById('obesity');\n  const host = document.getElementById('obesityGlp1KetoList');\n  const count = document.getElementById('obesityGlp1KetoCount');\n  const empty = document.getElementById('obesityGlp1KetoEmpty');\n  if (!obesity || !host) return;\n\n  const papers = Array.from(\n    obesity.querySelectorAll('.folder-curated > article.folder-paper')\n  );\n\n  const matches = papers.filter(isGlp1KetoIntersection);\n  host.innerHTML = '';\n\n  const lang = currentLang();\n\n  matches.forEach(paper => {\n    const card = document.createElement('article');\n    card.className = 'topic-subfolder-paper';\n\n    const sourceTitle = paper.querySelector('h4');\n    if (sourceTitle) {\n      const h4 = document.createElement('h4');\n      const en = sourceTitle.dataset.en || sourceTitle.textContent || '';\n      const it = sourceTitle.dataset.it || en;\n      h4.dataset.en = en;\n      h4.dataset.it = it;\n      h4.innerHTML = lang === 'it' ? it : en;\n      card.appendChild(h4);\n    }\n\n    const meta = paper.querySelector('p');\n    if (meta) {\n      const p = meta.cloneNode(true);\n      if (p.dataset.en || p.dataset.it) {\n        p.innerHTML = lang === 'it'\n          ? (p.dataset.it || p.dataset.en || p.textContent)\n          : (p.dataset.en || p.textContent);\n      }\n      card.appendChild(p);\n    }\n\n    const links = paper.querySelector('.paper-links');\n    if (links) card.appendChild(links.cloneNode(true));\n\n    host.appendChild(card);\n  });\n\n  if (count) count.textContent = String(matches.length);\n  if (empty) empty.hidden = matches.length > 0;\n}\n"
SUBCATEGORY_CSS = '\n/* Obesity GLP-1 + ketogenic subcategory */\n.library-topic-subfolder{\n  margin:14px 0 18px;\n  border:1px solid #bfd3e3;\n  border-radius:10px;\n  background:#f4f9fd;\n  overflow:hidden;\n}\n.library-topic-subfolder > summary{\n  list-style:none;\n  display:grid;\n  grid-template-columns:1fr auto 24px;\n  gap:12px;\n  align-items:center;\n  padding:13px 14px;\n  cursor:pointer;\n}\n.library-topic-subfolder > summary::-webkit-details-marker{display:none}\n.topic-subfolder-title strong{\n  display:block;\n  color:var(--primary);\n  font-size:14px;\n}\n.topic-subfolder-title small{\n  display:block;\n  color:var(--muted);\n  font-size:11px;\n  margin-top:2px;\n}\n.topic-subfolder-count{\n  min-width:28px;\n  padding:2px 8px;\n  border-radius:999px;\n  background:#dcecf7;\n  color:var(--primary);\n  font-size:11px;\n  font-weight:700;\n  text-align:center;\n}\n.topic-subfolder-arrow{\n  color:var(--primary-2);\n  font-size:18px;\n  transition:transform .18s ease;\n}\n.library-topic-subfolder[open] .topic-subfolder-arrow{transform:rotate(45deg)}\n.topic-subfolder-body{padding:0 14px 14px}\n.topic-subfolder-list{display:grid;gap:9px}\n.topic-subfolder-paper{\n  border:1px solid var(--line);\n  border-radius:9px;\n  padding:12px;\n  background:#fff;\n}\n.topic-subfolder-paper h4{\n  margin:0 0 7px;\n  font-size:13px;\n  line-height:1.35;\n  color:var(--ink);\n}\n.topic-subfolder-paper p{\n  margin:0 0 10px;\n  font-size:11px;\n  color:var(--muted);\n}\n.topic-subfolder-empty{\n  margin:8px 0 0 !important;\n  font-size:12px !important;\n}\n@media(max-width:850px){\n  .library-topic-subfolder > summary{\n    grid-template-columns:1fr auto 20px;\n    padding:12px;\n  }\n}\n'

def patch_library():
    html = LIBRARY.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")

    obesity = soup.find("details", id="obesity")
    if obesity is None:
        raise RuntimeError("Obesity clinical area (#obesity) not found")

    if soup.find(id=SUBFOLDER_ID) is not None:
        print("GLP-1 + ketogenic subcategory already present in Obesity")
        return

    body = obesity.select_one(".folder-body")
    if body is None:
        raise RuntimeError("Obesity .folder-body not found")

    sub = soup.new_tag("details")
    sub["class"] = ["library-topic-subfolder"]
    sub["id"] = SUBFOLDER_ID

    summary = soup.new_tag("summary")
    title = soup.new_tag("span")
    title["class"] = ["topic-subfolder-title"]

    strong = soup.new_tag("strong")
    strong["data-en"] = "GLP-1RA + ketogenic / ketosis / ketones"
    strong["data-it"] = "GLP-1RA + chetogenica / chetosi / chetoni"
    strong.string = strong["data-en"]

    small = soup.new_tag("small")
    small["data-en"] = "Studies combining GLP-1-based therapies with ketogenic interventions or ketone biology"
    small["data-it"] = "Studi che combinano terapie basate su GLP-1 con interventi chetogenici o biologia dei chetoni"
    small.string = small["data-en"]

    count = soup.new_tag("span")
    count["id"] = "obesityGlp1KetoCount"
    count["class"] = ["topic-subfolder-count"]
    count.string = "0"

    arrow = soup.new_tag("span")
    arrow["class"] = ["topic-subfolder-arrow"]
    arrow.string = "＋"

    title.append(strong)
    title.append(small)
    summary.append(title)
    summary.append(count)
    summary.append(arrow)
    sub.append(summary)

    sub_body = soup.new_tag("div")
    sub_body["class"] = ["topic-subfolder-body"]

    intro = soup.new_tag("p")
    intro["data-en"] = (
        "Automatically identified within the Obesity library when a record contains both "
        "a GLP-1/incretin therapy term and a ketogenic, ketosis or ketone-related term."
    )
    intro["data-it"] = (
        "Identificati automaticamente nell'area Obesità quando un record contiene sia "
        "un termine relativo a terapie GLP-1/incretiniche sia un termine relativo a "
        "chetogenica, chetosi o chetoni."
    )
    intro.string = intro["data-en"]

    host = soup.new_tag("div")
    host["id"] = "obesityGlp1KetoList"
    host["class"] = ["topic-subfolder-list"]

    empty = soup.new_tag("p")
    empty["id"] = "obesityGlp1KetoEmpty"
    empty["class"] = ["topic-subfolder-empty"]
    empty["data-en"] = "No matching studies are currently indexed in the Obesity library."
    empty["data-it"] = "Al momento non risultano studi corrispondenti indicizzati nell'area Obesità."
    empty.string = empty["data-en"]

    sub_body.append(intro)
    sub_body.append(host)
    sub_body.append(empty)
    sub.append(sub_body)

    curated = body.select_one(".folder-curated")
    if curated is not None:
        curated.insert_before(sub)
    else:
        body.insert(0, sub)

    LIBRARY.write_text(str(soup), encoding="utf-8")
    print("Added GLP-1RA + ketogenic subcategory under Obesity")

def patch_script():
    s = SCRIPT.read_text(encoding="utf-8")

    if "function populateObesityGlp1Keto()" not in s:
        marker = "function publicationIdentity(paper) {"
        if marker not in s:
            raise RuntimeError("publicationIdentity() marker not found in script.js")
        s = s.replace(marker, HELPER_JS + "\n" + marker, 1)

    if "function initLibrary() {\n  populateObesityGlp1Keto();" not in s:
        marker = "function initLibrary() {\n"
        if marker not in s:
            raise RuntimeError("initLibrary() not found in script.js")
        s = s.replace(marker, marker + "  populateObesityGlp1Keto();\n", 1)

    if "  populateObesityGlp1Keto();\n  applyLibraryFilters();\n  updateLibraryCounters();" not in s:
        marker = "  applyLibraryFilters();\n  updateLibraryCounters();"
        if marker not in s:
            raise RuntimeError("setLang() library refresh marker not found")
        s = s.replace(
            marker,
            "  populateObesityGlp1Keto();\n  applyLibraryFilters();\n  updateLibraryCounters();",
            1,
        )

    SCRIPT.write_text(s, encoding="utf-8")
    print("Added automatic GLP-1RA + ketogenic population logic")

def patch_styles():
    s = STYLES.read_text(encoding="utf-8")
    if "/* Obesity GLP-1 + ketogenic subcategory */" not in s:
        STYLES.write_text(s + SUBCATEGORY_CSS, encoding="utf-8")
        print("Added subcategory styles")
    else:
        print("Subcategory styles already present")

def verify():
    html = LIBRARY.read_text(encoding="utf-8")
    js = SCRIPT.read_text(encoding="utf-8")
    styles = STYLES.read_text(encoding="utf-8")

    checks = [
        (html.count('id="obesity-glp1-keto"') == 1, "Obesity subcategory missing or duplicated"),
        ('id="obesityGlp1KetoList"' in html, "subcategory host missing"),
        ("function populateObesityGlp1Keto()" in js, "population function missing"),
        ("function isGlp1KetoIntersection(" in js, "intersection matcher missing"),
        ("populateObesityGlp1Keto();" in js, "subcategory initialization missing"),
        ("Obesity GLP-1 + ketogenic subcategory" in styles, "subcategory CSS missing"),
    ]
    for ok, message in checks:
        if not ok:
            raise RuntimeError(message)

    print("Obesity GLP-1RA + ketogenic subcategory installed successfully")

def main():
    patch_library()
    patch_script()
    patch_styles()
    verify()

if __name__ == "__main__":
    main()
