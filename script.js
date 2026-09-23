// Ketogenic Research — V70 recovery script

const KR_LIBRARY_STATS = {
  publications: 4102,
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

  populateObesityGlp1Keto();
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
  const v = (value || '').toLowerCase();
  if (!v) return 'other';
  if (v.includes('systematic-review') && v.includes('meta-analysis')) return 'systematic-review-meta-analysis';
  if (v.includes('meta-analysis')) return 'meta-analysis';
  if (v.includes('systematic-review') || v.includes('systematic_review')) return 'systematic-review';
  if (v.includes('guideline') || v.includes('consensus') || v.includes('position-statement')) return 'guideline';
  if (v.includes('randomized-clinical-trial') || v.includes('clinical-trial') || v.includes('clinical_trial')) return 'clinical-trial';
  if (v.includes('observational-human-study') || v.includes('case-report') || v === 'human') return 'human';
  if (v.includes('preclinical') || v.includes('mechanistic')) return 'mechanistic';
  if (v.includes('review')) return 'review';
  return 'other';
}

function evidenceMatches(rawValue, selected) {
  if (selected === 'all') return true;
  const raw = (rawValue || '').toLowerCase();
  const norm = normalizeEvidence(raw);
  if (selected === 'meta-analysis') return raw.includes('meta-analysis');
  if (selected === 'systematic-review') return raw.includes('systematic-review') || norm === 'systematic-review-meta-analysis';
  if (selected === 'clinical-trial') return norm === 'clinical-trial';
  if (selected === 'human') return norm === 'human' || norm === 'clinical-trial';
  return norm === selected;
}

function topicMatches(rawText, selected) {
  if (selected === 'all') return true;
  const text = (rawText || '').toLowerCase();

  if (selected === 'glp1-keto') {
    const glpTerms = [
      'glp-1',
      'glp1',
      'glucagon-like peptide-1',
      'semaglutide',
      'liraglutide',
      'dulaglutide',
      'exenatide',
      'lixisenatide',
      'tirzepatide',
      'retatrutide',
      'survodutide',
      'orforglipron',
      'cagrisema'
    ];

    const ketoTerms = [
      'ketogenic',
      'ketosis',
      'ketone',
      'ketones',
      'ketonemia',
      'ketonaemia',
      'beta-hydroxybutyrate',
      'β-hydroxybutyrate',
      'b-hydroxybutyrate',
      'bhb',
      'vlckd',
      'vlekt',
      'low-energy ketogenic',
      'very low-calorie ketogenic',
      'very-low-calorie ketogenic',
      'keto diet'
    ];

    return (
      glpTerms.some(term => text.includes(term)) &&
      ketoTerms.some(term => text.includes(term))
    );
  }

  return true;
}

function isGlp1KetoIntersection(paper) {
  const titleEl = paper.querySelector('h4');
  const text = [
    paper.dataset.search || '',
    titleEl?.dataset?.en || '',
    titleEl?.dataset?.it || '',
    titleEl?.textContent || ''
  ].join(' ').toLowerCase();

  const glpTerms = [
    'glp-1', 'glp1', 'glp-1ra', 'glp1ra', 'glp-1 receptor agonist',
    'glucagon-like peptide-1', 'incretin',
    'semaglutide', 'liraglutide', 'dulaglutide', 'exenatide',
    'lixisenatide', 'tirzepatide', 'retatrutide', 'survodutide',
    'orforglipron', 'cagrisema'
  ];

  const ketoTerms = [
    'ketogenic', 'ketosis', 'ketone', 'ketones',
    'ketonemia', 'ketonaemia', 'beta-hydroxybutyrate',
    'β-hydroxybutyrate', 'b-hydroxybutyrate', 'bhb',
    'ketone ester', 'exogenous ketone',
    'vlckd', 'vlekt', 'low-energy ketogenic',
    'very low-calorie ketogenic', 'very-low-calorie ketogenic',
    'keto diet'
  ];

  return (
    glpTerms.some(term => text.includes(term)) &&
    ketoTerms.some(term => text.includes(term))
  );
}

function populateObesityGlp1Keto() {
  const obesity = document.getElementById('obesity');
  const host = document.getElementById('obesityGlp1KetoList');
  const count = document.getElementById('obesityGlp1KetoCount');
  const empty = document.getElementById('obesityGlp1KetoEmpty');
  if (!obesity || !host) return;

  const papers = Array.from(
    obesity.querySelectorAll('.folder-curated > article.folder-paper')
  );

  const matches = papers.filter(isGlp1KetoIntersection);
  host.innerHTML = '';

  const lang = currentLang();

  matches.forEach(paper => {
    const card = document.createElement('article');
    card.className = 'topic-subfolder-paper';

    const sourceTitle = paper.querySelector('h4');
    if (sourceTitle) {
      const h4 = document.createElement('h4');
      const en = sourceTitle.dataset.en || sourceTitle.textContent || '';
      const it = sourceTitle.dataset.it || en;
      h4.dataset.en = en;
      h4.dataset.it = it;
      h4.innerHTML = lang === 'it' ? it : en;
      card.appendChild(h4);
    }

    const meta = paper.querySelector('p');
    if (meta) {
      const p = meta.cloneNode(true);
      if (p.dataset.en || p.dataset.it) {
        p.innerHTML = lang === 'it'
          ? (p.dataset.it || p.dataset.en || p.textContent)
          : (p.dataset.en || p.textContent);
      }
      card.appendChild(p);
    }

    const links = paper.querySelector('.paper-links');
    if (links) card.appendChild(links.cloneNode(true));

    host.appendChild(card);
  });

  if (count) count.textContent = String(matches.length);
  if (empty) empty.hidden = matches.length > 0;
}

function publicationIdentity(paper) {
  // Prefer bibliographic identifiers. Title is only a fallback.
  if (paper.dataset.pmid) return `pmid:${paper.dataset.pmid}`;
  if (paper.dataset.doi) return `doi:${paper.dataset.doi.toLowerCase()}`;

  const h4 = paper.querySelector('h4');
  const rawTitle = h4?.dataset?.en || h4?.textContent || '';
  const title = rawTitle
    .replace(/^\s*\d+\.\s*/, '')
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '');

  if (title) return `title:${title}`;
  return `card:${paper.dataset.search || ''}`;
}

function applyLibraryFilters() {
  const folders = Array.from(
    document.querySelectorAll('details.library-folder')
  );

  if (!folders.length) return;

  const searchEl = document.getElementById('librarySearch');
  const evidenceEl = document.getElementById('evidenceFilter');
  const topicEl = document.getElementById('topicFilter');
  const yearEl = document.getElementById('yearFilter');
  const areaEl = document.getElementById('areaFilter');

  const q = (searchEl?.value || '').trim().toLowerCase();
  const ev = evidenceEl?.value || 'all';
  const topic = topicEl?.value || 'all';
  const yr = yearEl?.value || 'all';
  const area = areaEl?.value || 'all';

  const visiblePublicationKeys = new Set();
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
      const evOk = evidenceMatches(paper.dataset.evidence, ev);
      const topicOk = topicMatches(blob, topic);

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

      const show = qOk && evOk && topicOk && yrOk;
      paper.hidden = !show;

      if (show) {
        folderMatches++;
        visiblePapers++;
        visiblePublicationKeys.add(publicationIdentity(paper));
      }
    });

    const areaOk = area === 'all' || folder.id === area;
    const showFolder = folderMatches > 0 && areaOk;
    folder.hidden = !showFolder;

    if (showFolder) {
      visibleFolders++;
      if (q || ev !== 'all' || topic !== 'all' || yr !== 'all' || area !== 'all') {
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
      ? `${visiblePublicationKeys.size} pubblicazioni uniche in ${visibleFolders} aree`
      : `${visiblePublicationKeys.size} unique publications across ${visibleFolders} areas`;
  }
}

function initLibrary() {
  populateObesityGlp1Keto();
  ['librarySearch', 'evidenceFilter', 'topicFilter', 'yearFilter', 'areaFilter'].forEach(id => {
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
      const topic = document.getElementById('topicFilter');
      const year = document.getElementById('yearFilter');
      const area = document.getElementById('areaFilter');

      if (search) search.value = '';
      if (evidence) evidence.value = 'all';
      if (topic) topic.value = 'all';
      if (year) year.value = 'all';
      if (area) area.value = 'all';

      applyLibraryFilters();
    });
  }

  applyLibraryFilters();
}

function updateLibraryCounters() {
  // These values are generated by the bibliographic workflow and are the
  // canonical source of truth. Do not recompute them from DOM cards, because
  // the same publication can appear in multiple areas with title variants.
  const publications = KR_LIBRARY_STATS.publications;
  const clinicalAreas = KR_LIBRARY_STATS.clinicalAreas;

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
      'latest-publications.json?v=72',
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

    const verified = document.getElementById('latestVerified');
    if (verified) {
      const stamp =
        KR_LATEST_DATA.verified_at ||
        KR_LATEST_DATA.generated_at;
      verified.textContent = stamp
        ? latestDateLabel(stamp.slice(0, 10))
        : '—';
    }

    const contentUpdated = document.getElementById('latestContentUpdated');
    if (contentUpdated) {
      const stamp =
        KR_LATEST_DATA.content_updated_at ||
        KR_LATEST_DATA.generated_at;
      contentUpdated.textContent = stamp
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
      'latest-publications.json?v=72',
      { cache: 'no-store' }
    );

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    const literatureUpdatedAt =
      data.content_updated_at ||
      data.generated_at;
    if (!literatureUpdatedAt) return;

    const date = new Date(literatureUpdatedAt);
    if (Number.isNaN(date.getTime())) return;

    const label = new Intl.DateTimeFormat(
      currentLang() === 'it' ? 'it-IT' : 'en-GB',
      {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
        timeZone: 'UTC'
      }
    ).format(date);

    targets.forEach(el => {
      el.textContent = label;
      el.setAttribute('datetime', literatureUpdatedAt);
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
  
/* V97 — Library chronology and year labels */
function normalizeLibraryChronology() {
  document.querySelectorAll('details.library-folder .folder-curated').forEach(container => {
    const cards = Array.from(container.querySelectorAll(':scope > article.folder-paper'));
    if (!cards.length) return;

    cards.sort((a, b) => {
      const ya = /^\d{4}$/.test(a.dataset.year || '') ? Number(a.dataset.year) : null;
      const yb = /^\d{4}$/.test(b.dataset.year || '') ? Number(b.dataset.year) : null;

      if (ya == null && yb == null) return 0;
      if (ya == null) return 1;
      if (yb == null) return -1;
      return yb - ya;
    });

    cards.forEach((card, index) => {
      const year = /^\d{4}$/.test(card.dataset.year || '') ? card.dataset.year : '';

      if (year) {
        let badge = card.querySelector(':scope > .evidence-level');
        if (!badge) {
          badge = document.createElement('div');
          badge.className = 'evidence-level';
          card.insertBefore(badge, card.firstChild);
        }

        const appendYear = value => {
          value = String(value || '')
            .replace(/\s*[·•|–—-]\s*(18|19|20)\d{2}\s*$/, '')
            .trim();

          if (/^(18|19|20)\d{2}$/.test(value)) return year;
          return value ? `${value} · ${year}` : year;
        };

        const baseVisible = badge.textContent.trim();
        const en = appendYear(badge.dataset.en || baseVisible);
        const it = appendYear(badge.dataset.it || badge.dataset.en || baseVisible);

        badge.dataset.en = en;
        badge.dataset.it = it;
        badge.textContent = currentLang() === 'it' ? it : en;
      }

      const h4 = card.querySelector(':scope > h4');
      if (h4) {
        const stripNumber = value => String(value || '').replace(/^\s*\d+\.\s*/, '').trim();
        const visible = stripNumber(h4.textContent);
        const enTitle = stripNumber(h4.dataset.en || visible);
        const itTitle = stripNumber(h4.dataset.it || h4.dataset.en || visible);

        h4.dataset.en = `${index + 1}. ${enTitle}`;
        h4.dataset.it = `${index + 1}. ${itTitle}`;
        h4.textContent = currentLang() === 'it' ? h4.dataset.it : h4.dataset.en;
      }

      container.appendChild(card);
    });
  });
}

document.addEventListener('DOMContentLoaded', initSite);
} else {
  initSite();
}

window.addEventListener(
  'hashchange',
  openLibraryAreaFromHash
);

// Test reversibile: razionale meccanicistico Alzheimer
if (document.getElementById('alzheimers-disease')) {
  const krAlzheimerMechanisms = document.createElement('script');
  krAlzheimerMechanisms.src = 'alzheimer-mechanisms.js?v=1';
  krAlzheimerMechanisms.defer = true;
  document.head.appendChild(krAlzheimerMechanisms);
}


if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', normalizeLibraryChronology);
} else {
  normalizeLibraryChronology();
}


document.querySelectorAll("[data-lang]").forEach(btn => {
  btn.addEventListener("click", () => setTimeout(normalizeLibraryChronology, 60));
});
