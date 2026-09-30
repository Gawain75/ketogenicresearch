#!/usr/bin/env python3
import json,re,time,urllib.parse,urllib.request
from difflib import SequenceMatcher
from pathlib import Path

REPORT=Path('legacy-library-reconciliation-report.json')
OUT=Path('legacy-library-second-pass-audit.json')
UA='KetogenicResearchHub/1.0 (legacy metadata audit)'

def norm(s):
 s=(s or '').lower().replace('β','beta')
 s=re.sub(r'[^a-z0-9]+',' ',s)
 return ' '.join(s.split())

def score(a,b):
 a,b=norm(a),norm(b)
 if not a or not b:return 0
 seq=SequenceMatcher(None,a,b).ratio()
 A,B=set(a.split()),set(b.split()); jac=len(A&B)/max(1,len(A|B))
 containment=len(A&B)/max(1,min(len(A),len(B)))
 return round(.55*seq+.25*jac+.20*containment,4)

def get_json(url):
 req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'application/json'})
 with urllib.request.urlopen(req,timeout=25) as r:return json.load(r)

def variants(t):
 n=norm(t); words=n.split(); out=[t]
 # progressively shorter searches help truncated/paraphrased legacy titles
 for k in (12,9,7,5):
  if len(words)>k: out.append(' '.join(words[:k]))
 # remove common generic leading wording
 out.append(re.sub(r'^(the |a |an )','',t,flags=re.I))
 return list(dict.fromkeys(x for x in out if len(x)>12))

def pubmed(q):
 try:
  u='https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?'+urllib.parse.urlencode({'db':'pubmed','term':q+'[Title]','retmode':'json','retmax':5})
  ids=get_json(u).get('esearchresult',{}).get('idlist',[])
  if not ids:return []
  u='https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?'+urllib.parse.urlencode({'db':'pubmed','id':','.join(ids),'retmode':'json'})
  d=get_json(u).get('result',{}); out=[]
  for i in ids:
   x=d.get(i,{}); arts=x.get('articleids',[]) or []
   doi=next((a.get('value','') for a in arts if a.get('idtype')=='doi'),'')
   out.append({'source':'PubMed','title':x.get('title',''),'pmid':i,'doi':doi,'year':(x.get('pubdate','') or '')[:4]})
  return out
 except Exception:return []

def crossref(q):
 try:
  u='https://api.crossref.org/works?'+urllib.parse.urlencode({'query.title':q,'rows':5,'select':'DOI,title,published-print,published-online,issued'})
  items=get_json(u).get('message',{}).get('items',[]); out=[]
  for x in items:
   title=(x.get('title') or [''])[0]
   year=''
   for key in ('published-print','published-online','issued'):
    parts=(x.get(key) or {}).get('date-parts') or []
    if parts and parts[0]: year=str(parts[0][0]); break
   out.append({'source':'Crossref','title':title,'pmid':'','doi':x.get('DOI',''),'year':year})
  return out
 except Exception:return []

def main():
 if not REPORT.exists(): raise SystemExit(f'Missing {REPORT}')
 titles=json.loads(REPORT.read_text(encoding='utf-8')).get('unresolved_titles',[])
 results=[]
 for idx,t in enumerate(titles,1):
  candidates={}
  for q in variants(t):
   for c in pubmed(q)+crossref(q):
    key=(c.get('doi','').lower() or 'pmid:'+c.get('pmid','') or norm(c.get('title','')))
    s=score(t,c.get('title',''))
    if key and (key not in candidates or s>candidates[key]['score']): c['score']=s;candidates[key]=c
   if candidates and max(x['score'] for x in candidates.values())>=.94: break
   time.sleep(.12)
  best=sorted(candidates.values(),key=lambda x:x['score'],reverse=True)[:3]
  top=best[0]['score'] if best else 0
  # exact = safe for automatic metadata replacement; probable = human review; otherwise unfound
  status='identified' if top>=.91 else ('probable' if top>=.76 else 'not_found')
  results.append({'legacy_title':t,'status':status,'best_score':top,'candidates':best})
  print(f'[{idx}/{len(titles)}] {status:10} {top:.3f}  {t}')
  time.sleep(.18)
 counts={k:sum(r['status']==k for r in results) for k in ('identified','probable','not_found')}
 OUT.write_text(json.dumps({'audited':len(results),'counts':counts,'policy':'Audit only: no Library records are modified or deleted. identified >=0.91; probable 0.76-0.9099; not_found <0.76.','records':results},ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(counts,indent=2))
if __name__=='__main__': main()
