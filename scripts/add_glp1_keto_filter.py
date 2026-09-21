#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "library.html"
JS = ROOT / "script.js"

TOPIC_SELECT = (
    '<select aria-label="Filter by thematic intersection" id="topicFilter">'
    '<option data-en="All thematic intersections" data-it="Tutte le intersezioni tematiche" value="all">All thematic intersections</option>'
    '<option data-en="GLP-1-based therapies + ketogenic / ketosis / ketones" '
    'data-it="Terapie GLP-1 + chetogenica / chetosi / chetoni" '
    'value="glp1-keto">GLP-1-based therapies + ketogenic / ketosis / ketones</option>'
    '</select>'
)

def patch_library():
    s = LIB.read_text(encoding="utf-8")
    if 'id="topicFilter"' in s:
        print("topicFilter already present in library.html")
        return
    pos = s.find('id="evidenceFilter"')
    if pos < 0:
        raise RuntimeError("evidenceFilter not found in library.html")
    close = s.find("</select>", pos)
    if close < 0:
        raise RuntimeError("Closing evidenceFilter select not found")
    close += len("</select>")
    s = s[:close] + TOPIC_SELECT + s[close:]
    LIB.write_text(s, encoding="utf-8")
    print("Added thematic intersection filter to library.html")

def patch_js():
    s = JS.read_text(encoding="utf-8")

    helper = '''function topicMatches(rawText, selected) {
  if (selected === 'all') return true;
  const text = (rawText || '').toLowerCase();

  if (selected === 'glp1-keto') {
    const glpTerms = [
      'glp-1', 'glp1', 'glucagon-like peptide-1',
      'semaglutide', 'liraglutide', 'dulaglutide',
      'exenatide', 'lixisenatide', 'tirzepatide',
      'retatrutide', 'survodutide', 'orforglipron', 'cagrisema'
    ];

    const ketoTerms = [
      'ketogenic', 'ketosis', 'ketone', 'ketones',
      'ketonemia', 'ketonaemia', 'beta-hydroxybutyrate',
      'β-hydroxybutyrate', 'b-hydroxybutyrate', 'bhb',
      'vlckd', 'vlekt', 'low-energy ketogenic',
      'very low-calorie ketogenic', 'very-low-calorie ketogenic',
      'keto diet'
    ];

    return (
      glpTerms.some(term => text.includes(term)) &&
      ketoTerms.some(term => text.includes(term))
    );
  }

  return true;
}

'''

    if "function topicMatches(" not in s:
        marker = "function publicationIdentity(paper) {"
        if marker not in s:
            raise RuntimeError("publicationIdentity marker not found")
        s = s.replace(marker, helper + marker, 1)

    s = s.replace(
        "  const evidenceEl = document.getElementById('evidenceFilter');\n"
        "  const yearEl = document.getElementById('yearFilter');\n"
        "  const areaEl = document.getElementById('areaFilter');",
        "  const evidenceEl = document.getElementById('evidenceFilter');\n"
        "  const topicEl = document.getElementById('topicFilter');\n"
        "  const yearEl = document.getElementById('yearFilter');\n"
        "  const areaEl = document.getElementById('areaFilter');",
        1,
    )

    s = s.replace(
        "  const ev = evidenceEl?.value || 'all';\n"
        "  const yr = yearEl?.value || 'all';\n"
        "  const area = areaEl?.value || 'all';",
        "  const ev = evidenceEl?.value || 'all';\n"
        "  const topic = topicEl?.value || 'all';\n"
        "  const yr = yearEl?.value || 'all';\n"
        "  const area = areaEl?.value || 'all';",
        1,
    )

    s = s.replace(
        "      const paperEv = normalizeEvidence(paper.dataset.evidence);\n"
        "      const paperYear = paper.dataset.year || 'unknown';\n"
        "      const qOk = !q || blob.includes(q);\n"
        "      const evOk = evidenceMatches(paper.dataset.evidence, ev);",
        "      const paperEv = normalizeEvidence(paper.dataset.evidence);\n"
        "      const paperYear = paper.dataset.year || 'unknown';\n"
        "      const paperText = (paper.dataset.search || '').toLowerCase();\n"
        "      const qOk = !q || blob.includes(q);\n"
        "      const evOk = evidenceMatches(paper.dataset.evidence, ev);\n"
        "      const topicOk = topicMatches(paperText, topic);",
        1,
    )

    s = s.replace(
        "      const show = qOk && evOk && yrOk;",
        "      const show = qOk && evOk && topicOk && yrOk;",
        1,
    )

    s = s.replace(
        "      if (q || ev !== 'all' || yr !== 'all' || area !== 'all') {",
        "      if (q || ev !== 'all' || topic !== 'all' || yr !== 'all' || area !== 'all') {",
        1,
    )

    s = s.replace(
        "  ['librarySearch', 'evidenceFilter', 'yearFilter', 'areaFilter'].forEach(id => {",
        "  ['librarySearch', 'evidenceFilter', 'topicFilter', 'yearFilter', 'areaFilter'].forEach(id => {",
        1,
    )

    s = s.replace(
        "      const evidence = document.getElementById('evidenceFilter');\n"
        "      const year = document.getElementById('yearFilter');\n"
        "      const area = document.getElementById('areaFilter');",
        "      const evidence = document.getElementById('evidenceFilter');\n"
        "      const topic = document.getElementById('topicFilter');\n"
        "      const year = document.getElementById('yearFilter');\n"
        "      const area = document.getElementById('areaFilter');",
        1,
    )

    s = s.replace(
        "      if (evidence) evidence.value = 'all';\n"
        "      if (year) year.value = 'all';\n"
        "      if (area) area.value = 'all';",
        "      if (evidence) evidence.value = 'all';\n"
        "      if (topic) topic.value = 'all';\n"
        "      if (year) year.value = 'all';\n"
        "      if (area) area.value = 'all';",
        1,
    )

    required = [
        "function topicMatches(",
        "const topicEl = document.getElementById('topicFilter');",
        "const topicOk = topicMatches(paperText, topic);",
        "qOk && evOk && topicOk && yrOk",
        "'topicFilter'",
    ]
    for token in required:
        if token not in s:
            raise RuntimeError("JS patch incomplete: missing " + token)

    JS.write_text(s, encoding="utf-8")
    print("Added GLP-1 + ketogenic thematic filter logic to script.js")

def verify():
    lib = LIB.read_text(encoding="utf-8")
    js = JS.read_text(encoding="utf-8")
    if lib.count('id="topicFilter"') != 1:
        raise RuntimeError("Expected exactly one topicFilter")
    if 'value="glp1-keto"' not in lib:
        raise RuntimeError("GLP-1 ketogenic option missing")
    if "function topicMatches(" not in js:
        raise RuntimeError("topicMatches missing")
    print("Thematic GLP-1 + ketogenic filter installed successfully.")

def main():
    patch_library()
    patch_js()
    verify()

if __name__ == "__main__":
    main()
