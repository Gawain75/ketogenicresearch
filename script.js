// ============================================================
// KETOGENIC RESEARCH — MAIN SCRIPT
// Clean consolidated version
// ============================================================

const KR_LIBRARY_STATS = {
  publications: 1219,
  clinicalAreas: 53
};

let KR_LATEST_DATA = null;


// ------------------------------------------------------------
// LANGUAGE
// ------------------------------------------------------------

function getCurrentLang() {
  return document.documentElement.lang === 'it' ? 'it' : 'en';
}

function setLang(lang) {
  const safeLang = lang === 'it' ? 'it' : 'en';

  document.documentElement.lang = safeLang;

  document.querySelectorAll('[data-en]').forEach(el => {
    const value = el.dataset[safeLang];

    if (typeof value !== 'undefined') {
      el.innerHTML = value;
    }
  });

  document.querySelectorAll('[data-placeholder-en]').forEach(el => {
    const value =
      safeLang === 'it'
        ? el.dataset.placeholderIt
        : el.dataset.placeholderEn;

    if (value) {
      el.setAttribute('placeholder', value);
    }
  });

  document
    .querySelectorAll('.lang button[data-lang]')
    .forEach(button => {
      const active =
        button.dataset.lang === safeLang;

      button.classList.toggle(
        'active',
        active
      );

      button.setAttribute(
        'aria-pressed',
        active ? 'true' : 'false'
      );
    });

  const pageTitle =
    document.querySelector(
      `meta[name="kr-title-${safeLang}"]`
    );

  if (pageTitle) {
    document.title =
      pageTitle.content;
  }

  try {
    localStorage.setItem(
      'kr-lang',
      safeLang
    );
  } catch (error) {}

  translateDynamicLibraryControls();
  updateLibraryCounters();
  applyLibraryFilters();
  renderLatestEvidence();
  syncLiteratureUpdateDate();
}

function initLanguage() {
  document
    .querySelectorAll(
      '.lang button[data-lang]'
    )
    .forEach(button => {
      button.addEventListener(
        'click',
        () => {
          setLang(
            button.dataset.lang
          );
        }
      );
    });

  let saved = 'en';

  try {
    saved =
      localStorage.getItem(
        'kr-lang'
      ) || 'en';
  } catch (error) {
    saved = 'en';
  }

  setLang(saved);
}


// ------------------------------------------------------------
// MOBILE MENU
// ------------------------------------------------------------

function initMobileMenu() {
  const menu =
    document.querySelector(
      '.header .menu, .menu'
    );

  const nav =
    document.querySelector(
      '.header nav, nav'
    );

  if (!menu || !nav) {
    return;
  }

  menu.setAttribute(
    'aria-expanded',
    nav.classList.contains('open')
      ? 'true'
      : 'false'
  );

  menu.addEventListener(
    'click',
    event => {
      event.preventDefault();

      const open =
        nav.classList.toggle(
          'open'
        );

      menu.setAttribute(
        'aria-expanded',
        open ? 'true' : 'false'
      );
    }
  );

  nav.querySelectorAll('a')
    .forEach(link => {
      link.addEventListener(
        'click',
        () => {
          nav.classList.remove(
            'open'
          );

          menu.setAttribute(
            'aria-expanded',
            'false'
          );
        }
      );
    });
}


// ------------------------------------------------------------
// LIBRARY — HELPERS
// ------------------------------------------------------------

function getLibraryFolders() {
  return Array.from(
    document.querySelectorAll(
      'details.library-folder'
    )
  );
}

function findLibraryControlContainer() {
  const clear =
    document.getElementById(
      'clearLibraryFilters'
    );

  if (
    clear &&
    clear.parentElement
  ) {
    return clear.parentElement;
  }

  const evidence =
    document.getElementById(
      'evidenceFilter'
    );

  if (
    evidence &&
    evidence.parentElement
  ) {
    return evidence.parentElement;
  }

  const year =
    document.getElementById(
      'yearFilter'
    );

  if (
    year &&
    year.parentElement
  ) {
    return year.parentElement;
  }

  const search =
    document.getElementById(
      'librarySearch'
    );

  if (
    search &&
    search.parentElement
  ) {
    return search.parentElement;
  }

  return null;
}


// ------------------------------------------------------------
// LIBRARY — CLINICAL AREA FILTER
// ------------------------------------------------------------

function ensureLibraryAreaFilter() {
  const folders =
    getLibraryFolders();

  if (!folders.length) {
    return null;
  }

  let areaFilter =
    document.getElementById(
      'libraryAreaFilter'
    );

  if (areaFilter) {
    return areaFilter;
  }

  const container =
    findLibraryControlContainer();

  if (!container) {
    return null;
  }

  areaFilter =
    document.createElement(
      'select'
    );

  areaFilter.id =
    'libraryAreaFilter';

  areaFilter.className =
    'kr-v66-select';

  areaFilter.setAttribute(
    'aria-label',
    'Clinical area'
  );

  const allOption =
    document.createElement(
      'option'
    );

  allOption.value = 'all';

  allOption.dataset.en =
    'All clinical areas';

  allOption.dataset.it =
    'Tutte le aree cliniche';

  allOption.textContent =
    'All clinical areas';

  areaFilter.appendChild(
    allOption
  );

  folders.forEach(
    (folder, index) => {
      if (!folder.id) {
        folder.id =
          `clinical-area-${index + 1}`;
      }

      const heading =
        folder.querySelector(
          'summary strong'
        ) ||
        folder.querySelector(
          'summary'
        );

      if (!heading) {
        return;
      }

      const option =
        document.createElement(
          'option'
        );

      option.value =
        folder.id;

      option.dataset.en =
        heading.dataset.en ||
        heading.textContent.trim();

      option.dataset.it =
        heading.dataset.it ||
        heading.dataset.en ||
        heading.textContent.trim();

      option.textContent =
        option.dataset.en;

      areaFilter.appendChild(
        option
      );
    }
  );

  const evidence =
    document.getElementById(
      'evidenceFilter'
    );

  if (
    evidence &&
    evidence.parentElement ===
      container
  ) {
    container.insertBefore(
      areaFilter,
      evidence
    );
  } else {
    const clear =
      document.getElementById(
        'clearLibraryFilters'
      );

    if (
      clear &&
      clear.parentElement ===
        container
    ) {
      container.insertBefore(
        areaFilter,
        clear
      );
    } else {
      container.appendChild(
        areaFilter
      );
    }
  }

  return areaFilter;
}


// ------------------------------------------------------------
// LIBRARY — SORT FILTER
// ------------------------------------------------------------

function ensureLibrarySortFilter() {
  const folders =
    getLibraryFolders();

  if (!folders.length) {
    return null;
  }

  let sortFilter =
    document.getElementById(
      'librarySort'
    );

  if (sortFilter) {
    return sortFilter;
  }

  const container =
    findLibraryControlContainer();

  if (!container) {
    return null;
  }

  sortFilter =
    document.createElement(
      'select'
    );

  sortFilter.id =
    'librarySort';

  sortFilter.className =
    'kr-v66-select';

  sortFilter.setAttribute(
    'aria-label',
    'Sort publications'
  );

  const options = [
    [
      'default',
      'Default order',
      'Ordine predefinito'
    ],
    [
      'newest',
      'Newest first',
      'Più recenti'
    ],
    [
      'oldest',
      'Oldest first',
      'Meno recenti'
    ],
    [
      'evidence',
      'Evidence type',
      'Tipo di evidenza'
    ]
  ];

  options.forEach(
    ([value, en, it]) => {
      const option =
        document.createElement(
          'option'
        );

      option.value =
        value;

      option.dataset.en =
        en;

      option.dataset.it =
        it;

      option.textContent =
        en;

      sortFilter.appendChild(
        option
      );
    }
  );

  const clear =
    document.getElementById(
      'clearLibraryFilters'
    );

  if (
    clear &&
    clear.parentElement ===
      container
  ) {
    container.insertBefore(
      sortFilter,
      clear
    );
  } else {
    container.appendChild(
      sortFilter
    );
  }

  return sortFilter;
}


// ------------------------------------------------------------
// LIBRARY — TRANSLATE DYNAMIC CONTROLS
// ------------------------------------------------------------

function translateDynamicLibraryControls() {
  const lang =
    getCurrentLang();

  [
    'libraryAreaFilter',
    'librarySort'
  ].forEach(id => {
    const select =
      document.getElementById(
        id
      );

    if (!select) {
      return;
    }

    Array.from(
      select.options
    ).forEach(option => {
      const value =
        option.dataset[lang];

      if (value) {
        option.textContent =
          value;
      }
    });
  });
}


// ------------------------------------------------------------
// LIBRARY — RESULT COUNT
// ------------------------------------------------------------

function ensureLibraryResultCount() {
  if (
    !getLibraryFolders().length
  ) {
    return null;
  }

  let count =
    document.getElementById(
      'libraryResultCount'
    );

  if (count) {
    return count;
  }

  count =
    document.createElement(
      'div'
    );

  count.id =
    'libraryResultCount';

  count.className =
    'kr-v66-result-count';

  count.setAttribute(
    'aria-live',
    'polite'
  );

  const container =
    findLibraryControlContainer();

  if (container) {
    container.insertAdjacentElement(
      'afterend',
      count
    );
  }

  return count;
}


// ------------------------------------------------------------
// LIBRARY — SORT HELPERS
// ------------------------------------------------------------

function libraryEvidenceRank(
  paper
) {
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
    order[
      paper.dataset.evidence
    ] || 99
  );
}

function libraryPaperYear(
  paper
) {
  const year =
    parseInt(
      paper.dataset.year ||
      '0',
      10
    );

  return Number.isFinite(
    year
  )
    ? year
    : 0;
}

function sortLibraryPapers() {
  const sort =
    document.getElementById(
      'librarySort'
    );

  if (!sort) {
    return;
  }

  const mode =
    sort.value;

  document
    .querySelectorAll(
      '.folder-curated'
    )
    .forEach(container => {
      const papers =
        Array.from(
          container.querySelectorAll(
            'article.folder-paper'
          )
        );

      papers.forEach(
        (paper, index) => {
          if (
            !paper.dataset
              .krOriginalOrder
          ) {
            paper.dataset
              .krOriginalOrder =
              String(index);
          }
        }
      );

      papers.sort(
        (a, b) => {
          if (
            mode === 'newest'
          ) {
            return (
              libraryPaperYear(b) -
              libraryPaperYear(a)
            );
          }

          if (
            mode === 'oldest'
          ) {
            return (
              libraryPaperYear(a) -
              libraryPaperYear(b)
            );
          }

          if (
            mode === 'evidence'
          ) {
            const diff =
              libraryEvidenceRank(a) -
              libraryEvidenceRank(b);

            if (diff !== 0) {
              return diff;
            }

            return (
              libraryPaperYear(b) -
              libraryPaperYear(a)
            );
          }

          return (
            parseInt(
              a.dataset
                .krOriginalOrder ||
              '0',
              10
            ) -
            parseInt(
              b.dataset
                .krOriginalOrder ||
              '0',
              10
            )
          );
        }
      );

      papers.forEach(
        paper => {
          container.appendChild(
            paper
          );
        }
      );
    });
}


// ------------------------------------------------------------
// LIBRARY — FILTERS
// ------------------------------------------------------------

function applyLibraryFilters() {
  const folders =
    getLibraryFolders();

  if (!folders.length) {
    return;
  }

  const searchEl =
    document.getElementById(
      'librarySearch'
    );

  const evidenceEl =
    document.getElementById(
      'evidenceFilter'
    );

  const yearEl =
    document.getElementById(
      'yearFilter'
    );

  const areaEl =
    document.getElementById(
      'libraryAreaFilter'
    );

  const q =
    (
      searchEl?.value ||
      ''
    )
      .trim()
      .toLowerCase();

  const ev =
    evidenceEl?.value ||
    'all';

  const yr =
    yearEl?.value ||
    'all';

  const area =
    areaEl?.value ||
    'all';

  let visiblePapers = 0;
  let visibleFolders = 0;

  folders.forEach(folder => {
    const areaOk =
      area === 'all' ||
      folder.id === area;

    const extra =
      (
        folder.dataset
          .searchExtra ||
        ''
      ).toLowerCase();

    const folderTitle =
      (
        folder.querySelector(
          'summary'
        )?.textContent ||
        ''
      ).toLowerCase();

    let folderMatches = 0;

    folder
      .querySelectorAll(
        'article.folder-paper'
      )
      .forEach(paper => {
        const blob =
          (
            (
              paper.dataset.search ||
              ''
            ) +
            ' ' +
            extra +
            ' ' +
            folderTitle
          ).toLowerCase();

        const paperEv =
          paper.dataset.evidence ||
          'other';

        const paperYear =
          paper.dataset.year ||
          'unknown';

        const qOk =
          !q ||
          blob.includes(q);

        const evOk =
          ev === 'all' ||
          paperEv === ev;

        let yrOk = true;

        if (yr !== 'all') {
          if (
            yr === 'older'
          ) {
            yrOk =
              /^\d{4}$/.test(
                paperYear
              ) &&
              parseInt(
                paperYear,
                10
              ) <= 2022;
          } else if (
            yr === 'unknown'
          ) {
            yrOk =
              paperYear ===
              'unknown';
          } else {
            yrOk =
              paperYear === yr;
          }
        }

        const show =
          areaOk &&
          qOk &&
          evOk &&
          yrOk;

        paper.hidden =
          !show;

        if (show) {
          folderMatches++;
          visiblePapers++;
        }
      });

    const showFolder =
      areaOk &&
      folderMatches > 0;

    folder.hidden =
      !showFolder;

    if (showFolder) {
      visibleFolders++;

      if (
        q ||
        ev !== 'all' ||
        yr !== 'all' ||
        area !== 'all'
      ) {
        folder.open = true;
      }
    }
  });

  document
    .querySelectorAll(
      '.library-group'
    )
    .forEach(group => {
      const visible =
        Array.from(
          group.querySelectorAll(
            'details.library-folder'
          )
        ).some(
          folder =>
            !folder.hidden
        );

      group.hidden =
        !visible;
    });

  sortLibraryPapers();

  const count =
    document.getElementById(
      'libraryResultCount'
    );

  if (count) {
    count.textContent =
      getCurrentLang() === 'it'
        ? `${visiblePapers} pubblicazioni in ${visibleFolders} aree`
        : `${visiblePapers} publications across ${visibleFolders} areas`;
  }
}

function initLibraryControls() {
  if (
    !getLibraryFolders().length
  ) {
    return;
  }

  ensureLibraryAreaFilter();
  ensureLibrarySortFilter();
  ensureLibraryResultCount();
  translateDynamicLibraryControls();

  const listeners = [
    [
      'librarySearch',
      'input'
    ],
    [
      'evidenceFilter',
      'change'
    ],
    [
      'yearFilter',
      'change'
    ],
    [
      'libraryAreaFilter',
      'change'
    ],
    [
      'librarySort',
      'change'
    ]
  ];

  listeners.forEach(
    ([id, eventName]) => {
      const element =
        document.getElementById(
          id
        );

      if (element) {
        element.addEventListener(
          eventName,
          applyLibraryFilters
        );
      }
    }
  );

  const clear =
    document.getElementById(
      'clearLibraryFilters'
    );

  if (clear) {
    clear.addEventListener(
      'click',
      () => {
        const search =
          document.getElementById(
            'librarySearch'
          );

        const evidence =
          document.getElementById(
            'evidenceFilter'
          );

        const year =
          document.getElementById(
            'yearFilter'
          );

        const area =
          document.getElementById(
            'libraryAreaFilter'
          );

        const sort =
          document.getElementById(
            'librarySort'
          );

        if (search) {
          search.value = '';
        }

        if (evidence) {
          evidence.value =
            'all';
        }

        if (year) {
          year.value =
            'all';
        }

        if (area) {
          area.value =
            'all';
        }

        if (sort) {
          sort.value =
            'default';
        }

        applyLibraryFilters();
      }
    );
  }

  applyLibraryFilters();
}


// ------------------------------------------------------------
// LIBRARY COUNTERS
// ------------------------------------------------------------

function updateLibraryCounters() {
  let publications =
    KR_LIBRARY_STATS.publications;

  let clinicalAreas =
    KR_LIBRARY_STATS.clinicalAreas;

  const paperNodes =
    document.querySelectorAll(
      'article.folder-paper'
    );

  const folderNodes =
    document.querySelectorAll(
      'details.library-folder'
    );

  if (paperNodes.length) {
    publications =
      paperNodes.length;
  }

  if (folderNodes.length) {
    clinicalAreas =
      folderNodes.length;
  }

  const locale =
    getCurrentLang() === 'it'
      ? 'it-IT'
      : 'en-US';

  document
    .querySelectorAll(
      '[data-publication-count]'
    )
    .forEach(el => {
      el.textContent =
        publications
          .toLocaleString(
            locale
          );
    });

  document
    .querySelectorAll(
      '[data-clinical-area-count]'
    )
    .forEach(el => {
      el.textContent =
        clinicalAreas
          .toLocaleString(
            locale
          );
    });
}


// ------------------------------------------------------------
// LATEST EVIDENCE
// ------------------------------------------------------------

function krEscapeHtml(value) {
  return String(
    value ?? ''
  ).replace(
    /[&<>"']/g,
    ch => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#039;'
    })[ch]
  );
}

function latestLang() {
  return getCurrentLang();
}

function latestDateLabel(
  value,
  precision = ''
) {
  if (!value) {
    return '—';
  }

  const locale =
    latestLang() === 'it'
      ? 'it-IT'
      : 'en-GB';

  if (
    !precision &&
    /^\d{4}-01-01$/.test(
      value
    )
  ) {
    return value.slice(
      0,
      4
    );
  }

  if (
    precision === 'year' ||
    /^\d{4}$/.test(
      value
    )
  ) {
    return value.slice(
      0,
      4
    );
  }

  if (
    precision === 'month' ||
    /^\d{4}-\d{2}$/.test(
      value
    )
  ) {
    const [
      year,
      month
    ] =
      value
        .split('-')
        .map(Number);

    if (
      !yea
