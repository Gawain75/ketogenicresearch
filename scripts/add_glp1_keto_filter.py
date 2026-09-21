#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "library.html"
JS = ROOT / "script.js"

TOPIC_SELECT = (
    '<select aria-label="Filter by thematic intersection" id="topicFilter">'
    '<option data-en="All thematic intersections" data-it="Tutte le intersezioni tematiche" value="all">'
    'All thematic intersections</option>'
    '<option data-en="GLP-1-based therapies + ketogenic / ketosis / ketones" '
    'data-it="Terapie GLP-1 + chetogenica / chetosi / chetoni" '
    'value="glp1-keto">GLP-1-based therapies + ketogenic / ketosis / ketones</option>'
    '</select>'
)

HELPER = r'''function topicMatches(rawText, selected) {
  if (selected === 'all') return true;
  const text = (rawText || '').toLowerCase();

  if (selected === 'glp1-keto') {
    const glpTerms = [
      'glp-1',
      'glp1',
      'glucagon-like peptide-1',
      'semaglutide',
      'liraglutide',
      'dulaglutide',
      'exenatide',
      'lixisenatide',
      'tirzepatide',
      'retatrutide',
      'survodutide',
      'orforglipron',
      'cagrisema'
    ];

    const ketoTerms = [
      'ketogenic',
      'ketosis',
      'ketone',
      'ketones',
      'ketonemia',
      'ketonaemia',
      'beta-hydroxybutyrate',
      'β-hydroxybutyrate',
      'b-hydroxybutyrate',
      'bhb',
      'vlckd',
      'vlekt',
      'low-energy ketogenic',
      'very low-calorie ketogenic',
      'very-low-calorie ketogenic',
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

def patch_library():
    s = LIB.read_text(encoding="utf-8")
    if 'id="topicFilter"' in s:
        print("topicFilter already present")
        return

    pos = s.find('id="evidenceFilter"')
    if pos < 0:
        raise RuntimeError("evidenceFilter not found")
    close = s.find("</select>", pos)
    if close < 0:
        raise RuntimeError("Closing evidenceFilter select not found")
    close += len("</select>")

    s = s[:close] + TOPIC_SELECT + s[close:]
    LIB.write_text(s, encoding="utf-8")
    print("Added topicFilter to library.html")

def patch_js():
    s = JS.read_text(encoding="utf-8")

    if "function topicMatches(" not in s:
        marker = "function publicationIdentity(paper) {"
        if marker not in s:
            raise RuntimeError("publicationIdentity() not found")
        s = s.replace(marker, HELPER + marker, 1)

    replacements = [
        (
            "  const evidenceEl = document.getElementById('evidenceFilter');\n"
            "  const yearEl = document.getElementById('yearFilter');\n"
            "  const areaEl = document.getElementById('areaFilter');",
            "  const evidenceEl = document.getElementById('evidenceFilter');\n"
            "  const topicEl = document.getElementById('topicFilter');\n"
            "  const yearEl = document.getElementById('yearFilter');\n"
            "  const areaEl = document.getElementById('areaFilter');"
        ),
        (
            "  const ev = evidenceEl?.value || 'all';\n"
            "  const yr = yearEl?.value || 'all';\n"
            "  const area = areaEl?.value || 'all';",
            "  const ev = evidenceEl?.value || 'all';\n"
            "  const topic = topicEl?.value || 'all';\n"
            "  const yr = yearEl?.value || 'all';\n"
            "  const area = areaEl?.value || 'all';"
        ),
        (
            "      const qOk = !q || blob.includes(q);\n"
            "      const evOk = evidenceMatches(paper.dataset.evidence, ev);",
            "      const qOk = !q || blob.includes(q);\n"
            "      const evOk = evidenceMatches(paper.dataset.evidence, ev);\n"
            "      const topicOk = topicMatches(blob, topic);"
        ),
        (
            "      const show = qOk && evOk && yrOk;",
            "      const show = qOk && evOk && topicOk && yrOk;"
        ),
        (
            "      if (q || ev !== 'all' || yr !== 'all' || area !== 'all') {",
            "      if (q || ev !== 'all' || topic !== 'all' || yr !== 'all' || area !== 'all') {"
        ),
        (
            "  ['librarySearch', 'evidenceFilter', 'yearFilter', 'areaFilter'].forEach(id => {",
            "  ['librarySearch', 'evidenceFilter', 'topicFilter', 'yearFilter', 'areaFilter'].forEach(id => {"
        ),
        (
            "      const evidence = document.getElementById('evidenceFilter');\n"
            "      const year = document.getElementById('yearFilter');\n"
            "      const area = document.getElementById('areaFilter');",
            "      const evidence = document.getElementById('evidenceFilter');\n"
            "      const topic = document.getElementById('topicFilter');\n"
            "      const year = document.getElementById('yearFilter');\n"
            "      const area = document.getElementById('areaFilter');"
        ),
        (
            "      if (evidence) evidence.value = 'all';\n"
            "      if (year) year.value = 'all';\n"
            "      if (area) area.value = 'all';",
            "      if (evidence) evidence.value = 'all';\n"
            "      if (topic) topic.value = 'all';\n"
            "      if (year) year.value = 'all';\n"
            "      if (area) area.value = 'all';"
        ),
    ]

    for old, new in replacements:
        if new in s:
            continue
        if old not in s:
            raise RuntimeError("Expected current script.js block not found:\n" + old)
        s = s.replace(old, new, 1)

    JS.write_text(s, encoding="utf-8")
    print("Patched script.js")

def verify():
    lib = LIB.read_text(encoding="utf-8")
    js = JS.read_text(encoding="utf-8")

    required_js = [
        "function topicMatches(",
        "const topicEl = document.getElementById('topicFilter');",
        "const topic = topicEl?.value || 'all';",
        "const topicOk = topicMatches(blob, topic);",
        "const show = qOk && evOk && topicOk && yrOk;",
        "'topicFilter'",
        "if (topic) topic.value = 'all';",
    ]
    for token in required_js:
        if token not in js:
            raise RuntimeError("Missing JS token: " + token)

    if lib.count('id="topicFilter"') != 1:
        raise RuntimeError("Expected exactly one topicFilter")
    if 'value="glp1-keto"' not in lib:
        raise RuntimeError("GLP-1 ketogenic option missing")

    print("GLP-1 + ketogenic thematic filter installed successfully.")

def main():
    patch_library()
    patch_js()
    verify()

if __name__ == "__main__":
    main()
