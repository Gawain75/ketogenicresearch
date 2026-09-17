
const setLang = (lang) => {
  document.documentElement.lang = lang;
  document.querySelectorAll('[data-en]').forEach(el => el.innerHTML = el.dataset[lang]);
  document.querySelectorAll('.lang button').forEach(b => b.classList.toggle('active', b.dataset.lang === lang));
  localStorage.setItem('kr-lang', lang);
};
document.querySelectorAll('.lang button').forEach(b => b.addEventListener('click', () => setLang(b.dataset.lang)));
setLang(localStorage.getItem('kr-lang') || 'en');
const menu=document.querySelector('.menu'), nav=document.querySelector('nav');
if(menu&&nav){menu.addEventListener('click',()=>nav.classList.toggle('open'));document.querySelectorAll('nav a').forEach(a=>a.addEventListener('click',()=>nav.classList.remove('open')));}

const librarySearch = document.querySelector('#librarySearch');
if (librarySearch) {
  librarySearch.addEventListener('input', () => {
    const q = librarySearch.value.trim().toLowerCase();
    document.querySelectorAll('.library-folder').forEach(folder => {
      const hit = !q || (folder.dataset.search || '').includes(q);
      folder.style.display = hit ? '' : 'none';
    });
    document.querySelectorAll('.library-group').forEach(group => {
      const visible = [...group.querySelectorAll('.library-folder')].some(x => x.style.display !== 'none');
      group.style.display = visible ? '' : 'none';
    });
  });
}


// V10 — Live scientific bibliography via Europe PMC.
// Publications are loaded only when a folder is opened, reducing page weight.
// Europe PMC provides publication metadata, DOI/PMID/PMCID and full-text links.
(function () {
  const API = 'https://www.ebi.ac.uk/europepmc/webservices/rest/search';

  function esc(s='') {
    return String(s).replace(/[&<>"']/g, c => ({
      '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
    }[c]));
  }

  function currentLang() {
    const active = document.querySelector('.lang button.active');
    return active?.dataset.lang || localStorage.getItem('lang') || 'en';
  }

  function pubTypeLabel(p) {
    const t = p.pubTypeList?.pubType || [];
    if (!t.length) return '';
    return t.slice(0, 2).join(' · ');
  }

  function findBestFullText(p) {
    const items = p.fullTextUrlList?.fullTextUrl || [];
    if (!items.length) return null;

    // Prefer an explicitly free/open PDF
    let best = items.find(x =>
      String(x.documentStyle || '').toLowerCase() === 'pdf' &&
      /free|open/i.test(String(x.availability || '') + ' ' + String(x.availabilityCode || ''))
    );
    if (best) return {url: best.url, label: 'PDF'};

    // Then any PDF
    best = items.find(x => String(x.documentStyle || '').toLowerCase() === 'pdf');
    if (best) return {url: best.url, label: 'PDF'};

    // Then any free/open full text
    best = items.find(x => /free|open/i.test(String(x.availability || '') + ' ' + String(x.availabilityCode || '')));
    if (best) return {url: best.url, label: 'Full text'};

    return null;
  }

  function paperHtml(p) {
    const title = p.title || 'Untitled publication';
    const authors = p.authorString || '';
    const journal = p.journalTitle || '';
    const year = p.pubYear || '';
    const meta = [authors, journal, year].filter(Boolean).join(' · ');
    const type = pubTypeLabel(p);

    const links = [];
    const full = findBestFullText(p);
    if (full?.url) {
      links.push(`<a class="pdf-link" href="${esc(full.url)}" target="_blank" rel="noopener">${esc(full.label)} ↗</a>`);
    }
    if (p.doi) {
      links.push(`<a href="https://doi.org/${esc(p.doi)}" target="_blank" rel="noopener">DOI ↗</a>`);
    }
    if (p.pmid) {
      links.push(`<a href="https://pubmed.ncbi.nlm.nih.gov/${esc(p.pmid)}/" target="_blank" rel="noopener">PubMed ↗</a>`);
    }
    const epmcId = p.pmcid || p.pmid || p.id;
    if (epmcId) {
      links.push(`<a href="https://europepmc.org/article/${esc(p.source || 'MED')}/${esc(epmcId)}" target="_blank" rel="noopener">Europe PMC ↗</a>`);
    }

    return `
      <article class="live-paper">
        ${type ? `<div class="paper-badge">${esc(type)}</div>` : ''}
        <h4>${esc(title)}</h4>
        ${meta ? `<p>${esc(meta)}</p>` : ''}
        <div class="paper-links">${links.join('')}</div>
      </article>`;
  }

  async function loadFolder(folder) {
    if (folder.dataset.loaded === '1' || folder.dataset.loading === '1') return;
    const query = folder.dataset.query;
    if (!query) return;

    folder.dataset.loading = '1';
    const status = folder.querySelector('.live-status');
    const results = folder.querySelector('.live-results');
    const lang = currentLang();

    status.textContent = lang === 'it'
      ? 'Caricamento delle pubblicazioni recenti…'
      : 'Loading recent publications…';

    // 2020–2026, newest first, synonyms enabled. Request 30 records with core metadata.
    const fullQuery = `(${query}) AND FIRST_PDATE:[2020-01-01 TO 2026-12-31] sort_date:y`;
    const url = `${API}?query=${encodeURIComponent(fullQuery)}&format=json&pageSize=30&resultType=core&synonym=true`;

    try {
      const res = await fetch(url, {headers: {'Accept':'application/json'}});
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const papers = data?.resultList?.result || [];
      const hitCount = Number(data?.hitCount || papers.length);

      if (!papers.length) {
        status.textContent = lang === 'it'
          ? 'Nessuna pubblicazione trovata con questa query automatica. Usa i link di ricerca bibliografica qui sopra: la letteratura può esistere con terminologia diversa.'
          : 'No publications were returned by this automated query. Use the literature-search links above; relevant evidence may use different terminology.';
        folder.dataset.loaded = '1';
        return;
      }

      const shown = Math.min(papers.length, 30);
      status.textContent = lang === 'it'
        ? `${shown} pubblicazioni visualizzate${hitCount > shown ? ` · ${hitCount} risultati complessivi` : ''}.`
        : `${shown} publications displayed${hitCount > shown ? ` · ${hitCount} total results` : ''}.`;

      results.innerHTML = papers.slice(0, 30).map(paperHtml).join('');
      folder.dataset.loaded = '1';
    } catch (err) {
      console.error('Europe PMC load error:', err);
      status.textContent = lang === 'it'
        ? 'Impossibile caricare ora i risultati live. I link DOI, Europe PMC, PubMed e ricerca bibliografica restano disponibili.'
        : 'Live results could not be loaded right now. DOI, Europe PMC, PubMed and literature-search links remain available.';
    } finally {
      folder.dataset.loading = '0';
    }
  }

  document.querySelectorAll('.library-folder[data-query]').forEach(folder => {
    folder.addEventListener('toggle', () => {
      if (folder.open) loadFolder(folder);
    });
    if (folder.open) loadFolder(folder);
  });

  // Language changes should also update status text on folders that are not loaded yet.
  document.querySelectorAll('.lang button').forEach(btn => {
    btn.addEventListener('click', () => {
      setTimeout(() => {
        const lang = currentLang();
        document.querySelectorAll('.library-folder[data-loaded!="1"] .live-status').forEach(s => {
          s.textContent = lang === 'it'
            ? 'Apri questa cartella per caricare fino a 30 pubblicazioni recenti.'
            : 'Open this folder to load up to 30 recent publications.';
        });
      }, 0);
    });
  });
})();
