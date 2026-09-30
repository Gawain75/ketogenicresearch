#!/usr/bin/env python3
from __future__ import annotations
import json,re
from pathlib import Path
from collections import defaultdict
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
LIB=ROOT/'library.html'
AUDIT=ROOT/'legacy-library-second-pass-audit.json'
OUT=ROOT/'legacy-library-finalization-report.json'
GENERIC=('Bibliographic record reviewed for inclusion','Riferimento bibliografico revisionato')
STOP={'a','an','the','of','and','or','in','on','for','to','with','from','by','as','at','is','are'}

def norm(s):
 s=(s or '').lower().replace('β','beta').replace('’',"'")
 s=re.sub(r'^\s*\d+\.\s*','',s)
 return ' '.join(re.sub(r'[^a-z0-9]+',' ',s).split())
def words(s): return [x for x in norm(s).split() if x not in STOP and len(x)>2]
def doi_norm(s):
 s=(s or '').strip().lower(); s=re.sub(r'^https?://(?:dx\.)?doi\.org/','',s)
 return s.rstrip(' .;,') if s.startswith('10.') else ''
def safe_candidate(legacy,cand,score):
 # Conservative final auto-acceptance. A merely fuzzy title is never enough.
 a,b=norm(legacy),norm(cand.get('title',''))
 A,B=set(words(a)),set(words(b)); cover=len(A&B)/max(1,len(A)); reverse=len(A&B)/max(1,len(B))
 prefix=(b.startswith(a+' ') or a.startswith(b+' ')) and len(A)>=4
 ident=bool((cand.get('pmid') or '').strip() or doi_norm(cand.get('doi','')))
 return ident and ((score>=.88 and cover>=.88 and reverse>=.72) or (prefix and cover>=.95))
def card_title(card):
 h=card.find('h4'); return re.sub(r'^\s*\d+\.\s*','',(h.get('data-en') if h else '') or (h.get_text(' ',strip=True) if h else '')).strip()
def is_legacy(card):
 p=card.find('p',recursive=False)
 return bool(p and any(g in p.get_text(' ',strip=True) for g in GENERIC))
def existing_ids(soup,skip=None):
 pmids=set(); dois=set()
 for c in soup.select('article.folder-paper.drive-paper'):
  if c is skip: continue
  p=(c.get('data-pmid') or '').strip(); d=doi_norm(c.get('data-doi') or '')
  if p: pmids.add(p)
  if d: dois.add(d)
 return pmids,dois
def apply_metadata(card,cand):
 h=card.find('h4'); p=card.find('p',recursive=False); num=''
 if h:
  m=re.match(r'^(\s*\d+\.\s*)',h.get_text(' ',strip=True)); num=m.group(1) if m else ''
  old_it=h.get('data-it',''); old_en=card_title(card); h['data-en']=cand['title']; h.string=num+cand['title']
  if not old_it or norm(old_it)==norm(old_en): h['data-it']=cand['title']
 pmid=(cand.get('pmid') or '').strip(); doi=doi_norm(cand.get('doi','')); year=str(cand.get('year') or '').strip()
 if pmid: card['data-pmid']=pmid
 if doi: card['data-doi']=doi
 if year: card['data-year']=year
 bits=[]
 if year: bits.append(year)
 if pmid: bits.append('PMID: '+pmid)
 if doi: bits.append('DOI: '+doi)
 line='. '.join(bits)+('.' if bits else '')
 if p and line: p['data-en']=line; p['data-it']=line; p.string=line
 links=card.find('div',class_='paper-links')
 if links:
  for a in list(links.find_all('a',href=True)):
   if 'pubmed.ncbi.nlm.nih.gov/?term=' in a['href']: a.decompose()
  for label,url in [('PubMed ↗',f'https://pubmed.ncbi.nlm.nih.gov/{pmid}/' if pmid else ''),('DOI ↗',f'https://doi.org/{doi}' if doi else '')]:
   if url and not any(a.get('href')==url for a in links.find_all('a',href=True)):
    links.append(BeautifulSoup(f'<a href="{url}" target="_blank" rel="noopener" data-en="{label}" data-it="{label}">{label}</a>','html.parser').a)

def main():
 if not LIB.exists() or not AUDIT.exists(): raise SystemExit('Missing library.html or legacy-library-second-pass-audit.json')
 audit=json.loads(AUDIT.read_text(encoding='utf-8')); recs=audit.get('records',[])
 soup=BeautifulSoup(LIB.read_text(encoding='utf-8'),'html.parser')
 bytitle=defaultdict(list)
 for c in soup.select('article.folder-paper.drive-paper'):
  if is_legacy(c): bytitle[norm(card_title(c))].append(c)
 corrected=[]; removed=[]; duplicate_removed=[]; manual=[]; missing=[]
 for r in recs:
  legacy=r.get('legacy_title',''); key=norm(legacy)
  # The audit can contain duplicate legacy titles. A Tag that has already been
  # decomposed has attrs=None, so never reuse it on a later audit row.
  candidates=bytitle.get(key,[])
  while candidates and getattr(candidates[0],'attrs',None) is None:
   candidates.pop(0)
  card=candidates.pop(0) if candidates else None
  if card is None: missing.append(legacy); continue
  # Never touch a legacy-looking card that already acquired a stable identifier since the audit.
  if (card.get('data-pmid') or '').strip() or doi_norm(card.get('data-doi') or ''):
   manual.append({'legacy_title':legacy,'reason':'card now has PMID/DOI; left untouched'}); continue
  status=r.get('status'); best=(r.get('candidates') or [{}])[0]; score=float(r.get('best_score') or 0)
  if status=='probable' and best.get('title') and safe_candidate(legacy,best,score):
   pmids,dois=existing_ids(soup,card); p=(best.get('pmid') or '').strip(); d=doi_norm(best.get('doi') or '')
   if (p and p in pmids) or (d and d in dois):
    card.decompose(); duplicate_removed.append({'legacy_title':legacy,'matched_title':best.get('title'),'pmid':p,'doi':d})
   else:
    apply_metadata(card,best); corrected.append({'legacy_title':legacy,'canonical_title':best.get('title'),'score':score,'pmid':p,'doi':d,'source':best.get('source','')})
  elif status=='not_found':
   card.decompose(); removed.append({'legacy_title':legacy,'reason':'second-pass audit: no sufficiently reliable bibliographic match'})
  else:
   # Final cleanup: an unresolved generic legacy card with no PMID/DOI is not a verified publication.
   card.decompose(); removed.append({'legacy_title':legacy,'reason':'probable match remained unverified; generic legacy card removed'})
 LIB.write_text(str(soup),encoding='utf-8')
 report={'audited':len(recs),'corrected':len(corrected),'duplicates_removed':len(duplicate_removed),'unverified_removed':len(removed),'manual_review':len(manual),'cards_missing_since_audit':len(missing),'policy':'Only generic legacy cards without PMID/DOI are eligible. Verified probable matches may be corrected; all remaining unverified generic legacy cards are removed. Existing canonical duplicates are preserved and the legacy copy is removed.','corrected_records':corrected,'duplicate_legacy_records_removed':duplicate_removed,'unverified_records_removed':removed,'manual_review_records':manual,'missing_records':missing}
 OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({k:report[k] for k in ('audited','corrected','duplicates_removed','unverified_removed','manual_review','cards_missing_since_audit')},indent=2))
if __name__=='__main__': main()
