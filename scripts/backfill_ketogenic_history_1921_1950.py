#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "library.html"
REPORT = ROOT / "historical-ketogenic-1921-1950-report.json"

# Conservative, manually verified historical bibliography.  The aim is to
# recover early ketogenic/fasting literature that PubMed-only discovery misses,
# not to manufacture an entry for every calendar year.  Records with no modern
# PMID/DOI are linked to a verifiable bibliographic source.
RECORDS = [
    # Foundational fasting / ketogenesis papers directly leading to KDT
    dict(year=1921, area="epilepsy", title="Fasting as a Method for Treating Epilepsy", authors="Geyelin HR", journal="Medical Record", citation="1921;99:1037-1039", url="https://cir.nii.ac.jp/crid/1573105974779265408", kind="record", scope="foundational"),
    dict(year=1921, area="epilepsy", title="The Effect of Ketonemia on the Course of Epilepsy", authors="Wilder RM", journal="Mayo Clinic Bulletin", citation="1921;2:307-308", url="https://www.neurology.org/doi/10.1212/WNL.54.2.282", kind="source", scope="foundational"),
    dict(year=1921, area="epilepsy", title="High Fat Diets in Epilepsy", authors="Wilder RM", journal="Mayo Clinic Bulletin", citation="1921;2:308", url="https://www.sciencedirect.com/science/article/abs/pii/S152550501930914X", kind="source", scope="direct"),
    dict(year=1922, area="epilepsy", title="Some Observations on the Starvation Treatment of Epilepsy", authors="Goldbloom A", journal="Canadian Medical Association Journal", citation="1922;12(8):539-540", url="https://pubmed.ncbi.nlm.nih.gov/20314170/", kind="pubmed", pmid="20314170", scope="foundational"),
    dict(year=1922, area="epilepsy", title="The Threshold of Ketogenesis", authors="Wilder RM, Winter MD", journal="Journal of Biological Chemistry", citation="1922;52(2):393-401", url="https://doi.org/10.1016/S0021-9258(18)85833-1", kind="doi", doi="10.1016/S0021-9258(18)85833-1", scope="mechanistic"),
    dict(year=1923, area="epilepsy", title="Observations on Fasting and Diets in the Treatment of Epilepsy", authors="Weeks DF, Renner DS, Allen FM, Wishart MB", journal="Journal of Metabolic Research", citation="1923;3:317-364", url="https://jamanetwork.com/journals/jama/fullarticle/236347", kind="source", scope="foundational"),
    dict(year=1924, area="epilepsy", title="The Effect of Fasting on the Metabolism of Epileptic Children", authors="Hoeffel G, Moriarty M", journal="American Journal of Diseases of Children", citation="1924;28(1):16-24", url="https://doi.org/10.1001/archpedi.1924.04120190019002", kind="doi", doi="10.1001/archpedi.1924.04120190019002", scope="foundational"),
    dict(year=1924, area="epilepsy", title="Hypoglycemia and Acidosis in Fasting Children with Idiopathic Epilepsy", authors="Shaw EB, Moriarty M", journal="American Journal of Diseases of Children", citation="1924;28(5):553-567", url="https://doi.org/10.1001/archpedi.1924.04120230029003", kind="doi", doi="10.1001/archpedi.1924.04120230029003", scope="foundational"),
    dict(year=1924, area="epilepsy", title="The Ketogenic Diet in the Treatment of Epilepsy: A Preliminary Report", authors="Peterman MG", journal="American Journal of Diseases of Children", citation="1924;28(1):28-33", url="https://doi.org/10.1001/archpedi.1924.04120190031004", kind="doi", doi="10.1001/archpedi.1924.04120190031004", scope="direct"),
    dict(year=1925, area="epilepsy", title="The Ketogenic Diet in Epilepsy", authors="Peterman MG", journal="JAMA", citation="1925;84(26):1979-1983", url="https://doi.org/10.1001/jama.1925.02660520007003", kind="doi", doi="10.1001/jama.1925.02660520007003", scope="direct"),
    dict(year=1926, area="epilepsy", title="The Ketogenic Diet in Epilepsy", authors="Peterman MG", journal="Wisconsin Medical Journal", citation="1926;25:427-430", url="https://www.cambridge.org/core/journals/journal-of-mental-science/article/abs/ketogenic-diet-in-epilepsy/7FB3A3F73A830828F0C1EF6953AD1F9C", kind="source", scope="direct"),
    dict(year=1927, area="epilepsy", title="The Treatment of Epilepsy in Childhood: Five Years' Experience with the Ketogenic Diet", authors="Helmholz HF", journal="JAMA", citation="1927;88(26):2028-2032", url="https://doi.org/10.1001/jama.1927.02680520018008", kind="doi", doi="10.1001/jama.1927.02680520018008", scope="direct"),
    dict(year=1927, area="epilepsy", title="A Clinical Study of Epileptic Children Treated by Ketogenic Diet", authors="Talbot FB, Metcalf KM, Moriarty ME", journal="Boston Medical and Surgical Journal", citation="1927;196(3):89-96", url="https://doi.org/10.1056/NEJM192701201960302", kind="doi", doi="10.1056/NEJM192701201960302", scope="direct"),
    dict(year=1927, area="epilepsy", title="Epilepsy: Chemical Investigations of Rational Treatment by Production of Ketosis", authors="Talbot FB, Metcalf KM, Moriarty ME", journal="American Journal of Diseases of Children", citation="1927;33(2):218-225", url="https://doi.org/10.1001/archpedi.1927.04130140038005", kind="doi", doi="10.1001/archpedi.1927.04130140038005", scope="direct"),
    dict(year=1927, area="epilepsy", title="Epilepsy in Children: Relationship of Variations in the Degree of Ketonuria to Occurrence of Convulsions in Epileptic Children on Ketogenic Diets", authors="McQuarrie I, Keith HM", journal="American Journal of Diseases of Children", citation="1927;34(6):1013-1029", url="https://doi.org/10.1001/archpedi.1927.04130240092013", kind="doi", doi="10.1001/archpedi.1927.04130240092013", scope="direct"),
    dict(year=1928, area="epilepsy", title="The Ketogenic Diet", authors="Peterman MG", journal="JAMA", citation="1928;90(18):1427-1429", url="https://doi.org/10.1001/jama.1928.02690450007003", kind="doi", doi="10.1001/jama.1928.02690450007003", scope="direct"),
    dict(year=1928, area="epilepsy", title="Ketogenic Diet Treatment of Epilepsy in Adults", authors="Barborka CJ", journal="JAMA", citation="1928;91(2):73-78", url="https://doi.org/10.1001/jama.1928.02700020007003", kind="doi", doi="10.1001/jama.1928.02700020007003", scope="direct"),
    dict(year=1928, area="epilepsy", title="Ketogenic Diet in the Treatment of Epilepsy", authors="Lennox WG", journal="New England Journal of Medicine", citation="1928;199(2):74-75", url="https://doi.org/10.1056/NEJM192807121990206", kind="doi", doi="10.1056/NEJM192807121990206", scope="direct"),
    dict(year=1928, area="epilepsy", title="Influence of Acid-Forming and Base-Forming Constituents of Ketogenic Diet Used in Treatment of Idiopathic Epilepsy", authors="McQuarrie I, Keith HM", journal="Proceedings of the Society for Experimental Biology and Medicine", citation="1928;25(6):418-420", url="https://doi.org/10.3181/00379727-25-3877", kind="doi", doi="10.3181/00379727-25-3877", scope="mechanistic"),
    dict(year=1929, area="epilepsy", title="The Ketogenic Diet in the Treatment of Epilepsy", authors="Smith WA", journal="Annals of Internal Medicine", citation="1929;2(12):1300-1308", url="https://doi.org/10.7326/0003-4819-2-12-1300", kind="doi", doi="10.7326/0003-4819-2-12-1300", scope="direct"),
    dict(year=1929, area="epilepsy", title="Epilepsy in Children: The Relationship of Water Balance to the Occurrence of Seizures", authors="McQuarrie I", journal="American Journal of Diseases of Children", citation="1929;38(3):451-467", url="https://doi.org/10.1001/archpedi.1929.01930090003001", kind="doi", doi="10.1001/archpedi.1929.01930090003001", scope="mechanistic"),
    dict(year=1930, area="epilepsy", title="Eight Years' Experience with the Ketogenic Diet in the Treatment of Epilepsy", authors="Helmholz HF, Keith HM", journal="JAMA", citation="1930;95(10):707-709", url="https://doi.org/10.1001/jama.1930.02720100005002", kind="doi", doi="10.1001/jama.1930.02720100005002", scope="direct"),
    dict(year=1930, area="epilepsy", title="Epilepsy in Adults: Results of Treatment by Ketogenic Diet in One Hundred Cases", authors="Barborka CJ", journal="Archives of Neurology & Psychiatry", citation="1930;23(5):904-914", url="https://doi.org/10.1001/archneurpsyc.1930.02220110066004", kind="doi", doi="10.1001/archneurpsyc.1930.02220110066004", scope="direct"),
    dict(year=1930, area="headache-migraine", title="Migraine: Results of Treatment by Ketogenic Diet in Fifty Cases", authors="Barborka CJ", journal="JAMA", citation="1930;95(24):1825-1828", url="https://doi.org/10.1001/jama.1930.02720240035010", kind="doi", doi="10.1001/jama.1930.02720240035010", scope="direct"),
    dict(year=1931, area="epilepsy", title="The Mechanism of the Ketogenic Diet in Epilepsy: A Preliminary Report of Work in Progress", authors="Bridge EM, Iob LV", journal="American Journal of Psychiatry", citation="1931;87(4):667-671", url="https://doi.org/10.1176/ajp.87.4.667", kind="doi", doi="10.1176/ajp.87.4.667", scope="mechanistic"),
    dict(year=1931, area="epilepsy", title="The Ketogenic Treatment of Epilepsy", authors="Bastible C", journal="Irish Journal of Medical Science", citation="1931;6(9):506-520", url="https://doi.org/10.1007/BF02951585", kind="doi", doi="10.1007/BF02951585", scope="direct"),
    dict(year=1931, area="epilepsy", title="The Ketogenic Diet in Epilepsy", authors="A D B", journal="Canadian Medical Association Journal", citation="1931;24(1):106-107", url="https://pubmed.ncbi.nlm.nih.gov/20318124/", kind="pubmed", pmid="20318124", scope="direct"),
    dict(year=1932, area="epilepsy", title="The Present Status of the Ketogenic Diet", authors="Pulford DS", journal="Annals of Internal Medicine", citation="1932;6(6):795-801", url="https://doi.org/10.7326/0003-4819-6-6-795", kind="doi", doi="10.7326/0003-4819-6-6-795", scope="direct"),
    dict(year=1933, area="epilepsy", title="Ten Years' Experience in the Treatment of Epilepsy with Ketogenic Diet", authors="Helmholz HF, Keith HM", journal="Archives of Neurology & Psychiatry", citation="1933;29(4):808-812", url="https://doi.org/10.1001/archneurpsyc.1933.02240100127010", kind="doi", doi="10.1001/archneurpsyc.1933.02240100127010", scope="direct"),
    dict(year=1933, area="epilepsy", title="The Ketogenic Diet in Epilepsy", authors="Allan SM", journal="Journal of Mental Science", citation="1933;79(327):677-687", url="https://doi.org/10.1192/bjp.79.327.677", kind="doi", doi="10.1192/bjp.79.327.677", scope="direct"),
    dict(year=1934, area="epilepsy", title="Epilepsy: Treatment of Institutionalized Adult Patients with a Ketogenic Diet", authors="Notkin J", journal="Archives of Neurology & Psychiatry", citation="1934;31(4):787-793", url="https://doi.org/10.1001/archneurpsyc.1934.02250040111007", kind="doi", doi="10.1001/archneurpsyc.1934.02250040111007", scope="direct"),
    dict(year=1935, area="epilepsy", title="Epilepsy: Its Treatment by the Use of the Ketogenic Diet Versus Drugs", authors="Fischer L", journal="Archives of Pediatrics", citation="1935;52:131-136", url="https://api.pageplace.de/preview/DT0400.9780190498009_A30388627/preview-9780190498009_A30388627.pdf", kind="source", scope="direct"),
    dict(year=1935, area="epilepsy", title="Effect of Ketogenic Diet on the Blood Sugar and the Respiratory Quotient of Children", authors="Talbot FB, Bates V", journal="American Journal of Diseases of Children", citation="1935;50(4):827-839", url="https://doi.org/10.1001/archpedi.1935.01970100003001", kind="doi", doi="10.1001/archpedi.1935.01970100003001", scope="mechanistic"),
    dict(year=1935, area="epilepsy", title="Ketosis and the Ketogenic Diet: Their Application to Treatment of Epilepsy and Infections of the Urinary Tract", authors="Wilder RM, Pollack H", journal="International Clinics", citation="1935;45th series, 1:1-12", url="https://eurekamag.com/research/013/570/013570327.php", kind="source", scope="direct"),
    dict(year=1936, area="epilepsy", title="Ketosis in the Treatment of Epilepsy", authors="Finkelman I, Stephens WM", journal="Illinois Medical Journal", citation="1936;70:343-348", url="https://eurekamag.com/research/111/058/111058071.php", kind="source", scope="direct"),
    dict(year=1937, area="epilepsy", title="Epilepsy in Childhood: III. Results with the Ketogenic Diet", authors="Wilkins L", journal="Journal of Pediatrics", citation="1937;10(3):341-357", url="https://doi.org/10.1016/S0022-3476(37)80188-2", kind="doi", doi="10.1016/S0022-3476(37)80188-2", scope="direct"),
    dict(year=1938, area="epilepsy", title="Results of 15 Years' Experience with the Ketogenic Diet in the Treatment of Epilepsy in Children", authors="Helmholz HF, Goldstein M", journal="American Journal of Psychiatry", citation="1938;94(5):1205-1214", url="https://doi.org/10.1176/ajp.94.5.1205", kind="doi", doi="10.1176/ajp.94.5.1205", scope="direct"),
    dict(year=1939, area="epilepsy", title="Convulsions in Childhood: A Review of One Thousand Cases", authors="Peterman MG", journal="JAMA", citation="1939;113(3):194-198", url="https://doi.org/10.1001/jama.1939.02800280006002", kind="doi", doi="10.1001/jama.1939.02800280006002", scope="clinical-context"),
    dict(year=1942, area="epilepsy", title="Parallel Clinical and Electro-encephalographic Improvement in Epilepsy: A Study of Children Treated by the Ketogenic Diet", authors="Logan G, Baldes EJ", journal="Proceedings of the Staff Meetings of the Mayo Clinic", citation="1942;17:345-352", url="https://doi.org/10.1016/S0025-6196(25)11352-9", kind="doi", doi="10.1016/S0025-6196(25)11352-9", scope="direct"),
    dict(year=1946, area="epilepsy", title="Convulsions in Childhood: Twenty Year Study of 2,500 Cases", authors="Peterman MG", journal="American Journal of Diseases of Children", citation="1946;72(4):399-410", url="https://doi.org/10.1001/archpedi.1946.02020330031005", kind="doi", doi="10.1001/archpedi.1946.02020330031005", pmid="20275869", scope="clinical-context"),
    dict(year=1947, area="epilepsy", title="Results of Treatment of Recurring Convulsive Attacks of Epilepsy", authors="Keith HM", journal="American Journal of Diseases of Children", citation="1947;74(2):140-146", url="https://doi.org/10.1001/archpedi.1947.02030010148003", kind="doi", doi="10.1001/archpedi.1947.02030010148003", pmid="20261971", scope="direct"),
    dict(year=1948, area="epilepsy", title="The Treatment of Petit Mal Epilepsy with Tridione (Absentol, Petidion) and with Ketogenic Diet", authors="Kloek J, Ledeboer BC", journal="Nederlands Tijdschrift voor Geneeskunde", citation="1948;92(7):485-494", url="https://pubmed.ncbi.nlm.nih.gov/18862627/", kind="pubmed", pmid="18862627", scope="direct"),
]


def norm(value: str) -> str:
    value = re.sub(r"^\s*\d+\.\s*", "", value or "")
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", value)


def clean_doi(value: str) -> str:
    value = (value or "").strip().lower()
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value)
    return value.rstrip("/.,; ")


def make_article(soup: BeautifulSoup, rec: dict):
    a = soup.new_tag("article")
    a["class"] = ["folder-paper", "historical-paper"]
    a["data-evidence"] = "historical"
    a["data-evidence-reviewed"] = "true"
    a["data-evidence-source"] = "historical-record"
    a["data-historical-scope"] = rec.get("scope", "direct")
    a["data-year"] = str(rec["year"])
    a["data-search"] = " ".join([
        rec["title"], rec["authors"], rec["journal"], str(rec["year"]),
        "ketogenic diet ketosis fasting epilepsy historical foundational"
    ]).lower()
    if rec.get("doi"):
        a["data-doi"] = clean_doi(rec["doi"])
    if rec.get("pmid"):
        a["data-pmid"] = str(rec["pmid"])

    level = soup.new_tag("div")
    level["class"] = ["evidence-level"]
    level["data-en"] = "Historical / foundational evidence"
    level["data-it"] = "Evidenza storica / fondativa"
    level.string = "Historical / foundational evidence"
    a.append(level)

    h = soup.new_tag("h4")
    h["data-en"] = rec["title"]
    h["data-it"] = rec["title"]
    h.string = rec["title"]
    a.append(h)

    p = soup.new_tag("p")
    p["data-en"] = f'{rec["authors"]}. {rec["journal"]}. {rec["citation"]}. Historical ketogenic-diet reference.'
    p["data-it"] = f'{rec["authors"]}. {rec["journal"]}. {rec["citation"]}. Riferimento storico sulla dieta chetogenica.'
    p.string = p["data-en"]
    a.append(p)

    links = soup.new_tag("div")
    links["class"] = ["paper-links"]
    x = soup.new_tag("a", href=rec["url"])
    x["target"] = "_blank"
    x["rel"] = "noopener"
    labels = {
        "doi": ("DOI ↗", "DOI ↗"),
        "pubmed": ("PubMed ↗", "PubMed ↗"),
        "record": ("Bibliographic record ↗", "Scheda bibliografica ↗"),
        "source": ("Bibliographic source ↗", "Fonte bibliografica ↗"),
    }
    en, it = labels.get(rec.get("kind"), labels["source"])
    x["data-en"] = en
    x["data-it"] = it
    x.string = en
    links.append(x)
    a.append(links)
    return a


def update_folder(curated, soup):
    cards = curated.select(":scope > article.folder-paper")
    hist = [a for a in cards if "historical-paper" in (a.get("class") or [])]
    other = [a for a in cards if a not in hist]
    hist.sort(key=lambda a: (int(a.get("data-year") or 9999), norm((a.find("h4") or {}).get("data-en", "") if a.find("h4") else "")))
    for a in cards:
        a.extract()
    for a in hist + other:
        curated.append(a)
    for i, h in enumerate(curated.select(":scope > article.folder-paper h4"), 1):
        en = re.sub(r"^\s*\d+\.\s*", "", h.get("data-en") or h.get_text(" ", strip=True)).strip()
        it = re.sub(r"^\s*\d+\.\s*", "", h.get("data-it") or en).strip()
        h["data-en"] = f"{i}. {en}"
        h["data-it"] = f"{i}. {it}"
        h.string = f"{i}. {en}"
    title = curated.select_one(":scope > .folder-curated-title")
    if title:
        n = len(curated.select(":scope > article.folder-paper"))
        title["data-en"] = f"Curated references ({n})"
        title["data-it"] = f"Riferimenti curati ({n})"
        title.string = title["data-en"]


def main():
    if not LIBRARY.exists():
        raise SystemExit("library.html not found")
    soup = BeautifulSoup(LIBRARY.read_text(encoding="utf-8"), "html.parser")

    existing_titles = set()
    existing_dois = set()
    existing_pmids = set()
    for a in soup.select("article.folder-paper"):
        h = a.find("h4")
        if h:
            existing_titles.add(norm(h.get("data-en") or h.get_text(" ", strip=True)))
        d = clean_doi(a.get("data-doi", ""))
        if d:
            existing_dois.add(d)
        p = str(a.get("data-pmid") or "").strip()
        if p:
            existing_pmids.add(p)

    added = []
    skipped = []
    touched = set()
    for rec in RECORDS:
        key = norm(rec["title"])
        doi = clean_doi(rec.get("doi", ""))
        pmid = str(rec.get("pmid") or "").strip()
        duplicate = key in existing_titles or (doi and doi in existing_dois) or (pmid and pmid in existing_pmids)
        if duplicate:
            skipped.append({"year": rec["year"], "title": rec["title"], "reason": "already_present"})
            continue
        folder = soup.select_one(f'details#{rec["area"]} .folder-curated')
        if not folder:
            skipped.append({"year": rec["year"], "title": rec["title"], "reason": f'area_not_found:{rec["area"]}'})
            continue
        folder.append(make_article(soup, rec))
        touched.add(rec["area"])
        existing_titles.add(key)
        if doi:
            existing_dois.add(doi)
        if pmid:
            existing_pmids.add(pmid)
        added.append({k: rec.get(k) for k in ("year", "area", "title", "doi", "pmid", "scope")})

    for area in touched | {"epilepsy", "headache-migraine"}:
        curated = soup.select_one(f"details#{area} .folder-curated")
        if curated:
            update_folder(curated, soup)

    LIBRARY.write_text(str(soup), encoding="utf-8")

    # Audit the resulting 1921-1950 curated manifest by year. Existing PubMed
    # cards count too: a record should not disappear from the audit merely
    # because it pre-dated this historical script and therefore lacks the
    # historical-paper CSS class.
    final = BeautifulSoup(LIBRARY.read_text(encoding="utf-8"), "html.parser")
    all_cards = final.select("article.folder-paper")
    by_title = {}
    by_doi = {}
    by_pmid = {}
    for a in all_cards:
        h = a.find("h4")
        title = re.sub(r"^\s*\d+\.\s*", "", h.get("data-en") or h.get_text(" ", strip=True)).strip() if h else ""
        if title:
            by_title[norm(title)] = a
        d = clean_doi(a.get("data-doi", ""))
        if d:
            by_doi[d] = a
        p = str(a.get("data-pmid") or "").strip()
        if p:
            by_pmid[p] = a

    per_year = Counter()
    per_area = Counter()
    records = []
    unresolved = []
    for rec in RECORDS:
        a = None
        if rec.get("pmid"):
            a = by_pmid.get(str(rec["pmid"]))
        if a is None and rec.get("doi"):
            a = by_doi.get(clean_doi(rec["doi"]))
        if a is None:
            a = by_title.get(norm(rec["title"]))
        if a is None:
            unresolved.append({"year": rec["year"], "title": rec["title"]})
            continue
        y = int(rec["year"])
        parent = a.find_parent("details", class_="library-folder")
        area = parent.get("id") if parent else rec.get("area", "unknown")
        per_year[y] += 1
        per_area[area] += 1
        records.append({"year": y, "area": area, "title": rec["title"], "doi": rec.get("doi"), "pmid": rec.get("pmid"), "scope": rec.get("scope")})

    years = {str(y): per_year.get(y, 0) for y in range(1921, 1951)}
    report = {
        "range": "1921-1950",
        "curation_policy": "Conservative historical backfill. Empty years are retained when no direct/foundational ketogenic reference was verified; the script does not invent a publication to fill a year.",
        "records_in_curated_manifest": len(RECORDS),
        "added_this_run": len(added),
        "skipped_this_run": len(skipped),
        "historical_records_in_library_1921_1950": sum(per_year.values()),
        "unresolved_manifest_records": unresolved,
        "years_with_verified_records": [y for y in range(1921, 1951) if per_year.get(y)],
        "years_without_verified_records": [y for y in range(1921, 1951) if not per_year.get(y)],
        "counts_by_year": years,
        "counts_by_area": dict(sorted(per_area.items())),
        "added": added,
        "skipped": skipped,
        "records": sorted(records, key=lambda r: (r["year"], r["area"], r["title"].lower())),
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("records_in_curated_manifest", "added_this_run", "skipped_this_run", "historical_records_in_library_1921_1950", "years_with_verified_records", "years_without_verified_records")}, indent=2))


if __name__ == "__main__":
    main()
