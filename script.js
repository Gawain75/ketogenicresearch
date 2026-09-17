
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
