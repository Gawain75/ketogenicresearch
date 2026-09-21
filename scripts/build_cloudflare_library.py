#!/usr/bin/env python3
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "cloudflare-dist"
CF = ROOT / "cloudflare"

FILES = [
    "script.js",
    "styles.css",
    "latest-publications.json",
    "logo-ketogenic-research.png",
    "favicon.svg",
]

def clean_library_html(html: str) -> str:
    # Remove the old client-side GitHub Pages authentication gate.
    html = re.sub(
        r'<!-- KR_LIBRARY_AUTH_GATE_V1 -->.*?(?=</head>)',
        '',
        html,
        count=1,
        flags=re.S,
    )

    # Private/protected library should not be indexed.
    html = re.sub(
        r'<meta\s+content="[^"]*"\s+name="robots"\s*/?>',
        '<meta content="noindex,nofollow,noarchive" name="robots"/>',
        html,
        count=1,
        flags=re.I,
    )

    # Avoid canonicalizing the protected copy back to the public GitHub Pages URL.
    html = re.sub(
        r'<link\s+href="https://ketogenicresearch\.org/library\.html"\s+rel="canonical"\s*/?>',
        '',
        html,
        count=1,
        flags=re.I,
    )

    # Remove stale auth assets if a previous gate variant exists without marker.
    html = re.sub(r'\s*<script[^>]+src="library-gate\.js"[^>]*></script>', '', html, flags=re.I)
    html = re.sub(r'\s*<script[^>]+src="supabase-config\.js"[^>]*></script>', '', html, flags=re.I)
    html = re.sub(
        r'\s*<script[^>]+src="https://cdn\.jsdelivr\.net/npm/@supabase/supabase-js@2"[^>]*></script>',
        '',
        html,
        flags=re.I,
    )
    html = html.replace("kr-auth-pending", "")

    # The protected Library lives on library.ketogenicresearch.org, while the
    # rest of the website lives on ketogenicresearch.org. Convert the Library
    # navigation back to absolute main-site URLs so Home/Research/etc. never
    # resolve inside the protected subdomain.
    public_pages = {
        "index.html": "https://ketogenicresearch.org/",
        "research.html": "https://ketogenicresearch.org/research.html",
        "latest.html": "https://ketogenicresearch.org/latest.html",
        "evidence-trends.html": "https://ketogenicresearch.org/evidence-trends.html",
        "articles.html": "https://ketogenicresearch.org/articles.html",
        "director.html": "https://ketogenicresearch.org/director.html",
        "methodology.html": "https://ketogenicresearch.org/methodology.html",
        "contact.html": "https://ketogenicresearch.org/contact.html",
    }
    for relative, absolute in public_pages.items():
        html = re.sub(
            rf'href=(["\']){re.escape(relative)}\1',
            f'href="{absolute}"',
            html,
            flags=re.I,
        )

    # Any root-relative Home link inside the protected subdomain must go
    # back to the public website. Otherwise "/" on library.ketogenicresearch.org
    # opens the login page again.
    html = re.sub(
        r'href=(["\'])/\1',
        'href="https://ketogenicresearch.org/"',
        html,
        flags=re.I,
    )
    html = re.sub(
        r'href=(["\'])\./\1',
        'href="https://ketogenicresearch.org/"',
        html,
        flags=re.I,
    )

    return html

def main():
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)

    library = ROOT / "library.html"
    if not library.exists():
        raise SystemExit("library.html not found")

    html = clean_library_html(library.read_text(encoding="utf-8"))
    (DIST / "library.html").write_text(html, encoding="utf-8")

    for name in FILES:
        source = ROOT / name
        if not source.exists():
            raise SystemExit(f"Required Library asset missing: {name}")
        shutil.copy2(source, DIST / name)

    for name in ["library-access.html", "reset-password.html", "_worker.js", "index.html"]:
        source = CF / name
        if not source.exists():
            raise SystemExit(f"Required Cloudflare asset missing: cloudflare/{name}")
        shutil.copy2(source, DIST / name)

    checks = {
        "library.html": ["Scientific Library", "script.js", "styles.css"],
        "library-access.html": ["forgotPassword", "Complete your Library profile"],
        "_worker.js": ["env.ASSETS.fetch(request)", "library_profiles"],
    }
    for filename, needles in checks.items():
        data = (DIST / filename).read_text(encoding="utf-8", errors="ignore")
        for needle in needles:
            if needle not in data:
                raise SystemExit(f"Verification failed: {needle!r} missing from {filename}")

    library_out = (DIST / "library.html").read_text(encoding="utf-8")
    if "library-gate.js" in library_out:
        raise SystemExit("Old client-side library gate still present")

    if 'href="index.html"' in library_out:
        raise SystemExit("Relative Home link still present in protected Library")

    if re.search(r'href=(["\'])/\1', library_out, re.I):
        raise SystemExit("Root-relative Home link still present in protected Library")

    if 'https://ketogenicresearch.org/' not in library_out:
        raise SystemExit("Main-site Home URL missing from protected Library")

    print("Cloudflare Library package built successfully.")
    print("Files:")
    for p in sorted(DIST.iterdir()):
        print(f" - {p.name}: {p.stat().st_size} bytes")

if __name__ == "__main__":
    main()
