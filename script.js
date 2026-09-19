// Ketogenic Research — V70 recovery script

const KR_LIBRARY_STATS = {
  publications: 4559,
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
    const value = safeLang === 'it'
      ? el.dataset.placeholderIt
      : el.dataset.placeholderEn;
    if (value) el.setAttribute('placeholder', value);
  });

  document.querySelectorAll('.lang button[data-lang]').forEach(button => {
    const active = button.dataset.lang === safeLang;
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', active ? 'true' : 'false');
  });

  const pageTitle = document.querySelector(
    `meta[name="kr-title-${safeLang}"]`
  );
  if (pageTitle) document.title = pageTitle.content;

  try {
    localStorage.setItem('kr-lang', safeLang);
  } catch (error) {}

  applyLibraryFilters();
  updateLibraryCounters();
  renderLatestEvidence();
}

function initHeader() {
  document.querySelectorAll('.lang button[data-lang]').forEach(button => {
    button.addEventListener('click', () => setLang(button.dataset.lang));
  });

  let saved = 'en';
  try {
    const stored = localStorage.getItem('kr-lang');
    if (stored === 'en' || stored === 'it') saved = stored;
  } catch (error) {}

  setLang(saved);

  const menu = document.querySelector('.header .menu');
  const nav = document.querySelector('.header nav');

  if (menu && nav) {
    menu.setAttribute('aria-expanded', 'false');

    menu.addEventListener('click', event => {
      event.preventDefault();
      event.stopPropagation();

      const open = nav.classList.toggle('open');
      menu.setAttribute('aria-expanded', open ? 'true' : 'false');
    });

    nav.querySelectorAll('a').forEach(link => {
      link.addEventListener('click', () => {
        nav.classList.remove('open');
        menu.setAttribute('aria-expanded', 'false');
      });
    });
  }
}


// ------------------------------------------------------------
// Scientific Library
// ------------------------------------------------------------

function normalizeEvidence(value) {
  const map = {
    'systematic-review': 'systematic-review',
    'systematic_review': 'systematic-review',
    'guideline': 'guideline',
    'clinical-trial': 'clinical-trial',
    'clinical_trial': 'clinical-trial',
    'human': 'human',
    'review': 'review',
    'mechanistic': 'mechanistic',
    'other': 'other'
  };
  return map[value || ''] || value || 'other';
}

function applyLibraryFilters() {
  const folders = Array.from(
    document.querySelectorAll('details.library-folder')
  );

  if (!folders.length) return;

  const searchEl = document.getElementById('librarySearch');
  const evidenceEl = document.getElementById('evidenceFilter');
  const yearEl = document.getElementById('yearFilter');

  const q = (searchEl?.value || '').trim().toLowerCase();
  const ev = evidenceEl?.value || 'all';
  const yr = yearEl?.value || 'all';

  let visiblePapers = 0;
  let visibleFolders = 0;

  folders.forEach(folder => {
    const extra = (
      folder.dataset.searchExtra ||
      folder.dataset.search ||
      ''
    ).toLowerCase();

    const folderTitle = (
      folder.querySelector('summary')?.textContent ||
      ''
    ).toLowerCase();

    let folderMatches = 0;

    folder.querySelectorAll('article.folder-paper').forEach(paper => {
      const blob = (
        `${paper.dataset.search || ''} ${extra} ${folderTitle}`
      ).toLowerCase();

      const paperEv = normalizeEvidence(paper.dataset.evidence);
      const paperYear = paper.dataset.year || 'unknown';

      const qOk = !q || blob.includes(q);
      const evOk = ev === 'all' || paperEv === ev;

      let yrOk = true;
      if (yr !== 'all') {
        if (yr === 'older') {
          yrOk = /^\d{4}$/.test(paperYear) &&
            parseInt(paperYear, 10) <= 2022;
        } else if (yr === 'unknown') {
          yrOk = paperYear === 'unknown';
        } else {
          yrOk = paperYear === yr;
        }
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
      if (q || ev !== 'all' || yr !== 'all') {
        folder.open = true;
      }
    }
  });

  document.querySelectorAll('.library-group').forEach(group => {
    const visible = Array.from(
      group.querySelectorAll('details.library-folder')
    ).some(folder => !folder.hidden);

    group.hidden = !visible;
  });

  const count = document.getElementById('libraryResultCount');
  if (count) {
    count.textContent = currentLang() === 'it'
      ? `${visiblePapers} pubblicazioni in ${visibleFolders} aree`
      : `${visiblePapers} publications across ${visibleFolders} areas`;
  }
}

function initLibrary() {
  ['librarySearch', 'evidenceFilter', 'yearFilter'].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;

    el.addEventListener(
      id === 'librarySearch' ? 'input' : 'change',
      applyLibraryFilters
    );
  });

  const clear = document.getElementById('clearLibraryFilters');
  if (clear) {
    clear.addEventListener('click', () => {
      const search = document.getElementById('librarySearch');
      const evidence = document.getElementById('evidenceFilter');
      const year = document.getElementById('yearFilter');

      if (search) search.value = '';
      if (evidence) evidence.value = 'all';
      if (year) year.value = 'all';

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


// ------------------------------------------------------------
// Latest Evidence
// ------------------------------------------------------------

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, ch => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;'
  })[ch]);
}

function latestDateLabel(value, precision = '') {
  if (!value) return '—';

  const locale = currentLang() === 'it' ? 'it-IT' : 'en-GB';

  if (precision === 'year' || /^\d{4}$/.test(value)) {
    return value.slice(0, 4);
  }

  if (precision === 'month' || /^\d{4}-\d{2}$/.test(value)) {
    const [year, month] = value.split('-').map(Number);
    if (!year || !month) return value;

    return new Intl.DateTimeFormat(locale, {
      year: 'numeric',
      month: 'short',
      timeZone: 'UTC'
    }).format(new Date(Date.UTC(year, month - 1, 1)));
  }

  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    const [year, month, day] = value.split('-').map(Number);

    return new Intl.DateTimeFormat(locale, {
      year: 'numeric',
      month: 'short',
      day: '2-digit',
      timeZone: 'UTC'
    }).format(new Date(Date.UTC(year, month - 1, day)));
  }

  return value;
}

function renderLatestEvidence() {
  const host = document.getElementById('latestPublications');
  if (!host || !KR_LATEST_DATA) return;

  const q = (
    document.getElementById('latestSearch')?.value ||
    ''
  ).trim().toLowerCase();

  const selectedArea =
    document.getElementById('latestArea')?.value ||
    'all';

  const lang = currentLang();

  const rows = (KR_LATEST_DATA.publications || []).filter(p => {
    const haystack = [
      p.title,
      ...(p.authors || []),
      p.journal,
      ...(p.areas || []),
      p.doi,
      p.pmid
    ].join(' ').toLowerCase();

    return (
      (!q || haystack.includes(q)) &&
      (
        selectedArea === 'all' ||
        (p.areas || []).includes(selectedArea)
      )
    );
  });

  if (!rows.length) {
    host.innerHTML = `
      <p class="latest-empty">
        ${lang === 'it'
          ? 'Nessuna pubblicazione corrisponde ai filtri selezionati.'
          : 'No publications match the selected filters.'}
      </p>
    `;
    return;
  }

  host.innerHTML = rows.map(p => {
    const authors = (p.authors || []).slice(0, 6);
    const authorText =
      authors.join(', ') +
      ((p.authors || []).length > 6 ? ' et al.' : '');

    const areas = (p.areas || [])
      .map(area => `<span class="latest-area-chip">${escapeHtml(area)}</span>`)
      .join('');

    const evidenceLabel =
      lang === 'it'
        ? (p.evidence_type_it || p.evidence_type || '')
        : (p.evidence_type || '');

    const evidence = evidenceLabel
      ? `<span class="latest-evidence-chip">${escapeHtml(evidenceLabel)}</span>`
      : '';

    const newBadge = p.status === 'new'
      ? `<span class="latest-new-badge">${lang === 'it' ? 'Nuovo' : 'New'}</span>`
      : '';

    const pubmed = p.pubmed_url
      ? `<a href="${escapeHtml(p.pubmed_url)}" target="_blank" rel="noopener">PubMed ↗</a>`
      : '';

    const doi = p.doi_url
      ? `<a href="${escapeHtml(p.doi_url)}" target="_blank" rel="noopener">DOI ↗</a>`
      : '';

    const pmc = p.pmc_url
      ? `<a href="${escapeHtml(p.pmc_url)}" target="_blank" rel="noopener">${lang === 'it' ? 'Testo completo' : 'Full text'} ↗</a>`
      : '';

    return `
      <article class="latest-paper">
        <div class="latest-paper-top">
          <time datetime="${escapeHtml(p.date || '')}">
            ${escapeHtml(latestDateLabel(p.date, p.date_precision))}
          </time>
          ${newBadge}
        </div>

        <h2>${escapeHtml(p.title || '')}</h2>
        <p class="latest-authors">${escapeHtml(authorText)}</p>

        <p class="latest-journal">
          ${escapeHtml(p.journal || '')}
          ${p.year ? ` · ${escapeHtml(p.year)}` : ''}
        </p>

        <div class="latest-area-list">
          ${evidence}
          ${areas}
        </div>

        <div class="paper-links">
          ${pubmed}
          ${doi}
          ${pmc}
        </div>
      </article>
    `;
  }).join('');
}

async function loadLatestEvidence() {
  const host = document.getElementById('latestPublications');
  if (!host) return;

  const message = document.getElementById('latestLoadMessage');

  try {
    const response = await fetch(
      'latest-publications.json?v=70',
      { cache: 'no-store' }
    );

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    KR_LATEST_DATA = await response.json();

    const count = document.getElementById('latestCount');
    if (count) {
      count.textContent = Number(
        KR_LATEST_DATA.count || 0
      ).toLocaleString(
        currentLang() === 'it' ? 'it-IT' : 'en-US'
      );
    }

    const updated = document.getElementById('latestUpdated');
    if (updated) {
      const stamp = KR_LATEST_DATA.generated_at;
      updated.textContent = stamp
        ? latestDateLabel(stamp.slice(0, 10))
        : '—';
    }

    const areaSelect = document.getElementById('latestArea');
    if (areaSelect) {
      const current = areaSelect.value;

      const areas = [
        ...new Set(
          (KR_LATEST_DATA.publications || [])
            .flatMap(p => p.areas || [])
        )
      ].sort((a, b) => a.localeCompare(b));

      areaSelect
        .querySelectorAll('option:not([value="all"])')
        .forEach(option => option.remove());

      areas.forEach(area => {
        const option = document.createElement('option');
        option.value = area;
        option.textContent = area;
        areaSelect.appendChild(option);
      });

      if (
        Array.from(areaSelect.options)
          .some(option => option.value === current)
      ) {
        areaSelect.value = current;
      }
    }

    if (message) {
      message.hidden = Boolean(KR_LATEST_DATA.count);
      message.textContent = KR_LATEST_DATA.count
        ? ''
        : (
          currentLang() === 'it'
            ? 'Nessuna pubblicazione recente disponibile al momento.'
            : 'No recent publications are currently available.'
        );
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

  if (search) {
    search.addEventListener('input', renderLatestEvidence);
  }

  if (area) {
    area.addEventListener('change', renderLatestEvidence);
  }

  loadLatestEvidence();
}


// ------------------------------------------------------------
// Library update date + deep links
// ------------------------------------------------------------

async function syncLiteratureUpdateDate() {
  const targets = document.querySelectorAll(
    '[data-literature-update-date]'
  );
  if (!targets.length) return;

  try {
    const response = await fetch(
      'latest-publications.json?v=70',
      { cache: 'no-store' }
    );

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    if (!data.generated_at) return;

    const date = new Date(data.generated_at);
    if (Number.isNaN(date.getTime())) return;

    const label = new Intl.DateTimeFormat(
      currentLang() === 'it' ? 'it-IT' : 'en-GB',
      {
        month: 'short',
        year: 'numeric'
      }
    ).format(date);

    targets.forEach(el => {
      el.textContent = label;
      el.setAttribute('datetime', data.generated_at);
    });

  } catch (error) {
    console.warn(
      'Literature update date sync unavailable:',
      error
    );
  }
}

function openLibraryAreaFromHash() {
  if (!window.location.hash) return;

  const id = decodeURIComponent(
    window.location.hash.slice(1)
  );

  const target = document.getElementById(id);

  if (
    !target ||
    !target.matches('details.library-folder')
  ) {
    return;
  }

  document
    .querySelectorAll('details.library-folder[open]')
    .forEach(item => {
      if (item !== target) {
        item.removeAttribute('open');
      }
    });

  target.hidden = false;
  target.setAttribute('open', '');
  target.classList.add('deep-link-target');

  window.setTimeout(() => {
    const header = document.querySelector('.header');

    const offset =
      (
        header
          ? header.getBoundingClientRect().height
          : 0
      ) + 18;

    const top =
      target.getBoundingClientRect().top +
      window.scrollY -
      offset;

    window.scrollTo({
      top,
      behavior: 'smooth'
    });
  }, 80);

  window.setTimeout(() => {
    target.classList.remove('deep-link-target');
  }, 2200);
}


// ------------------------------------------------------------
// Startup
// ------------------------------------------------------------

function initSite() {
  initHeader();
  initLibrary();
  updateLibraryCounters();
  initLatestEvidence();
  syncLiteratureUpdateDate();
  openLibraryAreaFromHash();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initSite);
} else {
  initSite();
}

window.addEventListener(
  'hashchange',
  openLibraryAreaFromHash
);

// V65_AREA_FILTER
(function () {
  function applyAreaFilter() {
    const area = document.getElementById('areaFilter');
    if (!area) return;

    const chosen = area.value;

    document.querySelectorAll(
      'details.library-folder'
    ).forEach(folder => {
      const areaMatch =
        chosen === 'all' ||
        folder.id === chosen;

      if (!areaMatch) {
        folder.hidden = true;
      } else {
        folder.hidden = false;

        if (chosen !== 'all') {
          folder.open = true;
        }
      }
    });

    document.querySelectorAll(
      '.library-group'
    ).forEach(group => {
      const visible = [
        ...group.querySelectorAll(
          'details.library-folder'
        )
      ].some(
        folder =>
          !folder.hidden
      );

      group.hidden = !visible;
    });
  }

  document.addEventListener(
    'DOMContentLoaded',
    () => {
      const area =
        document.getElementById(
          'areaFilter'
        );

      if (area) {
        area.addEventListener(
          'change',
          () => {
            if (
              typeof applyLibraryFilters
              === 'function'
            ) {
              applyLibraryFilters();
            }

            applyAreaFilter();
          }
        );
      }

      const clear =
        document.getElementById(
          'clearLibraryFilters'
        );

      if (clear) {
        clear.addEventListener(
          'click',
          () => {
            const area =
              document.getElementById(
                'areaFilter'
              );

            if (area) {
              area.value = 'all';
            }

            window.setTimeout(
              applyAreaFilter,
              0
            );
          }
        );
      }

      applyAreaFilter();
    }
  );
})();
