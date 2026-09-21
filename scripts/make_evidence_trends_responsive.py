#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "evidence-trends.html"

STYLE = r"""
<style id="kr-responsive-evidence-chart">
/* Responsive Evidence Trends charts: never require horizontal scrolling */
#trendChart,
.chart,
.chart-wrap,
.chart-container,
.trend-chart,
.trend-chart-wrap,
.evidence-chart,
.evidence-chart-wrap {
  width: 100% !important;
  max-width: 100% !important;
  min-width: 0 !important;
  overflow-x: hidden !important;
}

#trendChart svg,
.chart svg,
.chart-wrap svg,
.chart-container svg,
.trend-chart svg,
.trend-chart-wrap svg,
.evidence-chart svg,
.evidence-chart-wrap svg,
svg[data-evidence-chart] {
  display: block;
  width: 100% !important;
  max-width: 100% !important;
  min-width: 0 !important;
  height: auto !important;
  overflow: visible;
}

/* Prevent a fixed-width chart from widening the whole page */
main,
section,
.wrap,
.container {
  min-width: 0;
  max-width: 100%;
}

@media (max-width: 700px) {
  #trendChart,
  .chart,
  .chart-wrap,
  .chart-container,
  .trend-chart,
  .trend-chart-wrap,
  .evidence-chart,
  .evidence-chart-wrap {
    margin-left: 0 !important;
    margin-right: 0 !important;
  }
}
</style>
"""

JS = r"""
<script id="kr-responsive-evidence-chart-js">
(function () {
  function numericAttr(el, name) {
    var v = parseFloat(el.getAttribute(name) || "");
    return Number.isFinite(v) ? v : null;
  }

  function makeSvgResponsive(svg) {
    if (!svg) return;

    /* Preserve the original drawing coordinate system before removing fixed size. */
    if (!svg.getAttribute("viewBox")) {
      var w = numericAttr(svg, "width");
      var h = numericAttr(svg, "height");
      if (w && h) svg.setAttribute("viewBox", "0 0 " + w + " " + h);
    }

    svg.removeAttribute("width");
    svg.removeAttribute("height");
    svg.style.width = "100%";
    svg.style.maxWidth = "100%";
    svg.style.minWidth = "0";
    svg.style.height = "auto";
    svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
    svg.setAttribute("data-evidence-chart", "responsive");

    /* Remove common fixed-width values from immediate parents. */
    var p = svg.parentElement;
    for (var i = 0; p && i < 3; i++, p = p.parentElement) {
      p.style.minWidth = "0";
      p.style.maxWidth = "100%";
      if (getComputedStyle(p).overflowX === "auto" ||
          getComputedStyle(p).overflowX === "scroll") {
        p.style.overflowX = "hidden";
      }
    }

    thinYearLabels(svg);
  }

  function thinYearLabels(svg) {
    var width = svg.getBoundingClientRect().width || window.innerWidth;
    var yearNodes = Array.prototype.filter.call(
      svg.querySelectorAll("text"),
      function (node) {
        return /^(18|19|20)\d{2}$/.test((node.textContent || "").trim());
      }
    );

    if (yearNodes.length < 2) return;

    /*
      Keep all bars/data points, but reduce only x-axis year labels.
      About one visible year label every 55-70 px depending on viewport.
    */
    var targetLabels = Math.max(5, Math.floor(width / (width < 600 ? 58 : 70)));
    var step = Math.max(1, Math.ceil(yearNodes.length / targetLabels));

    yearNodes.forEach(function (node, index) {
      var year = parseInt(node.textContent, 10);
      var keep =
        index === 0 ||
        index === yearNodes.length - 1 ||
        index % step === 0 ||
        year % 10 === 0;

      node.style.display = keep ? "" : "none";
    });
  }

  function apply() {
    var svgs = document.querySelectorAll(
      "#trendChart svg, .chart svg, .chart-wrap svg, .chart-container svg, " +
      ".trend-chart svg, .trend-chart-wrap svg, .evidence-chart svg, " +
      ".evidence-chart-wrap svg, svg[data-evidence-chart]"
    );

    /* Fallback: Evidence Trends normally has only a small number of SVG charts. */
    if (!svgs.length) svgs = document.querySelectorAll("main svg");

    svgs.forEach(makeSvgResponsive);
  }

  var resizeTimer;
  window.addEventListener("resize", function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(apply, 120);
  });

  var observer = new MutationObserver(function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(apply, 50);
  });

  function start() {
    apply();
    var main = document.querySelector("main") || document.body;
    observer.observe(main, {childList:true, subtree:true});
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
</script>
"""

def patch_page():
    if not PAGE.exists():
        raise RuntimeError("evidence-trends.html not found")

    html = PAGE.read_text(encoding="utf-8")

    # Remove older copy if rerun, then insert current version.
    html = re.sub(
        r'<style id="kr-responsive-evidence-chart">.*?</style>\s*',
        '',
        html,
        flags=re.S,
    )
    html = re.sub(
        r'<script id="kr-responsive-evidence-chart-js">.*?</script>\s*',
        '',
        html,
        flags=re.S,
    )

    if "</head>" in html:
        html = html.replace("</head>", STYLE + "\n</head>", 1)
    else:
        html = STYLE + html

    if "</body>" in html:
        html = html.replace("</body>", JS + "\n</body>", 1)
    else:
        html += JS

    PAGE.write_text(html, encoding="utf-8")
    print("Responsive Evidence Trends patch applied.")

def main():
    patch_page()

if __name__ == "__main__":
    main()
