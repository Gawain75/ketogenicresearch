(async function(){
  const base="https://library.ketogenicresearch.org";
  function currentLang(){try{return localStorage.getItem('kr-lang')||document.documentElement.lang||'en'}catch(e){return document.documentElement.lang||'en'}}
  try{
    const cfg=await fetch(base+"/api/site-public/config",{cache:"no-store"}).then(r=>r.ok?r.json():null);
    if(cfg&&Array.isArray(cfg.menu)&&cfg.menu.length){
      const nav=document.querySelector('.site-nav');
      if(nav){
        const items=cfg.menu.filter(x=>x.visible!==false).sort((a,b)=>(a.order||0)-(b.order||0));
        const direct=items.filter(x=>x.group!=="more"), more=items.filter(x=>x.group==="more");
        nav.innerHTML='';
        direct.forEach(x=>{const a=document.createElement('a');a.href=x.href;a.dataset.en=x.label_en||x.label_it||x.href;a.dataset.it=x.label_it||x.label_en||x.href;a.textContent=currentLang()==='it'?a.dataset.it:a.dataset.en;nav.appendChild(a)});
        if(more.length){const d=document.createElement('details');d.className='nav-more';const s=document.createElement('summary');const sp=document.createElement('span');sp.dataset.en='More';sp.dataset.it='Altro';sp.textContent=currentLang()==='it'?'Altro':'More';const caret=document.createElement('span');caret.className='nav-caret';caret.setAttribute('aria-hidden','true');caret.textContent='▾';s.append(sp,caret);const sub=document.createElement('div');sub.className='nav-submenu';more.forEach(x=>{const a=document.createElement('a');a.href=x.href;a.dataset.en=x.label_en||x.label_it||x.href;a.dataset.it=x.label_it||x.label_en||x.href;a.textContent=currentLang()==='it'?a.dataset.it:a.dataset.en;sub.appendChild(a)});d.append(s,sub);nav.appendChild(d)}
      }
    }
    if(cfg&&cfg.extended){
      const ex=cfg.extended;
      if(ex.director_photo && /director(?:\.html)?$/.test(location.pathname)){const img=document.querySelector('.portrait img');if(img)img.src=ex.director_photo;}
      if(ex.clinical_icons&&typeof ex.clinical_icons==='object'){
        const applyIcon=(box,src)=>{if(!box||!src)return;box.innerHTML='';const mark=document.createElement('span');mark.className='kr-admin-clinical-icon';mark.setAttribute('aria-hidden','true');mark.style.setProperty('--kr-admin-icon','url(\"'+String(src).replace(/[\"\n\r]/g,'')+'\")');box.appendChild(mark);};
        document.querySelectorAll('[data-area-slug]').forEach(el=>{const src=ex.clinical_icons[el.dataset.areaSlug];if(!src)return;const box=el.matches('.folder-icon,.kr-area-icon')?el:el.querySelector('.folder-icon,.kr-area-icon');if(box)applyIcon(box,src);else if(el.matches('img')){const wrap=document.createElement('span');wrap.className='kr-admin-clinical-icon';wrap.style.setProperty('--kr-admin-icon','url(\"'+String(src).replace(/[\"\n\r]/g,'')+'\")');el.replaceWith(wrap);}});
        document.querySelectorAll('details.library-folder[id]').forEach(folder=>{const src=ex.clinical_icons[folder.id];if(src)applyIcon(folder.querySelector('summary .folder-icon'),src);});
      }
    }
  }catch(e){}
  try{
    const path=location.pathname.replace(/^\/+/,"") || "index.html";
    const r=await fetch(base+"/api/site-public/content?path="+encodeURIComponent(path),{cache:"no-store"});
    if(r.status===404)return; const j=await r.json();
    if(j.deleted){document.documentElement.innerHTML='<head><title>Contenuto non disponibile</title></head><body><main style="max-width:760px;margin:80px auto;font:16px Arial;padding:20px"><h1>Contenuto non disponibile</h1><p>Questo contenuto è stato rimosso.</p><p><a href="https://ketogenicresearch.org/">Torna al sito</a></p></main></body>';return;}
    if(j.html){document.open();document.write(j.html.replace(/<script[^>]+site-admin-public\.js[^>]*><\/script>/i,''));document.close();}
  }catch(e){}
})();
