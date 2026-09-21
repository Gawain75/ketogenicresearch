#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "library.html"

MARKER = "<!-- KR_LIBRARY_AUTH_GATE_V1 -->"

BLOCK = """<!-- KR_LIBRARY_AUTH_GATE_V1 -->
<script>
  document.documentElement.classList.add('kr-auth-pending');
</script>
<style id="kr-library-auth-gate-style">
  html.kr-auth-pending body { visibility: hidden !important; }
</style>
<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
<script src="supabase-config.js"></script>
<script src="library-gate.js" defer></script>
"""

def main():
    html = LIBRARY.read_text(encoding="utf-8")

    if MARKER in html:
        print("Scientific Library auth gate already installed.")
        return

    if "</head>" not in html:
        raise RuntimeError("library.html does not contain </head>")

    html = html.replace("</head>", BLOCK + "\n</head>", 1)
    LIBRARY.write_text(html, encoding="utf-8")

    check = LIBRARY.read_text(encoding="utf-8")
    for required in (MARKER, "library-gate.js", "supabase-config.js", "@supabase/supabase-js@2"):
        if required not in check:
            raise RuntimeError(f"Verification failed: {required}")

    print("Scientific Library auth gate installed successfully.")

if __name__ == "__main__":
    main()
