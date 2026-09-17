
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
