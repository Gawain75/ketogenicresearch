#!/usr/bin/env python3
from __future__ import annotations
import argparse, html, json, re, time, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1] if Path(__file__).resolve().parent.name == "scripts" else Path.cwd()
LIBRARY = ROOT / "library.html"
REPORT = ROOT / "library-evidence-backfill-report.json"
BATCH_SIZE = 120
NCBI = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
UA = "KetogenicResearchHub/1.0 (scientific-library-classification)"

LABELS = {
 "Systematic review / meta-analysis": ("Revisione sistematica / meta-analisi","systematic-review-/-meta-analysis"),
 "Guideline / consensus": ("Linea guida / consenso","guideline-/-consensus"),
 "Randomized clinical trial": ("Trial clinico randomizzato","randomized-clinical-trial"),
 "Clinical trial / intervention": ("Trial clinico / intervento","clinical-trial-/-intervention"),
 "Observational human study": ("Studio osservazionale sull'uomo","observational-human-study"),
 "Case report / case series": ("Case report / serie di casi","case-report-/-case-series"),
 "Review": ("Revisione","review"),
 "Preclinical / mechanistic": ("Preclinico / meccanicistico","preclinical-/-mechanistic"),
 "Human / clinical or translational evidence": ("Evidenza umana / clinica o traslazionale","human"),
 "Historical / foundational evidence": ("Evidenza storica / fondativa","historical"),
 "Other": ("Altro","other"),
}

ANIMAL_RE = re.compile(r"\b(mouse|mice|murine|rat|rats|rodent|rodents|zebrafish|drosophila|rabbit|rabbits|porcine|swine|hamster|hamsters)\b", re.I)
HUMAN_RE = re.compile(r"\b(patient|patients|participant|participants|subject|subjects|volunteer|volunteers|men|women|woman|man|children|child|adolescent|adolescents|adult|adults|people|individuals|persons|obesity|overweight|athletes)\b", re.I)
OBS_RE = re.compile(r"\b(prospective|retrospective|cohort|cross[- ]sectional|case[- ]control|registry|real[- ]world|longitudinal|follow[- ]up)\b", re.I)
INTERVENTION_RE = re.compile(r"\b(intervention|interventional|trial|pilot study|feeding study|dietary program|ketogenic program|treatment study)\b", re.I)

def clean(v): return re.sub(r"\s+"," ",html.unescape(v or "")).strip()

def title_of(card):
    h4=card.select_one("h4")
    if not h4: return ""
    return re.sub(r"^\s*\d+\.\s*","",clean(h4.get("data-en") or h4.get_text(" ",strip=True)))

def blob_of(card):
    return clean(" ".join([title_of(card),card.get("data-search",""),card.get_text(" ",strip=True)]))

def pmid_of(card):
    v=clean(card.get("data-pmid"))
    if v.isdigit(): return v
    for a in card.select('a[href*="pubmed.ncbi.nlm.nih.gov"]'):
        m=re.search(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)/?",a.get("href",""),re.I)
        if m: return m.group(1)
    return ""

def parse_article(a):
    def txt(path):
        n=a.find(path)
        return clean("".join(n.itertext())) if n is not None else ""
    return {
      "pmid":txt(".//PMID"),
      "title":txt(".//ArticleTitle"),
      "abstract":" ".join(clean("".join(n.itertext())) for n in a.findall(".//Abstract/AbstractText")),
      "types":[clean("".join(n.itertext())).lower() for n in a.findall(".//PublicationTypeList/PublicationType")],
      "mesh":[clean("".join(n.itertext())).lower() for n in a.findall(".//MeshHeadingList/MeshHeading/DescriptorName")],
    }

def fetch(pmids):
    out={}; failed=[]
    for i in range(0,len(pmids),BATCH_SIZE):
        batch=pmids[i:i+BATCH_SIZE]
        qs=urllib.parse.urlencode({"db":"pubmed","id":",".join(batch),"retmode":"xml"})
        req=urllib.request.Request(f"{NCBI}?{qs}",headers={"User-Agent":UA})
        try:
            with urllib.request.urlopen(req,timeout=45) as r: payload=r.read()
            root=ET.fromstring(payload); found=set()
            for a in root.findall(".//PubmedArticle"):
                rec=parse_article(a)
                if rec["pmid"]:
                    out[rec["pmid"]]=rec; found.add(rec["pmid"])
            failed.extend(p for p in batch if p not in found)
        except Exception as e:
            print("PubMed batch failed:",e); failed.extend(batch)
        time.sleep(.38)
    return out,sorted(set(failed))

def classify(title, abstract="", types=None, mesh=None, historical=False):
    if historical: return "Historical / foundational evidence"
    types_s=" | ".join(types or []).lower()
    mesh_s=" | ".join(mesh or []).lower()
    body=f"{clean(title).lower()} {clean(abstract).lower()}"
    mesh_h="humans" in mesh_s
    mesh_a=("animals" in mesh_s) or any(x in mesh_s for x in ("mice","rats","zebrafish"))
    pre=bool(ANIMAL_RE.search(body)) or any(x in body for x in ("animal model","animal study","preclinical","in vitro","cell line","cell culture","organoid")) or (mesh_a and not mesh_h)
    human=mesh_h or bool(HUMAN_RE.search(body))
    if any(x in types_s or x in body for x in ("meta-analysis","meta analysis","systematic review","scoping review","umbrella review")): return "Systematic review / meta-analysis"
    if any(x in types_s or x in body for x in ("guideline","practice guideline","consensus","position statement")): return "Guideline / consensus"
    if any(x in types_s or x in body for x in ("case reports","case report","case series")) and not pre: return "Case report / case series"
    if pre and not (mesh_h and not mesh_a): return "Preclinical / mechanistic"
    if any(x in types_s or x in body for x in ("randomized controlled trial","controlled clinical trial","randomized clinical trial","randomised clinical trial","randomised controlled trial")) or (re.search(r"\brandomi[sz]ed\b",body) and human): return "Randomized clinical trial"
    if "clinical trial" in types_s or (INTERVENTION_RE.search(body) and human): return "Clinical trial / intervention"
    if any(x in types_s for x in ("observational study","cohort studies","case-control studies","comparative study")) or (OBS_RE.search(body) and human): return "Observational human study"
    if "review" in types_s or "review" in body or "mini-review" in body: return "Review"
    if pre: return "Preclinical / mechanistic"
    if human: return "Human / clinical or translational evidence"
    if re.search(r"\b(weight loss|body composition|blood glucose|glycemic|glycaemic|insulin resistance|quality of life|seizure frequency|clinical outcomes|tolerability|adherence|efficacy|safety)\b",body,re.I): return "Human / clinical or translational evidence"
    return "Other"

def ensure_badge(soup,card,evidence):
    it,slug=LABELS[evidence]
    card["data-evidence"]=slug
    badge=card.select_one(":scope > .evidence-level")
    if badge is None:
        badge=soup.new_tag("div"); badge["class"]=["evidence-level"]
        h4=card.select_one(":scope > h4")
        h4.insert_before(badge) if h4 else card.insert(0,badge)
    badge["data-en"]=evidence; badge["data-it"]=it; badge.string=evidence

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--offline",action="store_true"); args=ap.parse_args()
    soup=BeautifulSoup(LIBRARY.read_text(encoding="utf-8"),"html.parser")
    cards=soup.select("article.folder-paper")
    candidates=[]; missing=0; generic=0
    for c in cards:
        badge=c.select_one(":scope > .evidence-level")
        ev=clean(c.get("data-evidence")).lower()
        reviewed=clean(c.get("data-evidence-reviewed")).lower()=="true"
        if badge is None:
            missing+=1; candidates.append(c)
        elif ev=="other" and not reviewed:
            generic+=1; candidates.append(c)

    pmids=sorted({pmid_of(c) for c in candidates if pmid_of(c)},key=lambda x:int(x))
    records,failed=({},[]) if args.offline else fetch(pmids)
    counts=Counter(); sources=Counter()

    for c in candidates:
        old=clean(c.get("data-evidence")).lower()
        pmid=pmid_of(c); rec=records.get(pmid)
        ev=classify(
          rec["title"] if rec else title_of(c),
          rec["abstract"] if rec else blob_of(c),
          rec["types"] if rec else [],
          rec["mesh"] if rec else [],
          historical=(old=="historical"),
        )
        ensure_badge(soup,c,ev); counts[ev]+=1
        if rec:
            c["data-evidence-source"]="pubmed"; c["data-evidence-reviewed"]="true"; sources["PubMed metadata"]+=1
        elif old=="historical":
            c["data-evidence-source"]="historical-record"; c["data-evidence-reviewed"]="true"; sources["Historical record"]+=1
        else:
            c["data-evidence-source"]="local-rules"; sources["Local conservative rules"]+=1
            if not pmid or pmid not in failed: c["data-evidence-reviewed"]="true"

    # Hard invariant: no card without a badge.
    for c in cards:
        if c.select_one(":scope > .evidence-level") is None:
            ev="Historical / foundational evidence" if clean(c.get("data-evidence")).lower()=="historical" else "Other"
            ensure_badge(soup,c,ev); c["data-evidence-source"]="fallback"

    LIBRARY.write_text(str(soup),encoding="utf-8")
    final_missing=sum(1 for c in soup.select("article.folder-paper") if c.select_one(":scope > .evidence-level") is None)
    report={
      "cards_total":len(cards),
      "candidates_processed":len(candidates),
      "initial_missing_badges":missing,
      "initial_generic_other_reviewed":generic,
      "unique_candidate_pmids":len(pmids),
      "pubmed_records_retrieved":len(records),
      "pubmed_pmids_not_retrieved":failed,
      "classification_counts":dict(sorted(counts.items())),
      "classification_sources":dict(sorted(sources.items())),
      "cards_missing_badge_after_backfill":final_missing,
    }
    REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if final_missing: raise SystemExit(1)

if __name__=="__main__": main()
