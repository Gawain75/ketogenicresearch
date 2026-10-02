#!/usr/bin/env python3
from pathlib import Path
import re
import shutil
import json
import html as htmlmod
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "cloudflare-dist"
CF = ROOT / "cloudflare"
CHUNKS = DIST / "library-chunks"

FILES = [
    "script.js",
    "styles.css",
    "latest-publications.json",
    "logo-ketogenic-research.png",
    "favicon.svg",
    "privacy.html",
    "privacy-en.html",
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

    # Library: show research type and conclusion type on separate lines.
    library_details_css = """
<style id="kr-library-details-multiline">
.paper-study-details > span,
.article-study-details > span,
.library-study-details > span { display: block; }
.paper-study-details > span + span,
.article-study-details > span + span,
.library-study-details > span + span { margin-top: 3px; }
</style>
"""
    if "kr-library-details-multiline" not in html:
        m = re.search(r"</head>", html, flags=re.I)
        if m:
            html = html[:m.start()] + library_details_css + "\n" + html[m.start():]
        else:
            html = library_details_css + html

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
        "privacy.html": "https://ketogenicresearch.org/privacy.html",
    }
    for relative, absolute in public_pages.items():
        html = re.sub(
            rf'href=(["\']){re.escape(relative)}\1',
            f'href="{absolute}"',
            html,
            flags=re.I,
        )

    # Brand/home links sometimes use "/" instead of index.html.
    html = re.sub(
        r'(<a[^>]+class=(["\'])brand\2[^>]+href=)(["\'])/\3',
        rf'\1"https://ketogenicresearch.org/"',
        html,
        flags=re.I,
    )

    return html

def inject_account_status(html: str) -> str:
    """Add a compact authenticated-user strip below the header without covering controls."""
    marker = "KR_LIBRARY_ACCOUNT_STATUS_V2"
    if marker in html:
        return html

    widget = r"""
<!-- KR_LIBRARY_ACCOUNT_STATUS_V2 -->
<style>
.kr-account-strip-wrap{
  padding:10px 18px 0;
}
.kr-account-strip{
  max-width:1200px;margin:0 auto;
  display:none;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;
  padding:10px 14px;border:1px solid rgba(17,24,39,.08);
  border-radius:16px;background:#f7fbff;box-shadow:0 4px 18px rgba(15,23,42,.05);
  font:600 14px/1.35 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  color:#123b35;
}
.kr-account-strip .kr-account-text{
  display:flex;align-items:center;gap:10px;min-width:0;flex:1 1 260px;
}
.kr-account-strip .kr-account-badge{
  display:inline-flex;align-items:center;justify-content:center;
  min-width:28px;height:28px;padding:0 8px;border-radius:999px;
  background:#dff3ea;color:#0d5c48;font-size:12px;font-weight:800;letter-spacing:.02em;
}
.kr-account-strip .kr-user{
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0;
}
.kr-account-strip button{
  border:0;border-radius:999px;padding:8px 14px;cursor:pointer;
  background:#17352b;color:#fff;font:700 13px/1 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
}
.kr-account-strip button:disabled{opacity:.7;cursor:default}
@media (max-width:640px){
  .kr-account-strip-wrap{padding:8px 12px 0}
  .kr-account-strip{padding:10px 12px;gap:10px}
  .kr-account-strip .kr-account-text{flex-basis:100%}
  .kr-account-strip button{width:100%}
}
</style>
<div class="kr-account-strip-wrap">
  <div id="kr-account-status" class="kr-account-strip" aria-live="polite">
    <div class="kr-account-text">
      <span class="kr-account-badge">OK</span>
      <span class="kr-user" id="kr-account-user">Accesso attivo</span>
    </div>
    <button type="button" id="kr-logout">Esci</button>
  </div>
</div>
<script>
(async function(){
  const box=document.getElementById('kr-account-status');
  const label=document.getElementById('kr-account-user');
  const logout=document.getElementById('kr-logout');
  try{
    const r=await fetch('/auth/me',{credentials:'same-origin',cache:'no-store'});
    if(!r.ok) return;
    const me=await r.json();
    if(!me.authenticated) return;
    const full=[me.first_name,me.last_name].filter(Boolean).join(' ').trim();
    label.textContent='Connesso come: ' + (full || me.email || 'Account attivo');
    box.style.display='flex';
  }catch(e){}

  logout.addEventListener('click',async function(){
    logout.disabled=true;
    try{
      await fetch('/auth/logout',{method:'POST',credentials:'same-origin'});
    }finally{
      location.href='/library-access';
    }
  });
})();
</script>
"""

    m = re.search(r'</header>', html, flags=re.I)
    if m:
        pos = m.end()
        return html[:pos] + "\n" + widget + "\n" + html[pos:]
    if "</body>" in html.lower():
        pos = html.lower().rfind("</body>")
        return html[:pos] + widget + "\n" + html[pos:]
    return html + widget

def split_library_payload(html: str) -> str:
    """Split heavy Library card payloads into Cloudflare-safe fragments."""
    CHUNKS.mkdir(parents=True, exist_ok=True)
    start_re = re.compile(r'<div\s+class=(["\\\'])folder-curated\1[^>]*>', re.I)
    div_re = re.compile(r'<div\b[^>]*>|</div\s*>', re.I)
    out, cursor, chunk_no = [], 0, 0
    while True:
        m = start_re.search(html, cursor)
        if not m:
            out.append(html[cursor:]); break
        open_end, depth = m.end(), 1
        close_start = close_end = None
        for token in div_re.finditer(html, open_end):
            raw = token.group(0).lower()
            if raw.startswith('</div'):
                depth -= 1
                if depth == 0:
                    close_start, close_end = token.start(), token.end(); break
            else:
                depth += 1
        if close_start is None:
            raise SystemExit('Unable to split Library: unmatched folder-curated div')
        chunk_no += 1
        rel = f'library-chunks/chunk-{chunk_no:04d}.html'
        (DIST / rel).write_text(html[open_end:close_start], encoding='utf-8')
        out.append(html[cursor:m.start()])
        out.append(f'<div class="folder-curated" data-kr-library-chunk="{rel}"><div class="kr-library-loading" aria-hidden="true"></div></div>')
        cursor = close_end
    if chunk_no == 0:
        raise SystemExit('Unable to split Library: no folder-curated containers found')
    shell = ''.join(out)
    script_re = re.compile(r'<script\s+src=(["\\\'])script\.js(?:\?[^"\\\']*)?\1\s*></script>', re.I)
    loader = """<script>
(async function(){
  const nodes=Array.from(document.querySelectorAll('[data-kr-library-chunk]'));
  try {
    await Promise.all(nodes.map(async function(node){
      const url=node.getAttribute('data-kr-library-chunk');
      const response=await fetch(url,{cache:'default'});
      if(!response.ok) throw new Error('Library chunk failed: '+url+' ('+response.status+')');
      node.innerHTML=await response.text();
      node.removeAttribute('data-kr-library-chunk');
    }));
    const script=document.createElement('script');
    script.src='script.js?v=71';
    document.body.appendChild(script);
  } catch(error) {
    console.error(error);
    nodes.forEach(function(node){if(node.hasAttribute('data-kr-library-chunk')) node.innerHTML='<p class=\"folder-rationale\">Unable to load this Library section. Please reload the page.</p>';});
  }
})();
</script>"""
    shell, replaced = script_re.subn(loader, shell, count=1)
    if replaced != 1:
        raise SystemExit('Unable to split Library: script.js tag not found')
    print(f'Library payload split into {chunk_no} fragments.')
    return shell

def main():
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)

    library = ROOT / "library.html"
    if not library.exists():
        raise SystemExit("library.html not found")

    original_library_html = library.read_text(encoding="utf-8")

    # Admin manifests: lightweight indexes used by the browser backend.
    page_files = [x for x in ROOT.glob("*.html") if x.name not in {"admin.html", "library.html", "library-access.html", "reset-password.html", "review-studio.html"}]
    pages = []
    for x in sorted(page_files):
        src=x.read_text(encoding="utf-8",errors="ignore")
        m=re.search(r"<title>(.*?)</title>",src,re.I|re.S)
        pages.append({"path":x.name,"title":htmlmod.unescape(re.sub(r"<[^>]+>","",m.group(1)).strip()) if m else x.stem})
    # Snapshot the site's existing navigation so the Admin starts from the real menu,
    # not from an empty configuration. This also makes hide/delete/order operations reversible.
    menu=[]
    index_src=(ROOT/"index.html").read_text(encoding="utf-8",errors="ignore")
    nav_m=re.search(r'<nav[^>]*class="[^"]*site-nav[^"]*"[^>]*>(.*?)</nav>',index_src,re.I|re.S)
    if nav_m:
        nav_html=nav_m.group(1)
        more_m=re.search(r'<div[^>]*class="[^"]*nav-submenu[^"]*"[^>]*>(.*?)</div>',nav_html,re.I|re.S)
        more_html=more_m.group(1) if more_m else ""
        direct_html=re.sub(r'<details[^>]*class="[^"]*nav-more[^"]*"[^>]*>.*?</details>','',nav_html,flags=re.I|re.S)
        def add_links(fragment,group,start):
            n=start
            for am in re.finditer(r'<a\b([^>]*)>(.*?)</a>',fragment,re.I|re.S):
                attrs,body=am.group(1),am.group(2)
                hm=re.search(r'href="([^"]+)"',attrs,re.I)
                if not hm: continue
                href=htmlmod.unescape(hm.group(1)).strip()
                if href and not re.match(r'^(?:https?:|mailto:|#)',href,re.I): href='/'+href.lstrip('/')
                enm=re.search(r'data-en="([^"]*)"',attrs,re.I); itm=re.search(r'data-it="([^"]*)"',attrs,re.I)
                text=htmlmod.unescape(re.sub(r'<[^>]+>','',body)).strip()
                menu.append({"label_en":htmlmod.unescape(enm.group(1)) if enm else text,"label_it":htmlmod.unescape(itm.group(1)) if itm else text,"href":href,"group":group,"visible":True,"order":n})
                n+=10
            return n
        order=add_links(direct_html,"main",10)
        add_links(more_html,"more",order)

    articles=[]
    for x in sorted((ROOT/"articles").glob("*.html"),reverse=True):
        src=x.read_text(encoding="utf-8",errors="ignore")
        m=re.search(r"<h1[^>]*>(.*?)</h1>",src,re.I|re.S); pm=re.search(r"PMID:\s*(\d+)",src,re.I) or re.search(r"(?:^|-)\b(\d{7,9})-",x.name)
        title=htmlmod.unescape(re.sub(r"<[^>]+>","",m.group(1)).strip()) if m else x.stem
        articles.append({"path":"articles/"+x.name,"title":title,"pmid":pm.group(1) if pm else ""})
    studies=[]; seen=set()
    pat=re.compile(r'(<article[^>]*data-pmid="(\d+)"[^>]*>).*?<h4[^>]*>(.*?)</h4>',re.I|re.S)
    for m in pat.finditer(original_library_html):
        pmid=m.group(2)
        if pmid in seen: continue
        seen.add(pmid); title=htmlmod.unescape(re.sub(r"<[^>]+>","",m.group(3))).strip(); title=re.sub(r"^\d+\.\s*","",title)
        dm=re.search(r'data-doi="([^"]*)"',m.group(1),re.I)
        studies.append({"pmid":pmid,"doi":dm.group(1) if dm else "","title":title})

    html = clean_library_html(original_library_html)
    html = inject_account_status(html)
    html = split_library_payload(html)
    (DIST / "library.html").write_text(html, encoding="utf-8")

    for name in FILES:
        source = ROOT / name
        if not source.exists():
            raise SystemExit(f"Required Library asset missing: {name}")
        shutil.copy2(source, DIST / name)

    for name in ["admin.html", "admin.js", "admin.css", "review-studio.js", "review-studio.css", "site-admin-public.js"]:
        source = ROOT / name
        if not source.exists():
            raise SystemExit(f"Required admin asset missing: {name}")
        shutil.copy2(source, DIST / name)

    (DIST / "_admin-pages.json").write_text(json.dumps(pages,ensure_ascii=False),encoding="utf-8")
    (DIST / "_admin-menu.json").write_text(json.dumps(menu,ensure_ascii=False),encoding="utf-8")
    (DIST / "_admin-articles.json").write_text(json.dumps(articles,ensure_ascii=False),encoding="utf-8")
    (DIST / "_admin-library.json").write_text(json.dumps(studies,ensure_ascii=False),encoding="utf-8")
    # Safe appearance manifest: existing clinical-area identifiers only. The admin can
    # override their icons, never names/slugs/classification rules.
    clinical_areas=[]
    select_m=re.search(r'<select[^>]+id="areaFilter"[^>]*>(.*?)</select>',original_library_html,re.I|re.S)
    icon_by_label={}
    for im in re.finditer(r'<span[^>]+class="[^"]*kr-area-icon[^"]*"[^>]+data-icon-for="([^"]+)"[^>]*>\s*<img[^>]+src="([^"]+)"',original_library_html,re.I|re.S):
        icon_by_label[htmlmod.unescape(im.group(1)).strip()]=htmlmod.unescape(im.group(2))
    if select_m:
        for om in re.finditer(r'<option\b([^>]*)>(.*?)</option>',select_m.group(1),re.I|re.S):
            attrs=om.group(1); vm=re.search(r'value="([^"]+)"',attrs,re.I)
            if not vm or vm.group(1)=="all": continue
            em=re.search(r'data-en="([^"]+)"',attrs,re.I); label=htmlmod.unescape(em.group(1) if em else re.sub(r'<[^>]+>','',om.group(2))).strip()
            clinical_areas.append({"slug":htmlmod.unescape(vm.group(1)).strip(),"label":label,"icon":icon_by_label.get(label,"")})
    (DIST / "_admin-status.json").write_text(json.dumps({"generated_at":datetime.now(timezone.utc).isoformat(),"clinical_areas":clinical_areas},ensure_ascii=False),encoding="utf-8")
    source_dir=DIST/"_admin-source"; (source_dir/"articles").mkdir(parents=True,exist_ok=True)
    for x in page_files: (source_dir/(x.name+".txt")).write_text(x.read_text(encoding="utf-8",errors="ignore"),encoding="utf-8")
    for x in (ROOT/"articles").glob("*.html"): (source_dir/"articles"/(x.name+".txt")).write_text(x.read_text(encoding="utf-8",errors="ignore"),encoding="utf-8")

    for name in ["library-access.html", "reset-password.html", "_worker.js", "index.html"]:
        source = CF / name
        if not source.exists():
            raise SystemExit(f"Required Cloudflare asset missing: cloudflare/{name}")
        shutil.copy2(source, DIST / name)

    # Raw copies are deliberately stored with .txt extensions. Cloudflare Pages
    # canonicalizes .html asset URLs; serving these raw copies through the Worker
    # prevents redirect loops for the login and admin routes.
    shutil.copy2(CF / "library-access.html", DIST / "_raw-library-access.txt")
    shutil.copy2(ROOT / "admin.html", DIST / "_raw-admin.txt")
    shutil.copy2(ROOT / "review-studio.html", DIST / "_raw-review-studio.txt")

    checks = {
        "library.html": ["Scientific Library", "script.js?v=71", "styles.css", "data-kr-library-chunk"],
        "library-access.html": ["forgotPassword", "Complete your Library profile"],
        "_worker.js": ["env.ASSETS.fetch(request)", "library_profiles", "/auth/me"],
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

    if 'https://ketogenicresearch.org/' not in library_out:
        raise SystemExit("Main-site Home URL missing from protected Library")

    max_pages_file = 25 * 1024 * 1024
    oversized = [p for p in DIST.rglob("*") if p.is_file() and p.stat().st_size > max_pages_file]
    if oversized:
        details = ", ".join(f"{p.relative_to(DIST)} ({p.stat().st_size / 1024 / 1024:.1f} MiB)" for p in oversized)
        raise SystemExit(f"Cloudflare Pages 25 MiB file limit exceeded: {details}")

    print("Cloudflare Library package built successfully.")
    print("Files:")
    for p in sorted(DIST.iterdir()):
        print(f" - {p.name}: {p.stat().st_size} bytes")

if __name__ == "__main__":
    main()
