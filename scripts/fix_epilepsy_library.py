#!/usr/bin/env python3
from pathlib import Path
import re, unicodedata
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / 'library.html'

def norm(s):
    s = re.sub(r'^\s*\d+\.\s*', '', s or '')
    s = unicodedata.normalize('NFKD', s).encode('ascii','ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+','',s)

LINK_FIXES = {
    norm('The Effect of Ketonemia on the Course of Epilepsy'): ('Bibliographic record ↗','Scheda bibliografica ↗','https://cir.nii.ac.jp/crid/1570572701190809088?lang=en'),
    norm('High Fat Diets in Epilepsy'): ('Bibliographic record ↗','Scheda bibliografica ↗','https://www.sciencedirect.com/science/article/abs/pii/S152550501930914X'),
    norm('The Ketogenic Diet in the Treatment of Idiopathic Epilepsy'): ('Bibliographic record ↗','Scheda bibliografica ↗','https://www.mdpi.com/2073-4409/15/4/382'),
}

RECORDS = [
 (1921,'Fasting as a Method for Treating Epilepsy','Geyelin HR','Medical Record','1921;99:1037-1039','https://cir.nii.ac.jp/crid/1573105974779265408','record'),
 (1927,'A Clinical Study of Epileptic Children Treated by Ketogenic Diet','Talbot FB, Metcalf KM, Moriarty ME','Boston Medical and Surgical Journal','1927;196:89-96','https://doi.org/10.1056/NEJM192701201960302','doi'),
 (1927,'Epilepsy: Chemical Investigations of Rational Treatment by Production of Ketosis','Talbot FB, Metcalf KM, Moriarty ME','American Journal of Diseases of Children','1927;33(2):218-225','https://doi.org/10.1001/archpedi.1927.04130140038005','doi'),
 (1927,'Epilepsy in Children: Relationship of Variations in the Degree of Ketonuria to Occurrence of Convulsions in Epileptic Children on Ketogenic Diets','McQuarrie I, Keith HM','American Journal of Diseases of Children','1927;34(6):1013-1029','https://doi.org/10.1001/archpedi.1927.04130240092013','doi'),
 (1929,'Epilepsy in Children: The Relationship of Water Balance to the Occurrence of Seizures','McQuarrie I','American Journal of Diseases of Children','1929;38(3):451-467','https://doi.org/10.1001/archpedi.1929.01930090003001','doi'),
 (1930,"Eight Years' Experience with the Ketogenic Diet in the Treatment of Epilepsy",'Helmholz HF, Keith HM','JAMA','1930;95(10):707-709','https://doi.org/10.1001/jama.1930.02720100005002','doi'),
]

def make_article(soup, r):
    year,title,authors,journal,citation,url,kind=r
    a=soup.new_tag('article'); a['class']=['folder-paper','historical-paper']; a['data-evidence']='historical'; a['data-evidence-reviewed']='true'; a['data-evidence-source']='historical-record'; a['data-year']=str(year); a['data-search']=f'{title} {authors} {journal} {year} ketogenic diet epilepsy historical classic'.lower()
    level=soup.new_tag('div'); level['class']=['evidence-level']; level['data-en']='Historical / foundational evidence'; level['data-it']='Evidenza storica / fondativa'; level.string='Historical / foundational evidence'; a.append(level)
    h=soup.new_tag('h4'); h['data-en']=title; h['data-it']=title; h.string=title; a.append(h)
    p=soup.new_tag('p'); p['data-en']=f'{authors}. {journal}. {citation}. Historical ketogenic-diet reference.'; p['data-it']=f'{authors}. {journal}. {citation}. Riferimento storico sulla dieta chetogenica.'; p.string=p['data-en']; a.append(p)
    links=soup.new_tag('div'); links['class']=['paper-links']; x=soup.new_tag('a',href=url); x['target']='_blank'; x['rel']='noopener'; x['data-en']='DOI ↗' if kind=='doi' else 'Bibliographic record ↗'; x['data-it']='DOI ↗' if kind=='doi' else 'Scheda bibliografica ↗'; x.string=x['data-en']; links.append(x); a.append(links)
    return a

def main():
    soup=BeautifulSoup(LIBRARY.read_text(encoding='utf-8'),'html.parser')
    curated=soup.select_one('details#epilepsy .folder-curated')
    if not curated: raise SystemExit('Epilepsy section not found')
    articles=curated.select('article.folder-paper')
    by_title={norm((a.find('h4').get('data-en') if a.find('h4') else '')):a for a in articles}
    fixed=0
    for key,(en,it,url) in LINK_FIXES.items():
        a=by_title.get(key)
        if not a: continue
        links=a.select_one('.paper-links')
        if not links: links=soup.new_tag('div'); links['class']=['paper-links']; a.append(links)
        for old in list(links.select('a[href*="scholar.google"]')): old.decompose()
        if not links.select_one(f'a[href="{url}"]'):
            x=soup.new_tag('a',href=url); x['target']='_blank'; x['rel']='noopener'; x['data-en']=en; x['data-it']=it; x.string=en; links.append(x)
        fixed+=1
    existing=set(by_title)
    added=0
    for r in RECORDS:
        if norm(r[1]) not in existing:
            curated.append(make_article(soup,r)); existing.add(norm(r[1])); added+=1
    # Put historical records first, chronologically, while preserving all other cards.
    cards=curated.select(':scope > article.folder-paper')
    hist=[a for a in cards if 'historical-paper' in (a.get('class') or [])]
    other=[a for a in cards if a not in hist]
    hist.sort(key=lambda a:(int(a.get('data-year') or 9999), norm(a.find('h4').get('data-en') if a.find('h4') else '')))
    for a in cards: a.extract()
    for a in hist+other: curated.append(a)
    for i,h in enumerate(curated.select('article.folder-paper h4'),1):
        en=re.sub(r'^\s*\d+\.\s*','',h.get('data-en') or h.get_text(' ',strip=True)).strip(); it=re.sub(r'^\s*\d+\.\s*','',h.get('data-it') or en).strip(); h['data-en']=f'{i}. {en}'; h['data-it']=f'{i}. {it}'; h.string=f'{i}. {en}'
    LIBRARY.write_text(str(soup),encoding='utf-8')
    check=BeautifulSoup(LIBRARY.read_text(encoding='utf-8'),'html.parser').select_one('details#epilepsy .folder-curated')
    count=len(check.select('article.folder-paper')); scholar=len(check.select('a[href*="scholar.google"]'))
    print(f'Epilepsy records: {count}; added: {added}; links fixed: {fixed}; Scholar links remaining: {scholar}')
    if scholar: raise SystemExit('Scholar links remain in epilepsy section')

if __name__=='__main__': main()
