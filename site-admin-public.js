(async function(){
  const base="https://library.ketogenicresearch.org";
  try{
    const cfg=await fetch(base+"/api/site-public/config",{cache:"no-store"}).then(r=>r.ok?r.json():null);
    if(cfg&&Array.isArray(cfg.menu)&&cfg.menu.length){
      const nav=document.querySelector('.site-nav');
      if(nav){ const direct=cfg.menu.filter(x=>x.visible!==false&&x.group!=="more").sort((a,b)=>(a.order||0)-(b.order||0)); const links=[...nav.children].filter(x=>x.tagName==='A'); direct.forEach((x,i)=>{if(links[i]){links[i].href=x.href;links[i].textContent=x.label_en||x.label_it||x.href;}}); }
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