#!/usr/bin/env python3
from __future__ import annotations
import json, os, re, time, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from difflib import SequenceMatcher
from pathlib import Path
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]; LIB=ROOT/'library.html'; REPORT=ROOT/'legacy-library-reconciliation-report.json'
EMAIL=os.getenv('NCBI_EMAIL') or 'info@ketogenicresearch.org'; KEY=os.getenv('NCBI_API_KEY',''); UA=f'ketogenicresearch-legacy-reconcile/2.0 ({EMAIL})'
GENERIC=('Bibliographic record reviewed for inclusion','Riferimento bibliografico revisionato')
STOP={'a','an','the','of','and','or','in','on','for','to','with','from','by','as','at','is','are'}

def norm(s):
 s=(s or '').lower().replace('’',"'").replace('–','-').replace('—','-'); s=re.sub(r'^\s*\d+\.\s*','',s); return ' '.join(re.sub(r'[^a-z0-9]+',' ',s).split())
def doi_norm(s):
 s=(s or '').strip().lower(); s=re.sub(r'^https?://(?:dx\.)?doi\.org/','',s); return s.rstrip(' .;,') if s.startswith('10.') else ''
def words(s): return [x for x in norm(s).split() if x not in STOP and len(x)>2]
def match(src,cand):
 a,b=norm(src),norm(cand)
 if not a or not b:return False,0
 if a==b:return True,1
 seq=SequenceMatcher(None,a,b).ratio(); A,B=set(words(a)),set(words(b)); cover=len(A&B)/max(1,len(A)); jac=len(A&B)/max(1,len(A|B))
 # Exact abbreviated/prefix title: allow canonical title to add a subtitle/suffix.
 prefix=b.startswith(a+' ') and len(A)>=4 and len(a)>=28 and cover==1
 ok=seq>=.94 or (seq>=.88 and jac>=.75) or (prefix and seq>=.58)
 return ok, max(seq, .93 if prefix else seq)
def request(url, accept='application/json'):
 req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':accept}); last=None
 for n in range(5):
  try:
   with urllib.request.urlopen(req,timeout=60) as r:return r.read()
  except Exception as e:
   last=e; time.sleep(min(20,2**(n+1)))
 raise last
def eurl(name,params):
 p={**params,'tool':'ketogenicresearch','email':EMAIL};
 if KEY:p['api_key']=KEY
 return 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/'+name+'?'+urllib.parse.urlencode(p)
def pubmed_search(title):
 qs=[f'"{title.replace(chr(34),"")}"[Title]']
 w=words(title)
 if len(w)>=4: qs.append(' AND '.join(f'{x}[Title]' for x in w[:10]))
 ids=[]
 for q in qs:
  try:d=json.loads(request(eurl('esearch.fcgi',{'db':'pubmed','term':q,'retmode':'json','retmax':10})).decode())
  except Exception:continue
  for x in d.get('esearchresult',{}).get('idlist',[]):
   if x not in ids:ids.append(x)
  if ids: break
  time.sleep(.12 if KEY else .35)
 return ids[:10]
def txt(n): return '' if n is None else ''.join(n.itertext()).strip()
def pubmed_fetch(ids):
 if not ids:return []
 root=ET.fromstring(request(eurl('efetch.fcgi',{'db':'pubmed','id':','.join(ids),'retmode':'xml'}),'application/xml'))
 out=[]
 for x in root.findall('.//PubmedArticle'):
  cit=x.find('MedlineCitation'); art=cit.find('Article') if cit is not None else None
  if art is None:continue
  title=txt(art.find('ArticleTitle')); pmid=txt(cit.find('PMID')); journal=txt(art.find('Journal/ISOAbbreviation')) or txt(art.find('Journal/Title'))
  authors=[]
  for a in art.findall('AuthorList/Author'):
   name=' '.join(z for z in [txt(a.find('LastName')),txt(a.find('Initials'))] if z)
   if name:authors.append(name)
  abstract=' '.join(txt(a) for a in art.findall('Abstract/AbstractText') if txt(a))
  doi=''
  for aid in x.findall('./PubmedData/ArticleIdList/ArticleId'):
   if (aid.get('IdType') or '').lower()=='doi':doi=txt(aid);break
  year=''
  for n in [art.find('Journal/JournalIssue/PubDate/Year'), art.find('ArticleDate/Year')]:
   if txt(n).isdigit():year=txt(n);break
  if not year:
   md=txt(art.find('Journal/JournalIssue/PubDate/MedlineDate')); m=re.search(r'\b(19|20)\d{2}\b',md); year=m.group(0) if m else ''
  out.append(dict(title=title,pmid=pmid,doi=doi_norm(doi),journal=journal,authors=authors,year=year,abstract=abstract,source='PubMed'))
 return out
def crossref(title):
 url='https://api.crossref.org/works?rows=8&select=DOI,title,author,container-title,published-print,published-online,issued,type&query.title='+urllib.parse.quote(title)+'&mailto='+urllib.parse.quote(EMAIL)
 try:items=json.loads(request(url).decode()).get('message',{}).get('items',[])
 except Exception:return []
 out=[]
 for i in items:
  ct=(i.get('title') or [''])[0]; ok,score=match(title,ct)
  if not ok:continue
  year=''
  for k in ('published-print','published-online','issued'):
   p=(i.get(k) or {}).get('date-parts') or []
   if p and p[0]:year=str(p[0][0]);break
  authors=[]
  for a in i.get('author') or []:
   fam=(a.get('family') or '').strip(); giv=(a.get('given') or '').strip(); ini=''.join(z[0] for z in re.split(r'[\s.-]+',giv) if z); name=' '.join(z for z in [fam,ini] if z)
   if name:authors.append(name)
  out.append((score,dict(title=ct,doi=doi_norm(i.get('DOI','')),journal=(i.get('container-title') or [''])[0],authors=authors,year=year,abstract='',source='Crossref')))
 return [x[1] for x in sorted(out,key=lambda x:x[0],reverse=True)]
def bibliographic(rec):
 parts=[]
 if rec['authors']:parts.append(', '.join(rec['authors'][:6])+(' et al.' if len(rec['authors'])>6 else ''))
 if rec['journal']:parts.append(rec['journal'])
 if rec['year']:parts.append(rec['year'])
 if rec['pmid']:parts.append('PMID: '+rec['pmid'])
 if rec['doi']:parts.append('DOI: '+rec['doi'])
 return '. '.join(parts)+('.' if parts else '')
def add_link(box,label,url):
 if any(a.get('href')==url for a in box.find_all('a',href=True)):return
 a=box.new_tag('a') if hasattr(box,'new_tag') else None
 # BeautifulSoup Tag.new_tag is not reliable across versions; caller handles via fragment.
def main():
 soup=BeautifulSoup(LIB.read_text(encoding='utf-8'),'html.parser'); targets=[]
 for card in soup.select('article.folder-paper.drive-paper'):
  p=card.find('p',recursive=False); h=card.find('h4')
  if not p or not h:continue
  if any(g in p.get_text(' ',strip=True) for g in GENERIC): targets.append((card,p,h))
 print('Unresolved legacy cards:',len(targets)); resolved=[]; unresolved=[]
 for n,(card,p,h) in enumerate(targets,1):
  raw=h.get('data-en') or h.get_text(' ',strip=True); num=''; m=re.match(r'^(\s*\d+\.\s*)',h.get_text(' ',strip=True)); num=m.group(1) if m else ''; title=re.sub(r'^\s*\d+\.\s*','',raw).strip()
  best=None
  try:
   for rec in pubmed_fetch(pubmed_search(title)):
    ok,score=match(title,rec['title'])
    if ok and (best is None or score>best[0]):best=(score,rec)
  except Exception as e: print('PubMed error',title[:70],e)
  if best is None:
   try:
    cr=crossref(title)
    if cr:
     rec=cr[0]; ok,score=match(title,rec['title']); best=(score,rec) if ok else None
   except Exception as e: print('Crossref error',title[:70],e)
  if best is None:
   unresolved.append(title); continue
  score,rec=best
  # Canonicalize the English title; preserve an existing genuine Italian translation if present.
  old_it=h.get('data-it',''); h['data-en']=rec['title']; h.string=num+rec['title']
  if old_it and norm(old_it)!=norm(title):h['data-it']=old_it
  if rec['year']:card['data-year']=rec['year']
  if rec['pmid']:card['data-pmid']=rec['pmid']
  if rec['doi']:card['data-doi']=rec['doi']
  line=bibliographic(rec); p['data-en']=line; p['data-it']=line; p.string=line
  details=card.find('details',class_='paper-study-details')
  if rec['abstract'] and details:
   ap=details.find('p',class_='paper-source-abstract')
   if ap:
    ap['data-en']=rec['abstract']; ap.string=rec['abstract']; details['data-detail-source']='pubmed-abstract'
  links=card.find('div',class_='paper-links')
  if links:
   for a in list(links.find_all('a',href=True)):
    if 'pubmed.ncbi.nlm.nih.gov/?term=' in a['href']:a.decompose()
   for label,url in [('PubMed ↗',f"https://pubmed.ncbi.nlm.nih.gov/{rec['pmid']}/" if rec['pmid'] else ''),('DOI ↗',f"https://doi.org/{rec['doi']}" if rec['doi'] else '')]:
    if url and not any(a.get('href')==url for a in links.find_all('a',href=True)):
     frag=BeautifulSoup(f'<a href="{url}" target="_blank" rel="noopener" data-en="{label}" data-it="{label}">{label}</a>','html.parser').a; links.append(frag)
  resolved.append({'old_title':title,'canonical_title':rec['title'],'source':rec['source'],'score':round(score,4),'pmid':rec['pmid'],'doi':rec['doi'],'year':rec['year']})
  if n%20==0:print(f'Processed {n}/{len(targets)}')
  time.sleep(.12 if KEY else .35)
 LIB.write_text(str(soup),encoding='utf-8')
 REPORT.write_text(json.dumps({'targeted':len(targets),'resolved':len(resolved),'unresolved':len(unresolved),'resolved_records':resolved,'unresolved_titles':unresolved},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(f'Resolved {len(resolved)}/{len(targets)}; unresolved {len(unresolved)}')
if __name__=='__main__':main()
