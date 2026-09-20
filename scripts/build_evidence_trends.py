#!/usr/bin/env python3
from __future__ import annotations
import json, re, unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "library.html"
DATA_DIR = ROOT / "data"
DATA_FILE = DATA_DIR / "evidence-trends.json"
PAGE = ROOT / "evidence-trends.html"
CURRENT_YEAR = datetime.now().year

def norm_title(value):
    value = re.sub(r"^\s*\d+\.\s*", "", value or "")
    value = unicodedata.normalize("NFKD", value).encode("ascii","ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", value)

def pmid_from(article):
    for a in article.find_all("a", href=True):
        m = re.search(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)/?", a["href"])
        if m: return m.group(1)
    m = re.search(r"\bPMID\s*:?\s*(\d{6,9})\b", article.get_text(" ", strip=True), re.I)
    return m.group(1) if m else None

def doi_from(article):
    for a in article.find_all("a", href=True):
        href = unquote(a["href"])
        m = re.search(r"(?:doi\.org/|doi:\s*)(10\.\d{4,9}/[^\s?#\"'<>]+)", href, re.I)
        if m: return m.group(1).rstrip(".,;)").lower()
    m = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", article.get_text(" ", strip=True), re.I)
    return m.group(0).rstrip(".,;)").lower() if m else None

def paper_key(article):
    p = pmid_from(article)
    if p: return "pmid:" + p
    d = doi_from(article)
    if d: return "doi:" + d
    h = article.find("h4")
    title = h.get("data-en") if h and h.has_attr("data-en") else (h.get_text(" ", strip=True) if h else "")
    return "title:" + norm_title(title)

def paper_year(article):
    raw = (article.get("data-year") or "").strip()
    if re.fullmatch(r"(19|20)\d{2}", raw):
        y = int(raw)
        if 1900 <= y <= CURRENT_YEAR: return y
    text = article.get_text(" ", strip=True)
    m = re.search(r"\b(?:Year|Published|Publication year)\s*:?\s*((?:19|20)\d{2})\b", text, re.I)
    return int(m.group(1)) if m else None

def area_label(folder):
    s = folder.find("summary")
    strong = s.find("strong") if s else None
    if not strong:
        slug = folder.get("id") or "area"
        label = slug.replace("-"," ").title()
        return label, label
    en = (strong.get("data-en") or strong.get_text(" ", strip=True)).strip()
    it = (strong.get("data-it") or en).strip()
    return en, it

def build_dataset():
    soup = BeautifulSoup(LIBRARY.read_text(encoding="utf-8"), "html.parser")
    global_papers = {}
    areas_raw = {}
    labels = {}
    for folder in soup.select("details.library-folder"):
        slug = folder.get("id") or f"area-{len(areas_raw)+1}"
        en,it = area_label(folder)
        labels[slug] = {"en":en,"it":it}
        areas_raw.setdefault(slug,{})
        for article in folder.select("article.folder-paper"):
            key = paper_key(article)
            if key == "title:": continue
            year = paper_year(article)
            if key not in global_papers or (global_papers[key] is None and year is not None):
                global_papers[key] = year
            if key not in areas_raw[slug] or (areas_raw[slug][key] is None and year is not None):
                areas_raw[slug][key] = year

    def counts(papers):
        by = defaultdict(int); unknown = 0
        for y in papers.values():
            if y is None: unknown += 1
            else: by[str(y)] += 1
        return dict(sorted(by.items(), key=lambda x:int(x[0]))), unknown

    gb, gu = counts(global_papers)
    areas = []
    for slug,papers in areas_raw.items():
        by,u = counts(papers)
        areas.append({
            "slug":slug, "label":labels[slug], "total_unique":len(papers),
            "known_year":len(papers)-u, "unknown_year":u, "by_year":by
        })
    areas.sort(key=lambda a:a["label"]["en"].casefold())
    years = sorted(map(int, gb.keys())) if gb else []
    return {
        "generated_at":datetime.now().astimezone().isoformat(timespec="seconds"),
        "current_year":CURRENT_YEAR, "previous_year":CURRENT_YEAR-1,
        "scope_note":{
            "en":"Counts refer to unique publications indexed in the Ketogenic Research Scientific Library, not to all publications worldwide.",
            "it":"I conteggi si riferiscono alle pubblicazioni uniche indicizzate nella Biblioteca Scientifica di Ketogenic Research, non a tutte le pubblicazioni esistenti a livello mondiale."
        },
        "global":{
            "total_unique":len(global_papers),"known_year":len(global_papers)-gu,
            "unknown_year":gu,"first_year":years[0] if years else None,"by_year":gb
        },
        "areas":areas
    }

PAGE_HTML = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta content="width=device-width,initial-scale=1" name="viewport"/>
<title>Evidence Trends | Ketogenic Research</title>
<meta content="Explore publication trends over time across the Ketogenic Research Scientific Library, globally and by clinical area." name="description"/>
<link href="styles.css?v=70" rel="stylesheet"/>
<link href="https://ketogenicresearch.org/evidence-trends.html" rel="canonical"/>
<meta content="Evidence Trends | Ketogenic Research" name="kr-title-en"/>
<meta content="Andamento delle evidenze | Ketogenic Research" name="kr-title-it"/>
<style>
.trends-controls{display:grid;grid-template-columns:minmax(220px,1fr) minmax(120px,.35fr) minmax(120px,.35fr);gap:12px;align-items:end;margin:24px 0}
.trends-controls label{display:grid;gap:7px;font-weight:700}.trends-controls select{width:100%;padding:12px 14px;border:1px solid #cbd7e3;border-radius:10px;background:#fff;font:inherit}
.trend-kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin:20px 0 28px}.trend-kpi{border:1px solid #dbe4ec;border-radius:14px;padding:18px;background:#fff}
.trend-kpi strong{display:block;font-size:clamp(1.6rem,4vw,2.45rem);line-height:1;color:#173b5c;margin-bottom:8px}.trend-kpi span{font-size:.92rem;color:#536779}
.chart-shell{border:1px solid #dbe4ec;border-radius:16px;background:#fff;padding:18px;overflow:hidden}.chart-scroll{overflow-x:auto;padding-bottom:8px}
#trendChart{display:block;width:100%;min-width:760px;height:430px}.chart-note{margin:14px 0 0;color:#5d6d7b;font-size:.92rem}
.area-table{width:100%;border-collapse:collapse;margin-top:16px}.area-table th,.area-table td{text-align:left;padding:11px 9px;border-bottom:1px solid #e4ebf1}
.area-table th{font-size:.82rem;text-transform:uppercase;letter-spacing:.05em;color:#5b6d7e}.area-table td:nth-child(n+2),.area-table th:nth-child(n+2){text-align:right}
@media(max-width:760px){.trends-controls{grid-template-columns:1fr 1fr}.trends-controls label:first-child{grid-column:1/-1}.trend-kpis{grid-template-columns:1fr 1fr}}
</style>
</head>
<body>
<header class="header"><div class="wrap nav">
<a aria-label="Ketogenic Research" class="brand" href="index.html"><img alt="Ketogenic Research" class="site-logo" src="logo-ketogenic-research.png"/></a>
<nav><a href="index.html">Home</a><a data-en="Research" data-it="Ricerca" href="research.html">Research</a><a data-en="Scientific Library" data-it="Biblioteca Scientifica" href="library.html">Scientific Library</a><a data-en="Latest Evidence" data-it="Ultime pubblicazioni" href="latest.html">Latest Evidence</a><a data-en="Evidence Trends" data-it="Andamento evidenze" href="evidence-trends.html">Evidence Trends</a><a data-en="Articles" data-it="Articoli" href="articles.html">Articles</a><a data-en="Methodology" data-it="Metodologia" href="methodology.html">Methodology</a><a data-en="Scientific Direction" data-it="Direzione scientifica" href="director.html">Scientific Direction</a><a data-en="Contact" data-it="Contatti" href="contact.html">Contact</a></nav>
<div class="actions"><div class="lang"><button class="active" data-lang="en">EN</button><button data-lang="it">IT</button></div><button aria-label="Menu" class="menu">☰</button></div>
</div></header>
<main>
<section class="page-hero"><div class="wrap"><p class="kicker" data-en="EVIDENCE TRENDS" data-it="ANDAMENTO DELLE EVIDENZE">EVIDENCE TRENDS</p><h1 data-en="How the scientific literature has evolved over time." data-it="Come si è evoluta la letteratura scientifica nel tempo.">How the scientific literature has evolved over time.</h1><p class="lead" data-en="Explore the annual number of unique publications indexed in the Scientific Library, globally or within a selected clinical area." data-it="Esplora il numero annuale di pubblicazioni uniche indicizzate nella Biblioteca Scientifica, globalmente o all’interno di una specifica area clinica.">Explore the annual number of unique publications indexed in the Scientific Library, globally or within a selected clinical area.</p></div></section>
<section class="section"><div class="wrap">
<div class="trends-controls"><label><span data-en="Scope" data-it="Ambito">Scope</span><select id="areaSelect"></select></label><label><span data-en="From" data-it="Da">From</span><select id="fromYear"></select></label><label><span data-en="To" data-it="A">To</span><select id="toYear"></select></label></div>
<div class="trend-kpis"><div class="trend-kpi"><strong id="kpiTotal">—</strong><span data-en="Unique publications" data-it="Pubblicazioni uniche">Unique publications</span></div><div class="trend-kpi"><strong id="kpiCurrent">—</strong><span id="kpiCurrentLabel"></span></div><div class="trend-kpi"><strong id="kpiPrevious">—</strong><span id="kpiPreviousLabel"></span></div><div class="trend-kpi"><strong id="kpiKnown">—</strong><span data-en="With known publication year" data-it="Con anno di pubblicazione noto">With known publication year</span></div></div>
<div class="chart-shell"><div class="chart-scroll"><svg id="trendChart" role="img"></svg></div><p class="chart-note" id="scopeNote"></p><p class="chart-note" data-en="The current year is incomplete and should not be interpreted as a like-for-like comparison with a completed previous year." data-it="L’anno corrente è incompleto e non deve essere interpretato come un confronto omogeneo con un anno precedente già concluso.">The current year is incomplete and should not be interpreted as a like-for-like comparison with a completed previous year.</p></div>
</div></section>
<section class="section"><div class="wrap"><p class="kicker" data-en="AREAS AT A GLANCE" data-it="AREE IN SINTESI">AREAS AT A GLANCE</p><h2 data-en="Publication volume by clinical area" data-it="Volume delle pubblicazioni per area clinica">Publication volume by clinical area</h2><div style="overflow-x:auto"><table class="area-table"><thead><tr><th data-en="Area" data-it="Area">Area</th><th data-en="Total" data-it="Totale">Total</th><th id="tableCurrentHead"></th><th id="tablePreviousHead"></th></tr></thead><tbody id="areaTable"></tbody></table></div></div></section>
</main>
<footer class="footer"><div class="wrap"><strong>Ketogenic Research</strong></div></footer>
<script>
let DATA=null; const $=s=>document.querySelector(s); const lang=()=>document.documentElement.lang==="it"?"it":"en";
const n=v=>new Intl.NumberFormat(lang()==="it"?"it-IT":"en-US").format(v||0); const tf=o=>o?.[lang()]||o?.en||"";
function setLanguage(l){document.documentElement.lang=l;document.querySelectorAll("[data-en][data-it]").forEach(e=>e.textContent=e.dataset[l]||e.dataset.en);document.querySelectorAll("[data-lang]").forEach(b=>b.classList.toggle("active",b.dataset.lang===l));localStorage.setItem("kr-lang",l);if(DATA){populateAreas();render();}}
document.querySelectorAll("[data-lang]").forEach(b=>b.addEventListener("click",()=>setLanguage(b.dataset.lang)));document.querySelector(".menu")?.addEventListener("click",()=>document.querySelector(".header nav")?.classList.toggle("open"));
function scope(){return $("#areaSelect").value==="global"?DATA.global:(DATA.areas.find(a=>a.slug===$("#areaSelect").value)||DATA.global)}
function populateAreas(){const v=$("#areaSelect").value||"global";$("#areaSelect").innerHTML=`<option value="global">${lang()==="it"?"Globale — tutte le aree":"Global — all areas"}</option>`;DATA.areas.forEach(a=>{let o=document.createElement("option");o.value=a.slug;o.textContent=tf(a.label);$("#areaSelect").appendChild(o)});$("#areaSelect").value=[...$("#areaSelect").options].some(o=>o.value===v)?v:"global"}
function populateYears(){const ys=Object.keys(DATA.global.by_year).map(Number).sort((a,b)=>a-b);for(const id of ["fromYear","toYear"]){$("#"+id).innerHTML="";ys.forEach(y=>{let o=document.createElement("option");o.value=y;o.textContent=y;$("#"+id).appendChild(o)})}if(ys.length){$("#fromYear").value=ys[0];$("#toYear").value=ys.at(-1)}}
function draw(by,from,to){const svg=$("#trendChart"),ys=[];for(let y=from;y<=to;y++)ys.push(y);const vals=ys.map(y=>+by[y]||0),W=Math.max(760,ys.length*42+90),H=430,p={l:58,r:22,t:24,b:62},pw=W-p.l-p.r,ph=H-p.t-p.b,m=Math.max(1,...vals),ns="http://www.w3.org/2000/svg";svg.setAttribute("viewBox",`0 0 ${W} ${H}`);svg.style.minWidth=W+"px";svg.innerHTML="";const add=(t,a,x)=>{let e=document.createElementNS(ns,t);Object.entries(a||{}).forEach(([k,v])=>e.setAttribute(k,v));if(x!=null)e.textContent=x;svg.appendChild(e);return e};for(let i=0;i<=5;i++){let val=Math.round(m*i/5),y=p.t+ph-ph*i/5;add("line",{x1:p.l,y1:y,x2:W-p.r,y2:y,stroke:"#e6edf3"});add("text",{x:p.l-10,y:y+4,"text-anchor":"end",fill:"#667889","font-size":"11"},val)}const band=pw/ys.length,bw=Math.max(8,Math.min(28,band*.64));ys.forEach((yr,i)=>{let v=vals[i],h=v/m*ph,x=p.l+i*band+(band-bw)/2,y=p.t+ph-h,b=add("rect",{x,y,width:bw,height:h,rx:3,fill:"#1f6f8b"}),tt=document.createElementNS(ns,"title");tt.textContent=`${yr}: ${v}`;b.appendChild(tt);if(ys.length<=18||i%Math.ceil(ys.length/14)===0||i===ys.length-1)add("text",{x:x+bw/2,y:H-28,"text-anchor":"middle",fill:"#536779","font-size":"11"},yr)});add("line",{x1:p.l,y1:p.t+ph,x2:W-p.r,y2:p.t+ph,stroke:"#93a5b5"})}
function table(){let tb=$("#areaTable");tb.innerHTML="";let cy=DATA.current_year,py=DATA.previous_year;$("#tableCurrentHead").textContent=`${cy}${lang()==="it"?" (in corso)":" (to date)"}`;$("#tablePreviousHead").textContent=py;[...DATA.areas].sort((a,b)=>b.total_unique-a.total_unique).forEach(a=>{let tr=document.createElement("tr");tr.innerHTML=`<td>${tf(a.label)}</td><td>${n(a.total_unique)}</td><td>${n(a.by_year[cy]||0)}</td><td>${n(a.by_year[py]||0)}</td>`;tr.onclick=()=>{$("#areaSelect").value=a.slug;render();window.scrollTo({top:0,behavior:"smooth"})};tb.appendChild(tr)})}
function render(){let s=scope(),cy=DATA.current_year,py=DATA.previous_year,from=+$("#fromYear").value,to=+$("#toYear").value;$("#kpiTotal").textContent=n(s.total_unique);$("#kpiCurrent").textContent=n(s.by_year[cy]||0);$("#kpiPrevious").textContent=n(s.by_year[py]||0);$("#kpiKnown").textContent=n(s.known_year);$("#kpiCurrentLabel").textContent=lang()==="it"?`${cy} · anno in corso`:`${cy} · year to date`;$("#kpiPreviousLabel").textContent=py;$("#scopeNote").textContent=tf(DATA.scope_note)+(s.unknown_year?` ${lang()==="it"?"Anno non disponibile per":"Publication year unavailable for"} ${n(s.unknown_year)} ${lang()==="it"?"record.":"records."}`:"");draw(s.by_year,Math.min(from,to),Math.max(from,to));table()}
fetch("data/evidence-trends.json",{cache:"no-store"}).then(r=>r.json()).then(d=>{DATA=d;populateAreas();populateYears();["areaSelect","fromYear","toYear"].forEach(id=>$("#"+id).onchange=render);setLanguage(localStorage.getItem("kr-lang")==="it"?"it":"en");render()});
</script>
</body></html>'''

def patch_navigation():
    for path in ROOT.glob("*.html"):
        if path.name == PAGE.name: continue
        text = path.read_text(encoding="utf-8")
        if "evidence-trends.html" in text: continue
        new,count = re.subn(
            r'(<a[^>]+href="latest\.html"[^>]*>.*?</a>)',
            r'\1<a data-en="Evidence Trends" data-it="Andamento evidenze" href="evidence-trends.html">Evidence Trends</a>',
            text, count=1, flags=re.S
        )
        if count: path.write_text(new, encoding="utf-8")

def main():
    DATA_DIR.mkdir(exist_ok=True)
    data = build_dataset()
    DATA_FILE.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    PAGE.write_text(PAGE_HTML,encoding="utf-8")
    patch_navigation()
    print(json.dumps({
        "global_unique_publications":data["global"]["total_unique"],
        "known_year":data["global"]["known_year"],
        "unknown_year":data["global"]["unknown_year"],
        "clinical_areas":len(data["areas"]),
        "current_year_publications":data["global"]["by_year"].get(str(data["current_year"]),0),
        "previous_year_publications":data["global"]["by_year"].get(str(data["previous_year"]),0)
    },indent=2))

if __name__=="__main__": main()
