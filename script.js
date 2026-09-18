// Ketogenic Research — consolidated site script

const KR_LIBRARY_STATS = {
  publications: 1219,
  clinicalAreas: 53
};

let KR_LATEST_DATA = null;

function currentLang() {
  return document.documentElement.lang === 'it' ? 'it' : 'en';
}

function setLang(lang) {
  const safeLang = lang === 'it' ? 'it' : 'en';
  document.documentElement.lang = safeLang;

  document.querySelectorAll('[data-en]').forEach(el => {
    const value = el.dataset[safeLang];
    if (typeof value !== 'undefined') el.innerHTML = value;
  });

  document.querySelectorAll('[data-placeholder-en]').forEach(el => {
    const value = safeLang === 'it' ? el.dataset.placeholderIt : el.dataset.placeholderEn;
    if (value) el.setAttribute('placeholder', value);
  });

  document.querySelectorAll('.lang button[data-lang]').forEach(button => {
    const active = button.dataset.lang === safeLang;
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', active ? 'true' : 'false');
  });

  const pageTitle = document.querySelector(`meta[name="kr-title-${safeLang}"]`);
  if (pageTitle) document.title = pageTitle.content;

  try {
    localStorage.setItem('kr-lang', safeLang);
  } catch (error) {}

  applyLibraryFilters();
  updateLibraryCounters();
  renderLatestEvidence();
  syncLiteratureUpdateDate();
}

function initLanguage() {
  document.querySelectorAll('.lang button[data-lang]').forEach(button => {
    button.addEventListener('click', () => setLang(button.dataset.lang));
  });

  let saved = 'en';
  try {
    const stored = localStorage.getItem('kr-lang');
    if (stored === 'it' || stored === 'en') saved = stored;
  } catch (error) {}

  setLang(saved);
}

function initMobileMenu() {
  const menu = document.querySelector('.header .menu');
  const nav = document.querySelector('.header nav');
  if (!menu || !nav) return;

  menu.setAttribute('aria-expanded', 'false');

  menu.addEventListener('click', event => {
    event.preventDefault();
    const isOpen = nav.classList.toggle('open');
    menu.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
  });

  nav.querySelectorAll('a').forEach(link => {
    link.addEventListener('click', () => {
      nav.classList.remove('open');
      menu.setAttribute('aria-expanded', 'false');
    });
  });
}

function libraryFolders() {
  return Array.from(document.querySelectorAll('details.library-folder'));
}

function ensureLibraryAreaFilter() {
  const folders = libraryFolders();
  const row = document.querySelector('.library-filter-row');
  if (!folders.length || !row) return null;

  let select = document.getElementById('areaFilter');
  if (select) return select;

  select = document.createElement('select');
  select.id = 'areaFilter';
  select.setAttribute('aria-label', 'Filter by clinical area');

  const all = document.createElement('option');
  all.value = 'all';
  all.dataset.en = 'All clinical areas';
  all.dataset.it = 'Tutte le aree cliniche';
  all.textContent = currentLang() === 'it' ? all.dataset.it : all.dataset.en;
  select.appendChild(all);

  folders.forEach((folder, index) => {
    if (!folder.id) folder.id = `clinical-area-${index + 1}`;
    const heading = folder.querySelector('summary strong') || folder.querySelector('summary');
    if (!heading) return;

    const option = document.createElement('option');
    option.value = folder.id;
    option.dataset.en = heading.dataset.en || heading.textContent.trim();
    option.dataset.it = heading.dataset.it || option.dataset.en;
    option.textContent = currentLang() === 'it' ? option.dataset.it : option.dataset.en;
    select.appendChild(option);
  });

  const evidence = document.getElementById('evidenceFilter');
  row.insertBefore(select, evidence || row.firstChild);
  return select;
}

function ensureLibrarySortFilter() {
  const row = document.querySelector('.library-filter-row');
  if (!row || !libraryFolders().length) return null;

  let select = document.getElementById('librarySort');
  if (select) return select;

  select = document.createElement('select');
  select.id = 'librarySort';
  select.setAttribute('aria-label', 'Sort publications');

  [
    ['default', 'Default order', 'Ordine predefinito'],
    ['newest', 'Newest first', 'Più recenti'],
    ['oldest', 'Oldest first', 'Meno recenti'],
    ['evidence', 'Evidence type', 'Tipo di evidenza']
  ].forEach(([value, en, it]) => {
    const option = document.createElement('option');
    option.value = value;
    option.dataset.en = en;
    option.dataset.it = it;
    option.textContent = currentLang() === 'it' ? it : en;
    select.appendChild(option);
  });

  const clear = document.getElementById('clearLibraryFilters');
  row.insertBefore(select, clear || null);
  return select;
}

function normalizeEvidence(value) {
  const map = {
    'randomized-clinical-trial': 'clinical-trial',
    'clinical-trial-/-intervention': 'clinical-trial',
    'observational-human-study': 'human',
    'case-report-/-case-series': 'human',
    'preclinical-/-mechanistic': 'mechanistic'
  };
  return map[value] || value || 'other';
}

function evidenceRank(paper) {
  const ranks = {
    'meta-analysis': 1,
    'systematic-review': 2,
    'guideline': 3,
    'clinical-trial': 4,
    'human': 5,
    'review': 6,
    'mechanistic': 7,
    'other': 8
  };
  return ranks[normalizeEvidence(paper.dataset.evidence)] || 99;
}

function paperYear(paper) {
  const year = parseInt(paper.dataset.year || '0', 10);
  return Number.isFinite(year) ? year : 0;
}

function sortLibraryPapers() {
  const sort = document.getElementById('librarySort');
  if (!sort) return;

  document.querySelectorAll('.folder-curated').forEach(container => {
    const papers = Array.from(container.querySelectorAll('article.folder-paper'));
    papers.forEach((paper, index) => {
      if (typeof paper.dataset.originalOrder === 'undefined') {
        paper.dataset.originalOrder = String(index);
      }
    });

    papers.sort((a, b) => {
      if (sort.value === 'newest') return paperYear(b) - paperYear(a);
      if (sort.value === 'oldest') return paperYear(a) - paperYear(b);
      if (sort.value === 'evidence') {
        const diff = evidenceRank(a) - evidenceRank(b);
        return diff || (paperYear(b) - paperYear(a));
      }
      return parseInt(a.dataset.originalOrder || '0', 10) - parseInt(b.dataset.originalOrder || '0', 10);
    });

    papers.forEach(paper => container.appendChild(paper));
  });
}

function applyLibraryFilters() {
  const folders = libraryFolders();
  if (!folders.length) return;

  const searchEl = document.getElementById('librarySearch');
  const evidenceEl = document.getElementById('evidenceFilter');
  const yearEl = document.getElementById('yearFilter');
  const areaEl = document.getElementById('areaFilter');

  const q = (searchEl?.value || '').trim().toLowerCase();
  const ev = evidenceEl?.value || 'all';
  const yr = yearEl?.value || 'all';
  const area = areaEl?.value || 'all';

  let visiblePapers = 0;
  let visibleFolders = 0;

  folders.forEach(folder => {
    const areaOk = area === 'all' || folder.id === area;
    const extra = (folder.dataset.searchExtra || folder.dataset.search || '').toLowerCase();
    const folderTitle = (folder.querySelector('summary')?.textContent || '').toLowerCase();
    let folderMatches = 0;

    folder.querySelectorAll('article.folder-paper').forEach(paper => {
      const blob = `${paper.dataset.search || ''} ${extra} ${folderTitle}`.toLowerCase();
      const paperEv = normalizeEvidence(paper.dataset.evidence);
      const paperYearValue = paper.dataset.year || 'unknown';

      const qOk = !q || blob.includes(q);
      const evOk = ev === 'all' || paperEv === ev;

      let yrOk = true;
      if (yr !== 'all') {
        if (yr === 'older') {
          yrOk = /^\d{4}$/.test(paperYearValue) && parseInt(paperYearValue, 10) <= 2022;
        } else if (yr === 'unknown') {
          yrOk = paperYearValue === 'unknown';
        } else {
          yrOk = paperYearValue === yr;
        }
      }

      const show = areaOk && qOk && evOk && yrOk;
      paper.hidden = !show;
      if (show) {
        folderMatches++;
        visiblePapers++;
      }
    });

    const showFolder = areaOk && folderMatches > 0;
    folder.hidden = !showFolder;
    if (showFolder) {
      visibleFolders++;
      if (q || ev !== 'all' || yr !== 'all' || area !== 'all') folder.open = true;
    }
  });

  document.querySelectorAll('.library-group').forEach(group => {
    const anyVisible = Array.from(group.querySelectorAll('details.library-folder')).some(folder => !folder.hidden);
    group.hidden = !anyVisible;
  });

  sortLibraryPapers();

  const count = document.getElementById('libraryResultCount');
  if (count) {
    count.textContent = currentLang() === 'it'
      ? `${visiblePapers} pubblicazioni in ${visibleFolders} aree`
      : `${visiblePapers} publications across ${visibleFolders} areas`;
  }
}

function initLibraryControls() {
  if (!libraryFolders().length) return;

  ensureLibraryAreaFilter();
  ensureLibrarySortFilter();

  [
    ['librarySearch', 'input'],
    ['areaFilter', 'change'],
    ['evidenceFilter', 'change'],
    ['yearFilter', 'change'],
    ['librarySort', 'change']
  ].forEach(([id, eventName]) => {
    const element = document.getElementById(id);
    if (element) element.addEventListener(eventName, applyLibraryFilters);
  });

  const clear = document.getElementById('clearLibraryFilters');
  if (clear) {
    clear.addEventListener('click', () => {
      const defaults = {
        librarySearch: '',
        areaFilter: 'all',
        evidenceFilter: 'all',
        yearFilter: 'all',
        librarySort: 'default'
      };
      Object.entries(defaults).forEach(([id, value]) => {
        const element = document.getElementById(id);
        if (element) element.value = value;
      });
      applyLibraryFilters();
    });
  }

  applyLibraryFilters();
}

function updateLibraryCounters() {
  let publications = KR_LIBRARY_STATS.publications;
  let clinicalAreas = KR_LIBRARY_STATS.clinicalAreas;

  const papers = document.querySelectorAll('article.folder-paper');
  const folders = document.querySelectorAll('details.library-folder');
  if (papers.length) publications = papers.length;
  if (folders.length) clinicalAreas = folders.length;

  const locale = currentLang() === 'it' ? 'it-IT' : 'en-US';
  document.querySelectorAll('[data-publication-count]').forEach(el => {
    el.textContent = publications.toLocaleString(locale);
  });
  document.querySelectorAll('[data-clinical-area-count]').forEach(el => {
    el.textContent = clinicalAreas.toLocaleString(locale);
  });
}

function krEscapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, ch => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'
  })[ch]);
}

function latestDateLabel(value, precision = '') {
  if (!value) return '—';
  const locale = currentLang() === 'it' ? 'it-IT' : 'en-GB';

  if (precision === 'year' || /^\d{4}$/.test(value)) return value.slice(0, 4);

  if (precision === 'month' || /^\d{4}-\d{2}$/.test(value)) {
    const [year, month] = value.split('-').map(Number);
    if (!year || !month) return value;
    return new Intl.DateTimeFormat(locale, {
      year: 'numeric', month: 'short', timeZone: 'UTC'
    }).format(new Date(Date.UTC(year, month - 1, 1)));
  }

  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    const [year, month, day] = value.split('-').map(Number);
    return new Intl.DateTimeFormat(locale, {
      year: 'numeric', month: 'short', day: '2-digit', timeZone: 'UTC'
    }).format(new Date(Date.UTC(year, month - 1, day)));
  }

  return value;
}

function renderLatestEvidence() {
  const host = document.getElementById('latestPublications');
  if (!host || !KR_LATEST_DATA) return;

  const q = (document.getElementById('latestSearch')?.value || '').trim().toLowerCase();
  const area = document.getElementById('latestArea')?.value || 'all';
  const lang = currentLang();

  const rows = (KR_LATEST_DATA.publications || []).filter(p => {
    const hay = [p.title, ...(p.authors || []), p.journal, ...(p.areas || []), p.doi, p.pmid]
      .join(' ').toLowerCase();
    return (!q || hay.includes(q)) && (area === 'all' || (p.areas || []).includes(area));
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
    const evidenceLabel = lang === 'it' ? (p.evidence_type_it || p.evidence_type || '') : (p.evidence_type || '');
    const evidenceBadge = evidenceLabel ? `<span class="latest-evidence-chip">${krEscapeHtml(evidenceLabel)}</span>` : '';
    const newBadge = p.status === 'new' ? `<span class="latest-new-badge">${lang === 'it' ? 'Nuovo' : 'New'}</span>` : '';
    const pmid = p.pubmed_url ? `<a href="${krEscapeHtml(p.pubmed_url)}" target="_blank" rel="noopener">PubMed ↗</a>` : '';
    const doi = p.doi_url ? `<a href="${krEscapeHtml(p.doi_url)}" target="_blank" rel="noopener">DOI ↗</a>` : '';
    const pmc = p.pmc_url ? `<a href="${krEscapeHtml(p.pmc_url)}" target="_blank" rel="noopener">${lang === 'it' ? 'Testo completo' : 'Full text'} ↗</a>` : '';

    return `
      <article class="latest-paper">
        <div class="latest-paper-top">
          <time datetime="${krEscapeHtml(p.date || '')}">${krEscapeHtml(latestDateLabel(p.date, p.date_precision))}</time>
          ${newBadge}
        </div>
        <h2>${krEscapeHtml(p.title || '')}</h2>
        <p class="latest-authors">${krEscapeHtml(authorText)}</p>
        <p class="latest-journal">${krEscapeHtml(p.journal || '')}${p.year ? ` · ${krEscapeHtml(p.year)}` : ''}</p>
        <div class="latest-area-list">${evidenceBadge}${areas}</div>
        <div class="paper-links">${pmid}${doi}${pmc}</div>
      </article>`;
  }).join('');
}

async function loadLatestEvidence() {
  const host = document.getElementById('latestPublications');
  if (!host) return;

  const message = document.getElementById('latestLoadMessage');

  try {
    const response = await fetch('latest-publications.json?v=68', { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    KR_LATEST_DATA = await response.json();

    const count = document.getElementById('latestCount');
    if (count) count.textContent = Number(KR_LATEST_DATA.count || 0).toLocaleString(currentLang() === 'it' ? 'it-IT' : 'en-US');

    const updated = document.getElementById('latestUpdated');
    if (updated) {
      const stamp = KR_LATEST_DATA.generated_at;
      updated.textContent = stamp ? latestDateLabel(stamp.slice(0, 10)) : '—';
    }

    const areaSelect = document.getElementById('latestArea');
    if (areaSelect) {
      const current = areaSelect.value;
      const areas = [...new Set((KR_LATEST_DATA.publications || []).flatMap(p => p.areas || []))]
        .sort((a, b) => a.localeCompare(b));
      areaSelect.querySelectorAll('option:not([value="all"])').forEach(option => option.remove());
      areas.forEach(areaName => {
        const option = document.createElement('option');
        option.value = areaName;
        option.textContent = areaName;
        areaSelect.appendChild(option);
      });
      if ([...areaSelect.options].some(option => option.value === current)) areaSelect.value = current;
    }

    if (message) {
      message.textContent = KR_LATEST_DATA.count ? '' : (currentLang() === 'it'
        ? 'Nessuna pubblicazione recente disponibile al momento.'
        : 'No recent publications are currently available.');
      message.hidden = Boolean(KR_LATEST_DATA.count);
    }

    renderLatestEvidence();
  } catch (error) {
    if (message) {
      message.hidden = false;
      message.textContent = currentLang() === 'it'
        ? 'Il feed automatico non è al momento disponibile.'
        : 'The automated literature feed is currently unavailable.';
    }
    console.error('Latest Evidence load error:', error);
  }
}

function initLatestEvidence() {
  const search = document.getElementById('latestSearch');
  const area = document.getElementById('latestArea');
  if (search) search.addEventListener('input', renderLatestEvidence);
  if (area) area.addEventListener('change', renderLatestEvidence);
  loadLatestEvidence();
}

async function syncLiteratureUpdateDate() {
  const targets = document.querySelectorAll('[data-literature-update-date]');
  if (!targets.length) return;

  try {
    const response = await fetch('latest-publications.json?v=68', { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    if (!data.generated_at) return;

    const date = new Date(data.generated_at);
    if (Number.isNaN(date.getTime())) return;

    const label = new Intl.DateTimeFormat(currentLang() === 'it' ? 'it-IT' : 'en-GB', {
      month: 'short', year: 'numeric'
    }).format(date);

    targets.forEach(el => {
      el.textContent = label;
      el.setAttribute('datetime', data.generated_at);
    });
  } catch (error) {
    console.warn('Literature update date sync unavailable:', error);
  }
}

function openLibraryAreaFromHash() {
  if (!window.location.hash) return;
  const id = decodeURIComponent(window.location.hash.slice(1));
  const target = document.getElementById(id);
  if (!target || !target.matches('details.library-folder')) return;

  const areaFilter = document.getElementById('areaFilter');
  if (areaFilter && [...areaFilter.options].some(option => option.value === id)) {
    areaFilter.value = id;
    applyLibraryFilters();
  }

  document.querySelectorAll('details.library-folder[open]').forEach(item => {
    if (item !== target) item.removeAttribute('open');
  });

  target.hidden = false;
  target.setAttribute('open', '');
  target.classList.add('deep-link-target');

  window.setTimeout(() => {
    const header = document.querySelector('.header');
    const offset = (header ? header.getBoundingClientRect().height : 0) + 18;
    const top = target.getBoundingClientRect().top + window.scrollY - offset;
    window.scrollTo({ top, behavior: 'smooth' });
  }, 80);

  window.setTimeout(() => target.classList.remove('deep-link-target'), 2200);
}

function initSite() {
  initMobileMenu();
  initLibraryControls();
  updateLibraryCounters();
  initLatestEvidence();
  initLanguage();
  syncLiteratureUpdateDate();
  openLibraryAreaFromHash();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initSite);
} else {
  initSite();
}

window.addEventListener('hashchange', openLibraryAreaFromHash);
