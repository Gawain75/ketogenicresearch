#!/usr/bin/env python3
from pathlib import Path
from bs4 import BeautifulSoup
import json,re,sys

LIB=Path('library.html')
REPORT=Path('legacy-library-dedup-report.json')
if not LIB.exists():
    raise SystemExit('library.html not found')
html=LIB.read_text(encoding='utf-8')
soup=BeautifulSoup(html,'html.parser')
articles=soup.select('article.folder-paper')

def ids(a):
    pmids=set(); dois=set()
    text=a.get_text(' ',strip=True)
    for m in re.finditer(r'PMID\s*:\s*(\d{6,9})',text,re.I): pmids.add(m.group(1))
    for x in a.select('a[href]'):
        h=x.get('href','')
        m=re.search(r'pubmed\.ncbi\.nlm\.nih\.gov/(\d{6,9})',h,re.I)
        if m: pmids.add(m.group(1))
        m=re.search(r'doi\.org/(10\.\d{4,9}/[^?#\s]+)',h,re.I)
        if m: dois.add(m.group(1).rstrip('.,;').lower())
    for m in re.finditer(r'DOI\s*:\s*(10\.\d{4,9}/[^\s<]+)',text,re.I):
        dois.add(m.group(1).rstrip('.,;').lower())
    return pmids,dois

def legacy(a):
    t=a.get_text(' ',strip=True).lower()
    return ('bibliographic record reviewed for inclusion' in t or
            'riferimento bibliografico revisionato per' in t or
            a.get('data-year') in (None,'','unknown'))

def quality(a):
    pm,do=ids(a); q=0
    q += 20*bool(pm)+20*bool(do)
    q += 10*bool(a.select_one('.paper-source-abstract'))
    q += 8*bool(a.select_one('a[data-link-kind="fulltext"]'))
    q += 8*bool(a.select_one('a[data-link-kind="pdf"]'))
    q += min(len(a.get_text(' ',strip=True))//300,10)
    q -= 50*legacy(a)
    return q

by_pmid={}; by_doi={}
for a in articles:
    pm,do=ids(a)
    for k in pm: by_pmid.setdefault(k,[]).append(a)
    for k in do: by_doi.setdefault(k,[]).append(a)

groups=[]; seen=set()
for d,kind in ((by_pmid,'pmid'),(by_doi,'doi')):
    for key,arr in d.items():
        uniq=[]
        for a in arr:
            if id(a) not in {id(x) for x in uniq}: uniq.append(a)
        if len(uniq)<2: continue
        sig=tuple(sorted(id(x) for x in uniq))
        if sig in seen: continue
        seen.add(sig); groups.append((kind,key,uniq))

removed=[]
for kind,key,arr in groups:
    # Safety: only act when at least one copy is clearly legacy/degraded.
    legacy_copies=[a for a in arr if legacy(a)]
    nonlegacy=[a for a in arr if not legacy(a)]
    if not legacy_copies or not nonlegacy: continue
    keep=max(nonlegacy,key=quality)
    keep_title=(keep.select_one('h4').get_text(' ',strip=True) if keep.select_one('h4') else '')
    for a in legacy_copies:
        title=a.select_one('h4').get_text(' ',strip=True) if a.select_one('h4') else ''
        pm,do=ids(a)
        removed.append({'matched_by':kind,'identifier':key,'removed_title':title,'kept_title':keep_title,'pmid':sorted(pm),'doi':sorted(do)})
        a.decompose()

if removed:
    LIB.write_text(str(soup),encoding='utf-8')
REPORT.write_text(json.dumps({'duplicates_removed':len(removed),'records':removed},ensure_ascii=False,indent=2),encoding='utf-8')
print(f'Duplicate legacy records removed: {len(removed)}')
print(f'Report: {REPORT}')
