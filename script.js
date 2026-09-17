
const setLang = (lang) => {
  document.documentElement.lang = lang;
  document.querySelectorAll('[data-en]').forEach(el => {
    const value = el.dataset[lang];
    if (typeof value !== 'undefined') el.innerHTML = value;
  });
  document.querySelectorAll('.lang button').forEach(b => b.classList.toggle('active', b.dataset.lang === lang));
  const pageTitle = document.querySelector('meta[name="kr-title-' + lang + '"]');
  if (pageTitle) document.title = pageTitle.content;
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
