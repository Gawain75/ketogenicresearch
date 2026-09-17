
const setLang = (lang) => {
  document.documentElement.lang = lang;
  document.querySelectorAll('[data-en]').forEach(el => {
    const value = el.dataset[lang];
    if (typeof value !== 'undefined') el.innerHTML = value;
  });
  document.querySelectorAll('[data-placeholder-en]').forEach(el => {
    const value = lang === 'it' ? el.dataset.placeholderIt : el.dataset.placeholderEn;
    if (value) el.setAttribute('placeholder', value);
  });
  document.querySelectorAll('.lang button').forEach(b => {
    const active = b.dataset.lang === lang;
    b.classList.toggle('active', active);
    b.setAttribute('aria-pressed', active ? 'true' : 'false');
  });
  const pageTitle = document.querySelector('meta[name="kr-title-' + lang + '"]');
  if (pageTitle) document.title = pageTitle.content;
  localStorage.setItem('kr-lang', lang);
  if (typeof applyLibraryFilters === 'function') applyLibraryFilters();
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

// V32 Scientific Library: full-text search + evidence/year filters.
function applyLibraryFilters() {
  const searchEl = document.getElementById('librarySearch');
  const evidenceEl = document.getElementById('evidenceFilter');
  const yearEl = document.getElementById('yearFilter');
  if (!searchEl || !evidenceEl || !yearEl) return;

  const q = searchEl.value.trim().toLowerCase();
  const ev = evidenceEl.value;
  const yr = yearEl.value;
  let visiblePapers = 0;
  let visibleFolders = 0;

  document.querySelectorAll('details.library-folder').forEach(folder => {
    const extra = (folder.dataset.searchExtra || '').toLowerCase();
    const folderTitle = (folder.querySelector('summary')?.textContent || '').toLowerCase();
    let folderMatches = 0;

    folder.querySelectorAll('article.folder-paper').forEach(paper => {
      const blob = ((paper.dataset.search || '') + ' ' + extra + ' ' + folderTitle).toLowerCase();
      const paperEv = paper.dataset.evidence || 'other';
      const paperYear = paper.dataset.year || 'unknown';

      const qOk = !q || blob.includes(q);
      const evOk = ev === 'all' || paperEv === ev;
      let yrOk = true;
      if (yr !== 'all') {
        if (yr === 'older') yrOk = /^\d{4}$/.test(paperYear) && parseInt(paperYear, 10) <= 2022;
        else if (yr === 'unknown') yrOk = paperYear === 'unknown';
        else yrOk = paperYear === yr;
      }

      const show = qOk && evOk && yrOk;
      paper.hidden = !show;
      if (show) {
        folderMatches++;
        visiblePapers++;
      }
    });

    const showFolder = folderMatches > 0;
    folder.hidden = !showFolder;
    if (showFolder) {
      visibleFolders++;
      if (q || ev !== 'all' || yr !== 'all') folder.open = true;
    }
  });

  const count = document.getElementById('libraryResultCount');
  if (count) {
    const lang = document.documentElement.lang === 'it' ? 'it' : 'en';
    count.textContent = lang === 'it'
      ? `${visiblePapers} pubblicazioni in ${visibleFolders} aree`
      : `${visiblePapers} publications across ${visibleFolders} areas`;
  }
}

document.addEventListener('DOMContentLoaded', () => {
  ['librarySearch','evidenceFilter','yearFilter'].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener(id === 'librarySearch' ? 'input' : 'change', applyLibraryFilters);
  });
  const clear = document.getElementById('clearLibraryFilters');
  if (clear) {
    clear.addEventListener('click', () => {
      const s = document.getElementById('librarySearch');
      const e = document.getElementById('evidenceFilter');
      const y = document.getElementById('yearFilter');
      if (s) s.value = '';
      if (e) e.value = 'all';
      if (y) y.value = 'all';
      applyLibraryFilters();
    });
  }
  applyLibraryFilters();
});


// V37 — centralized scientific-library counters
const KR_LIBRARY_STATS = {
  publications: 570,
  clinicalAreas: 53
};

function updateLibraryCounters() {
  let publications = KR_LIBRARY_STATS.publications;
  let clinicalAreas = KR_LIBRARY_STATS.clinicalAreas;

  const paperNodes = document.querySelectorAll('article.folder-paper');
  const folderNodes = document.querySelectorAll('details.library-folder');

  if (paperNodes.length) publications = paperNodes.length;
  if (folderNodes.length) clinicalAreas = folderNodes.length;

  document.querySelectorAll('[data-publication-count]').forEach(el => {
    el.textContent = publications.toLocaleString(document.documentElement.lang === 'it' ? 'it-IT' : 'en-US');
  });

  document.querySelectorAll('[data-clinical-area-count]').forEach(el => {
    el.textContent = clinicalAreas.toLocaleString(document.documentElement.lang === 'it' ? 'it-IT' : 'en-US');
  });
}

document.addEventListener('DOMContentLoaded', updateLibraryCounters);


// V40 — automated Latest Evidence feed
let KR_LATEST_DATA = null;

function krEscapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, ch => ({
    '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#039;'
  })[ch]);
}

function latestLang() {
  return document.documentElement.lang === 'it' ? 'it' : 'en';
}

function latestDateLabel(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(`${iso}T00:00:00Z`);
    return new Intl.DateTimeFormat(latestLang() === 'it' ? 'it-IT' : 'en-GB', {
      year:'numeric', month:'short', day:'2-digit', timeZone:'UTC'
    }).format(d);
  } catch (_) {
    return iso;
  }
}

function renderLatestEvidence() {
  const host = document.getElementById('latestPublications');
  if (!host || !KR_LATEST_DATA) return;

  const q = (document.getElementById('latestSearch')?.value || '').trim().toLowerCase();
  const area = document.getElementById('latestArea')?.value || 'all';
  const lang = latestLang();

  const rows = (KR_LATEST_DATA.publications || []).filter(p => {
    const hay = [
      p.title,
      ...(p.authors || []),
      p.journal,
      ...(p.areas || []),
      p.doi,
      p.pmid
    ].join(' ').toLowerCase();
    const qOk = !q || hay.includes(q);
    const areaOk = area === 'all' || (p.areas || []).includes(area);
    return qOk && areaOk;
  });

  if (!rows.length) {
    host.innerHTML = `<p class="latest-empty">${lang === 'it'
      ? 'Nessuna pubblicazione corrisponde ai filtri selezionati.'
      : 'No publications match the selected filters.'}</p>`;
    return;
  }

  host.innerHTML = rows.map(p => {
    const authors = (p.authors || []).slice(0, 6);
    const authorText = authors.join(', ') + ((p.authors || []).length > 6 ? ' et al.' : '');
    const areas = (p.areas || []).map(a => `<span class="latest-area-chip">${krEscapeHtml(a)}</span>`).join('');
    const newBadge = p.status === 'new'
      ? `<span class="latest-new-badge">${lang === 'it' ? 'Nuovo' : 'New'}</span>` : '';
    const doi = p.doi_url
      ? `<a href="${krEscapeHtml(p.doi_url)}" target="_blank" rel="noopener">DOI ↗</a>` : '';
    const pmid = p.pubmed_url
      ? `<a href="${krEscapeHtml(p.pubmed_url)}" target="_blank" rel="noopener">PubMed ↗</a>` : '';
    return `
      <article class="latest-paper">
        <div class="latest-paper-top">
          <time datetime="${krEscapeHtml(p.date || '')}">${krEscapeHtml(latestDateLabel(p.date))}</time>
          ${newBadge}
        </div>
        <h2>${krEscapeHtml(p.title || '')}</h2>
        <p class="latest-authors">${krEscapeHtml(authorText)}</p>
        <p class="latest-journal">${krEscapeHtml(p.journal || '')}${p.year ? ` · ${krEscapeHtml(p.year)}` : ''}</p>
        <div class="latest-area-list">${areas}</div>
        <div class="paper-links">${pmid}${doi}</div>
      </article>`;
  }).join('');
}

async function loadLatestEvidence() {
  const host = document.getElementById('latestPublications');
  if (!host) return;

  const message = document.getElementById('latestLoadMessage');
  try {
    const response = await fetch('latest-publications.json?v=41', {cache:'no-store'});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    KR_LATEST_DATA = await response.json();

    const count = document.getElementById('latestCount');
    if (count) count.textContent = Number(KR_LATEST_DATA.count || 0).toLocaleString(
      latestLang() === 'it' ? 'it-IT' : 'en-US'
    );

    const updated = document.getElementById('latestUpdated');
    if (updated) {
      const stamp = KR_LATEST_DATA.generated_at;
      updated.textContent = stamp ? latestDateLabel(stamp.slice(0,10)) : '—';
    }

    const areaSelect = document.getElementById('latestArea');
    if (areaSelect) {
      const current = areaSelect.value;
      const areas = [...new Set(
        (KR_LATEST_DATA.publications || []).flatMap(p => p.areas || [])
      )].sort((a,b) => a.localeCompare(b));
      areaSelect.querySelectorAll('option:not([value="all"])').forEach(o => o.remove());
      areas.forEach(area => {
        const opt = document.createElement('option');
        opt.value = area;
        opt.textContent = area;
        areaSelect.appendChild(opt);
      });
      if ([...areaSelect.options].some(o => o.value === current)) areaSelect.value = current;
    }

    if (message) {
      message.textContent = (KR_LATEST_DATA.count || 0)
        ? ''
        : (latestLang() === 'it'
            ? 'Nessuna pubblicazione recente disponibile al momento.'
            : 'No recent publications are currently available.');
      message.hidden = Boolean(KR_LATEST_DATA.count);
    }

    renderLatestEvidence();
  } catch (err) {
    if (message) {
      message.hidden = false;
      message.textContent = latestLang() === 'it'
        ? 'Il feed automatico non è al momento disponibile.'
        : 'The automated literature feed is currently unavailable.';
    }
    console.error('Latest Evidence load error:', err);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const search = document.getElementById('latestSearch');
  const area = document.getElementById('latestArea');
  if (search) search.addEventListener('input', renderLatestEvidence);
  if (area) area.addEventListener('change', renderLatestEvidence);
  loadLatestEvidence();
});

