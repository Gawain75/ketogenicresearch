#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "evidence-trends.html"
STYLES = ROOT / "styles.css"
BUILDER = ROOT / "scripts" / "build_evidence_trends.py"

CSS = r"""
/* Evidence Trends responsive fit */
.evidence-trends-chart,
.evidence-chart,
.trend-chart,
.chart-wrap,
.chart-container,
.chart-scroll,
.chart-panel,
#trendChart,
#evidenceTrendChart {
  width: 100% !important;
  max-width: 100% !important;
  min-width: 0 !important;
  overflow-x: hidden !important;
  box-sizing: border-box;
}

.evidence-trends-chart svg,
.evidence-chart svg,
.trend-chart svg,
.chart-wrap svg,
.chart-container svg,
.chart-scroll svg,
.chart-panel svg,
#trendChart svg,
#evidenceTrendChart svg,
svg.evidence-trends-svg {
  display: block;
  width: 100% !important;
  max-width: 100% !important;
  min-width: 0 !important;
  height: auto !important;
  overflow: visible;
}

@media (max-width: 720px) {
  .evidence-trends-chart,
  .evidence-chart,
  .trend-chart,
  .chart-wrap,
  .chart-container,
  .chart-scroll,
  .chart-panel,
  #trendChart,
  #evidenceTrendChart {
    margin-left: 0 !important;
    margin-right: 0 !important;
    padding-left: 0 !important;
    padding-right: 0 !important;
  }

  .evidence-trends-chart svg text,
  .evidence-chart svg text,
  .trend-chart svg text,
  .chart-wrap svg text,
  .chart-container svg text,
  .chart-scroll svg text,
  .chart-panel svg text,
  #trendChart svg text,
  #evidenceTrendChart svg text {
    font-size: 10px !important;
  }
}
"""

MARKER = "/* Evidence Trends responsive fit */"

def inject_css_into_html(path: Path):
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    if MARKER in text:
        return False

    if "</style>" in text:
        text = text.replace("</style>", CSS + "\n</style>", 1)
    elif "</head>" in text:
        text = text.replace("</head>", "<style>\n" + CSS + "\n</style>\n</head>", 1)
    else:
        raise RuntimeError("Could not find a place to inject responsive chart CSS.")

    path.write_text(text, encoding="utf-8")
    print("Patched evidence-trends.html")
    return True

def patch_shared_css(path: Path):
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    if MARKER in text:
        return False
    text += "\n\n" + CSS.strip() + "\n"
    path.write_text(text, encoding="utf-8")
    print("Patched styles.css")
    return True

def patch_builder(path: Path):
    if not path.exists():
        print("Builder not found; current page still patched.")
        return False

    text = path.read_text(encoding="utf-8")
    if MARKER in text:
        return False

    # PAGE_HTML contains a </style> tag. Inject the same CSS into the template
    # so future automatic rebuilds preserve the mobile fit.
    if "</style>" in text:
        text = text.replace("</style>", CSS + "\n</style>", 1)
        path.write_text(text, encoding="utf-8")
        print("Patched build_evidence_trends.py")
        return True

    print("Builder has no inline </style>; shared stylesheet will still apply.")
    return False

def main():
    changed = 0
    changed += int(inject_css_into_html(PAGE))
    changed += int(patch_shared_css(STYLES))
    changed += int(patch_builder(BUILDER))
    print(f"Files changed: {changed}")

if __name__ == "__main__":
    main()
