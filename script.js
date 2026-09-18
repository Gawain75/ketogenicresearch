
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
  publications: 1219,
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

function latestDateLabel(value, precision = '') {
  if (!value) return '—';

  const locale = latestLang() === 'it' ? 'it-IT' : 'en-GB';

  if (!precision && /^\d{4}-01-01$/.test(value)) {
    return value.slice(0, 4);
  }

  if (precision === 'year' || /^\d{4}$/.test(value)) {
    return value.slice(0, 4);
  }

  if (precision === 'month' || /^\d{4}-\d{2}$/.test(value)) {
    const [year, month] = value.split('-').map(Number);
    if (!year || !month) return value;
    const d = new Date(Date.UTC(year, month - 1, 1));
    return new Intl.DateTimeFormat(locale, {
      year: 'numeric',
      month: 'short',
      timeZone: 'UTC'
    }).format(d);
  }

  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    const [year, month, day] = value.split('-').map(Number);
    const d = new Date(Date.UTC(year, month - 1, day));
    return new Intl.DateTimeFormat(locale, {
      year: 'numeric',
      month: 'short',
      day: '2-digit',
      timeZone: 'UTC'
    }).format(d);
  }

  return value;
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
    const evidenceLabel = lang === 'it'
      ? (p.evidence_type_it || p.evidence_type || '')
      : (p.evidence_type || '');
    const evidenceBadge = evidenceLabel
      ? `<span class="latest-evidence-chip">${krEscapeHtml(evidenceLabel)}</span>` : '';
    const newBadge = p.status === 'new'
      ? `<span class="latest-new-badge">${lang === 'it' ? 'Nuovo' : 'New'}</span>` : '';
    const doi = p.doi_url
      ? `<a href="${krEscapeHtml(p.doi_url)}" target="_blank" rel="noopener">DOI ↗</a>` : '';
    const pmid = p.pubmed_url
      ? `<a href="${krEscapeHtml(p.pubmed_url)}" target="_blank" rel="noopener">PubMed ↗</a>` : '';
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
        <div class="paper-links">${pmid}${doi}</div>
      </article>`;
  }).join('');
}

async function loadLatestEvidence() {
  const host = document.getElementById('latestPublications');
  if (!host) return;

  const message = document.getElementById('latestLoadMessage');
  try {
    const response = await fetch('latest-publications.json?v=63', {cache:'no-store'});
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



// V43 — synchronize curated Library "Last literature update" with the latest PubMed feed timestamp
async function syncLiteratureUpdateDate() {
  const targets = document.querySelectorAll('[data-literature-update-date]');
  if (!targets.length) return;

  try {
    const response = await fetch('latest-publications.json', { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    const data = await response.json();
    const stamp = data.generated_at;
    if (!stamp) return;

    const date = new Date(stamp);
    if (Number.isNaN(date.getTime())) return;

    const lang = document.documentElement.lang === 'it' ? 'it-IT' : 'en-GB';
    const label = new Intl.DateTimeFormat(lang, {
      month: 'short',
      year: 'numeric'
    }).format(date);

    targets.forEach(el => {
      el.textContent = label;
      el.setAttribute('datetime', stamp);
    });
  } catch (error) {
    console.warn('Literature update date sync unavailable:', error);
  }
}

document.addEventListener('DOMContentLoaded', syncLiteratureUpdateDate);


// V54 — robust deep links from Research Programs to specific Library areas
function openLibraryAreaFromHash() {
  if (!window.location.hash) return;

  const id = decodeURIComponent(window.location.hash.slice(1));
  if (!id) return;

  const target = document.getElementById(id);
  if (!target || !target.matches('details.library-folder')) return;

  // Close other areas so the destination is visually unambiguous.
  document.querySelectorAll('details.library-folder[open]').forEach((item) => {
    if (item !== target) item.removeAttribute('open');
  });

  target.setAttribute('open', '');

  // Brief visual emphasis after navigation.
  target.classList.add('deep-link-target');

  window.setTimeout(() => {
    const header = document.querySelector('.header');
    const offset = (header ? header.getBoundingClientRect().height : 0) + 18;
    const top = target.getBoundingClientRect().top + window.scrollY - offset;
    window.scrollTo({ top, behavior: 'smooth' });
    // LIBRARY CLINICAL AREA FILTER
(function () {
  function setupClinicalAreaFilter() {
    const filterRow = document.querySelector('.library-filter-row');
    const folders = Array.from(
      document.querySelectorAll('details.library-folder')
    );

    if (!filterRow || !folders.length) return;

    let areaFilter = document.getElementById('areaFilter');

    if (!areaFilter) {
      areaFilter = document.createElement('select');
      areaFilter.id = 'areaFilter';
      areaFilter.setAttribute(
        'aria-label',
        'Filter by clinical area'
      );

      const firstOption = document.createElement('option');
      firstOption.value = 'all';
      firstOption.textContent = 'All clinical areas';
      firstOption.dataset.en = 'All clinical areas';
      firstOption.dataset.it = 'Tutte le aree cliniche';
      areaFilter.appendChild(firstOption);

      folders.forEach(folder => {
        const title = folder.querySelector('summary strong');
        if (!title || !folder.id) return;

        const option = document.createElement('option');
        option.value = folder.id;
        option.textContent =
          title.dataset.en ||
          title.textContent.trim();

        option.dataset.en =
          title.dataset.en ||
          title.textContent.trim();

        option.dataset.it =
          title.dataset.it ||
          title.textContent.trim();

        areaFilter.appendChild(option);
      });

      filterRow.insertBefore(
        areaFilter,
        filterRow.firstChild
      );
    }

    function applyClinicalAreaFilter() {
      const selected = areaFilter.value;

      folders.forEach(folder => {
        const areaMatches =
          selected === 'all' ||
          folder.id === selected;

        if (!areaMatches) {
          folder.hidden = true;
        } else if (selected !== 'all') {
          folder.hidden = false;
          folder.open = true;
        }
      });

      document
        .querySelectorAll('.library-group')
        .forEach(group => {
          const hasVisibleFolder = Array.from(
            group.querySelectorAll(
              'details.library-folder'
            )
          ).some(folder => !folder.hidden);

          group.hidden = !hasVisibleFolder;
        });
    }

    areaFilter.addEventListener(
      'change',
      function () {
        if (
          typeof window.applyLibraryFilters ===
          'function'
        ) {
          window.applyLibraryFilters();
        }

        applyClinicalAreaFilter();
      }
    );

    const controls = [
      document.getElementById('librarySearch'),
      document.getElementById('evidenceFilter'),
      document.getElementById('yearFilter')
    ].filter(Boolean);

    controls.forEach(control => {
      const eventName =
        control.tagName === 'SELECT'
          ? 'change'
          : 'input';

      control.addEventListener(
        eventName,
        function () {
          setTimeout(
            applyClinicalAreaFilter,
            0
          );
        }
      );
    });

    const clearButton =
      document.getElementById(
        'clearLibraryFilters'
      );

    if (clearButton) {
      clearButton.addEventListener(
        'click',
        function () {
          areaFilter.value = 'all';

          setTimeout(
            applyClinicalAreaFilter,
            0
          );
        }
      );
    }

    applyClinicalAreaFilter();
  }

  if (
    document.readyState === 'loading'
  ) {
    document.addEventListener(
      'DOMContentLoaded',
      setupClinicalAreaFilter
    );
  } else {
    setupClinicalAreaFilter();
  }
})();
  }, 80);

  window.setTimeout(() => {
    target.classList.remove('deep-link-target');
  }, 2200);
}

document.addEventListener('DOMContentLoaded', openLibraryAreaFromHash);
window.addEventListener('hashchange', openLibraryAreaFromHash);
// ============================================================
// V66 LIBRARY UX
// ============================================================

(function () {
  function initV66LibraryUX() {
    const filterRow = document.querySelector('.library-filter-row');
    const folders = Array.from(
      document.querySelectorAll('details.library-folder')
    );

    if (!filterRow || !folders.length) return;

    filterRow.classList.add('kr-v66-toolbar');

    // --------------------------------------------------------
    // Clinical area filter
    // --------------------------------------------------------

    let areaFilter = document.getElementById('areaFilter');

    if (!areaFilter) {
      areaFilter = document.createElement('select');
      areaFilter.id = 'areaFilter';
      areaFilter.className = 'kr-v66-select';
      areaFilter.setAttribute(
        'aria-label',
        'Filter by clinical area'
      );

      const allAreas = document.createElement('option');
      allAreas.value = 'all';
      allAreas.textContent = 'All clinical areas';
      allAreas.dataset.en = 'All clinical areas';
      allAreas.dataset.it = 'Tutte le aree cliniche';

      areaFilter.appendChild(allAreas);

      folders.forEach(folder => {
        const heading = folder.querySelector('summary strong');

        if (!heading || !folder.id) return;

        const option = document.createElement('option');
        option.value = folder.id;

        option.dataset.en =
          heading.dataset.en ||
          heading.textContent.trim();

        option.dataset.it =
          heading.dataset.it ||
          heading.textContent.trim();

        option.textContent = option.dataset.en;

        areaFilter.appendChild(option);
      });

      const search =
        document.getElementById('librarySearch') ||
        filterRow.querySelector(
          'input[type="search"], input[type="text"]'
        );

      if (search && search.nextSibling) {
        filterRow.insertBefore(
          areaFilter,
          search.nextSibling
        );
      } else {
        filterRow.prepend(areaFilter);
      }
    }

    // --------------------------------------------------------
    // Sort filter
    // --------------------------------------------------------

    let sortFilter = document.getElementById('librarySort');

    if (!sortFilter) {
      sortFilter = document.createElement('select');
      sortFilter.id = 'librarySort';
      sortFilter.className = 'kr-v66-select';
      sortFilter.setAttribute(
        'aria-label',
        'Sort publications'
      );

      const options = [
        {
          value: 'default',
          en: 'Default order',
          it: 'Ordine predefinito'
        },
        {
          value: 'newest',
          en: 'Newest first',
          it: 'Più recenti'
        },
        {
          value: 'oldest',
          en: 'Oldest first',
          it: 'Meno recenti'
        },
        {
          value: 'evidence',
          en: 'Evidence type',
          it: 'Tipo di evidenza'
        }
      ];

      options.forEach(item => {
        const option = document.createElement('option');

        option.value = item.value;
        option.dataset.en = item.en;
        option.dataset.it = item.it;
        option.textContent = item.en;

        sortFilter.appendChild(option);
      });

      const clearButton =
        document.getElementById('clearLibraryFilters');

      if (clearButton) {
        filterRow.insertBefore(
          sortFilter,
          clearButton
        );
      } else {
        filterRow.appendChild(sortFilter);
      }
    }

    // --------------------------------------------------------
    // Result counter
    // --------------------------------------------------------

    let resultCounter =
      document.getElementById('libraryResultCount');

    if (!resultCounter) {
      resultCounter = document.createElement('div');

      resultCounter.id = 'libraryResultCount';
      resultCounter.className = 'kr-v66-result-count';
      resultCounter.setAttribute(
        'aria-live',
        'polite'
      );

      filterRow.insertAdjacentElement(
        'afterend',
        resultCounter
      );
    }

    // --------------------------------------------------------
    // Filter selected clinical area
    // --------------------------------------------------------

    function applyAreaFilter() {
      const selected = areaFilter.value;

      folders.forEach(folder => {
        const matches =
          selected === 'all' ||
          folder.id === selected;

        if (!matches) {
          folder.dataset.v66AreaHidden = 'true';
          folder.hidden = true;
        } else {
          delete folder.dataset.v66AreaHidden;

          folder.hidden = false;

          if (selected !== 'all') {
            folder.open = true;
          }
        }
      });

      document
        .querySelectorAll('.library-group')
        .forEach(group => {
          const visibleFolder = Array.from(
            group.querySelectorAll(
              'details.library-folder'
            )
          ).some(folder => !folder.hidden);

          group.hidden = !visibleFolder;
        });
    }

    // --------------------------------------------------------
    // Sorting
    // --------------------------------------------------------

    const originalOrder = new WeakMap();

    document
      .querySelectorAll('.folder-curated')
      .forEach(container => {
        Array.from(
          container.querySelectorAll(
            'article.folder-paper'
          )
        ).forEach((paper, index) => {
          originalOrder.set(paper, index);
        });
      });

    function paperYear(paper) {
      const value =
        paper.dataset.year ||
        '';

      const year = parseInt(value, 10);

      return Number.isFinite(year)
        ? year
        : 0;
    }

    function evidenceRank(paper) {
      const order = {
        'systematic-review': 1,
        'guideline': 2,
        'clinical-trial': 3,
        'human': 4,
        'review': 5,
        'mechanistic': 6,
        'other': 7
      };

      return (
        order[paper.dataset.evidence] ||
        99
      );
    }

    function sortPapers() {
      const mode = sortFilter.value;

      document
        .querySelectorAll('.folder-curated')
        .forEach(container => {
          const papers = Array.from(
            container.querySelectorAll(
              'article.folder-paper'
            )
          );

          papers.sort((a, b) => {
            if (mode === 'newest') {
              return paperYear(b) - paperYear(a);
            }

            if (mode === 'oldest') {
              return paperYear(a) - paperYear(b);
            }

            if (mode === 'evidence') {
              const diff =
                evidenceRank(a) -
                evidenceRank(b);

              if (diff !== 0) return diff;

              return paperYear(b) -
                paperYear(a);
            }

            return (
              (originalOrder.get(a) || 0) -
              (originalOrder.get(b) || 0)
            );
          });

          papers.forEach(paper => {
            container.appendChild(paper);
          });
        });
    }

    // --------------------------------------------------------
    // Result count
    // --------------------------------------------------------

    function updateResultCount() {
      const papers = Array.from(
        document.querySelectorAll(
          'article.folder-paper'
        )
      );

      const visible = papers.filter(paper => {
        const folder =
          paper.closest(
            'details.library-folder'
          );

        if (!folder || folder.hidden) {
          return false;
        }

        const style =
          window.getComputedStyle(paper);

        return (
          !paper.hidden &&
          style.display !== 'none'
        );
      });

      const language =
        document.documentElement.lang ||
        'en';

      if (
        language.toLowerCase().startsWith('it')
      ) {
        resultCounter.textContent =
          `${visible.length} pubblicazioni visualizzate`;
      } else {
        resultCounter.textContent =
          `${visible.length} publications shown`;
      }
    }

    // --------------------------------------------------------
    // Refresh
    // --------------------------------------------------------

    function refreshV66() {
      window.setTimeout(() => {
        applyAreaFilter();
        sortPapers();
        updateResultCount();
      }, 0);
    }

    areaFilter.addEventListener(
      'change',
      refreshV66
    );

    sortFilter.addEventListener(
      'change',
      refreshV66
    );

    const search =
      document.getElementById('librarySearch') ||
      filterRow.querySelector(
        'input[type="search"], input[type="text"]'
      );

    if (search) {
      search.addEventListener(
        'input',
        refreshV66
      );
    }

    [
      document.getElementById('evidenceFilter'),
      document.getElementById('yearFilter')
    ]
      .filter(Boolean)
      .forEach(control => {
        control.addEventListener(
          'change',
          refreshV66
        );
      });

    const clear =
      document.getElementById(
        'clearLibraryFilters'
      );

    if (clear) {
      clear.addEventListener(
        'click',
        () => {
          areaFilter.value = 'all';
          sortFilter.value = 'default';

          window.setTimeout(
            refreshV66,
            20
          );
        }
      );
    }

    // Update count when existing filters modify the DOM.
    const observer = new MutationObserver(() => {
      window.clearTimeout(
        window.krV66CounterTimer
      );

      window.krV66CounterTimer =
        window.setTimeout(
          updateResultCount,
          40
        );
    });

    folders.forEach(folder => {
      observer.observe(folder, {
        attributes: true,
        subtree: true,
        attributeFilter: [
          'hidden',
          'style',
          'class'
        ]
      });
    });

    refreshV66();
  }

  if (
    document.readyState === 'loading'
  ) {
    document.addEventListener(
      'DOMContentLoaded',
      initV66LibraryUX
    );
  } else {
    initV66LibraryUX();
  }
})();
