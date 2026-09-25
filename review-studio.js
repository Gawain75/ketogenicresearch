(() => {
  'use strict';

  const STORAGE_KEY = 'kr_review_studio_project_v1';
  const $ = id => document.getElementById(id);
  const num = v => Number.parseFloat(v);
  const finite = v => Number.isFinite(v);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

  let project = loadProject() || blankProject();

  function blankProject(){
    return {
      version: 1,
      name: '', question: '', language: 'English',
      protocol: {title:'',type:'Systematic review with possible meta-analysis',primary_outcome:'',population:'',intervention:'',comparator:'',outcomes:'',designs:'',subgroups:'',inclusion:'',exclusion:'',pubmed_query:'',frozen:false,frozen_at:null},
      candidates: [],
      analysis_outcome: '',
      extraction: {},
      meta: null,
      draft: '',
      updated_at: new Date().toISOString()
    };
  }

  function saveProject(){
    project.updated_at = new Date().toISOString();
    localStorage.setItem(STORAGE_KEY, JSON.stringify(project));
  }
  function loadProject(){
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY)); } catch { return null; }
  }
  function setStatus(id, text, kind=''){
    const el=$(id); el.textContent=text; el.className='review-status'+(kind?' '+kind:'');
  }
  function showStep(step){
    document.querySelectorAll('.review-step').forEach(b=>b.classList.toggle('active', b.dataset.step===step));
    document.querySelectorAll('[id^="panel-"]').forEach(p=>p.hidden = p.id !== `panel-${step}`);
    if(step==='screening') renderStudies();
    if(step==='extraction') renderExtraction();
    if(step==='analysis') renderMeta();
    if(step==='draft') $('draftOutput').textContent = project.draft || 'No draft generated.';
  }

  function bindProjectToForm(){
    $('question').value=project.question||'';
    $('projectName').value=project.name||'';
    $('projectLanguage').value=project.language||'English';
    const p=project.protocol||{};
    $('pTitle').value=p.title||''; $('pType').value=p.type||'Systematic review with possible meta-analysis';
    $('pPrimary').value=p.primary_outcome||''; $('pPopulation').value=p.population||''; $('pIntervention').value=p.intervention||'';
    $('pComparator').value=p.comparator||''; $('pOutcomes').value=p.outcomes||''; $('pDesigns').value=p.designs||'';
    $('pSubgroups').value=p.subgroups||''; $('pInclude').value=p.inclusion||''; $('pExclude').value=p.exclusion||''; $('pQuery').value=p.pubmed_query||'';
    $('analysisOutcome').value=project.analysis_outcome||'';
    refreshLock(); refreshMetrics();
    if(project.question) setStatus('questionStatus', `Project loaded · updated ${new Date(project.updated_at).toLocaleString()}`, 'ok');
  }

  function readProtocol(){
    return {
      title:$('pTitle').value.trim(), type:$('pType').value, primary_outcome:$('pPrimary').value.trim(),
      population:$('pPopulation').value.trim(), intervention:$('pIntervention').value.trim(), comparator:$('pComparator').value.trim(),
      outcomes:$('pOutcomes').value.trim(), designs:$('pDesigns').value.trim(), subgroups:$('pSubgroups').value.trim(),
      inclusion:$('pInclude').value.trim(), exclusion:$('pExclude').value.trim(), pubmed_query:$('pQuery').value.trim(),
      frozen: project.protocol?.frozen || false, frozen_at: project.protocol?.frozen_at || null
    };
  }

  function refreshLock(){
    const frozen=!!project.protocol?.frozen;
    $('protocolLock').hidden=!frozen;
    document.querySelectorAll('#panel-protocol input,#panel-protocol textarea,#panel-protocol select').forEach(el=>el.disabled=frozen);
    $('freezeProtocol').disabled=frozen;
    $('unfreezeProtocol').disabled=!frozen;
    $('saveProtocol').disabled=frozen;
    setStatus('protocolStatus', frozen ? `Protocol frozen ${new Date(project.protocol.frozen_at).toLocaleString()}. Changes require explicit unlock.` : 'Protocol not frozen.', frozen?'ok':'');
  }

  async function api(path, payload){
    const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const data=await r.json().catch(()=>({}));
    if(!r.ok) throw new Error(data.error || `Request failed (${r.status})`);
    return data;
  }

  async function generateProtocol(){
    const question=$('question').value.trim();
    if(!question){ setStatus('questionStatus','Enter a research question first.','error'); return; }
    project.question=question; project.name=$('projectName').value.trim()||question.slice(0,80); project.language=$('projectLanguage').value;
    setStatus('questionStatus','Generating structured protocol draft…');
    $('generateProtocol').disabled=true;
    try{
      const data=await api('/api/review/protocol',{question,language:project.language});
      const p=data.protocol||data;
      project.protocol={
        title:p.title||project.name,
        type:p.review_type||p.type||'Systematic review with possible meta-analysis',
        primary_outcome:p.primary_outcome||'',
        population:arrayText(p.population), intervention:arrayText(p.intervention), comparator:arrayText(p.comparator), outcomes:arrayText(p.outcomes),
        designs:arrayText(p.study_designs||p.designs), subgroups:arrayText(p.subgroups), inclusion:arrayText(p.inclusion_criteria||p.inclusion),
        exclusion:arrayText(p.exclusion_criteria||p.exclusion), pubmed_query:p.pubmed_query||'', frozen:false,frozen_at:null
      };
      project.candidates=[]; project.extraction={}; project.meta=null; project.draft=''; saveProject(); bindProjectToForm();
      setStatus('questionStatus','Protocol draft generated. Review and freeze it before searching.','ok'); showStep('protocol');
    }catch(e){ setStatus('questionStatus',e.message,'error'); }
    finally{$('generateProtocol').disabled=false;}
  }
  function arrayText(v){ return Array.isArray(v)?v.join('\n'):String(v||''); }

  function freezeProtocol(){
    project.protocol=readProtocol();
    if(!project.protocol.pubmed_query || !project.protocol.population || !project.protocol.outcomes){ setStatus('protocolStatus','Population, outcomes and PubMed query are required before freezing.','error'); return; }
    project.protocol.frozen=true; project.protocol.frozen_at=new Date().toISOString(); saveProject(); refreshLock();
  }
  function unfreezeProtocol(){ project.protocol.frozen=false; project.protocol.frozen_at=null; saveProject(); refreshLock(); }
  function saveProtocol(){ project.protocol=readProtocol(); saveProject(); setStatus('protocolStatus','Protocol changes saved.','ok'); }

  async function searchPubmed(){
    if(!project.protocol?.frozen){ setStatus('screenStatus','Freeze the protocol before running the search.','error'); return; }
    setStatus('screenStatus','Searching PubMed…'); $('searchPubmed').disabled=true;
    try{
      const data=await api('/api/review/pubmed',{query:project.protocol.pubmed_query,retmax:100});
      const existing=new Map((project.candidates||[]).map(x=>[String(x.pmid),x]));
      const incoming=(data.studies||[]).map(s=>({...s,decision:existing.get(String(s.pmid))?.decision||'unscreened',reason:existing.get(String(s.pmid))?.reason||''}));
      project.candidates=incoming; saveProject(); renderStudies(); refreshMetrics();
      setStatus('screenStatus',`${incoming.length} PubMed records loaded. Search date: ${new Date().toLocaleDateString()}.`,'ok');
    }catch(e){ setStatus('screenStatus',e.message,'error'); }
    finally{$('searchPubmed').disabled=false;}
  }

  function refreshMetrics(){
    const c=project.candidates||[];
    const count=d=>c.filter(x=>x.decision===d).length;
    $('mIdentified').textContent=c.length; $('mIncluded').textContent=count('include'); $('mExcluded').textContent=count('exclude'); $('mUncertain').textContent=count('uncertain');
  }

  function renderStudies(){
    const box=$('studyList'), studies=project.candidates||[]; refreshMetrics();
    if(!studies.length){box.innerHTML='<div class="empty">No candidate studies.</div>';return;}
    box.innerHTML=studies.map((s,i)=>`<article class="study-card"><h3>${esc(s.title||'Untitled')}</h3><div class="study-meta">PMID ${esc(s.pmid)} · ${esc(s.journal||'')} · ${esc(s.pubdate||s.year||'')}<br>${esc((s.authors||[]).join(', '))}</div><div class="study-actions"><button class="screen-btn include ${s.decision==='include'?'active':''}" data-i="${i}" data-d="include">Include</button><button class="screen-btn exclude ${s.decision==='exclude'?'active':''}" data-i="${i}" data-d="exclude">Exclude</button><button class="screen-btn uncertain ${s.decision==='uncertain'?'active':''}" data-i="${i}" data-d="uncertain">Uncertain</button><a class="screen-btn" href="https://pubmed.ncbi.nlm.nih.gov/${encodeURIComponent(s.pmid)}/" target="_blank" rel="noopener">PubMed ↗</a></div>${s.decision==='exclude'?`<div class="review-field" style="margin-top:9px"><label>Exclusion reason</label><input class="exclude-reason" data-i="${i}" value="${esc(s.reason||'')}" placeholder="Required for PRISMA full-text exclusion log"/></div>`:''}</article>`).join('');
    box.querySelectorAll('[data-d]').forEach(btn=>btn.addEventListener('click',()=>{const i=+btn.dataset.i; project.candidates[i].decision=btn.dataset.d; if(btn.dataset.d!=='exclude')project.candidates[i].reason=''; saveProject(); renderStudies();}));
    box.querySelectorAll('.exclude-reason').forEach(inp=>inp.addEventListener('change',()=>{project.candidates[+inp.dataset.i].reason=inp.value.trim(); saveProject();}));
  }

  function includedStudies(){return (project.candidates||[]).filter(s=>s.decision==='include');}
  function renderExtraction(){
    const body=$('extractionBody'), studies=includedStudies(); $('analysisOutcome').value=project.analysis_outcome||project.protocol?.primary_outcome||'';
    if(!studies.length){body.innerHTML='<tr><td colspan="9" class="empty">No included studies.</td></tr>';return;}
    body.innerHTML=studies.map(s=>{const e=project.extraction?.[s.pmid]||{}; return `<tr data-pmid="${esc(s.pmid)}"><td><strong>${esc(shortTitle(s.title))}</strong><br><span class="small">PMID ${esc(s.pmid)}</span></td><td><input data-k="n_i" value="${esc(e.n_i||'')}"></td><td><input data-k="mean_i" value="${esc(e.mean_i||'')}"></td><td><input data-k="sd_i" value="${esc(e.sd_i||'')}"></td><td><input data-k="n_c" value="${esc(e.n_c||'')}"></td><td><input data-k="mean_c" value="${esc(e.mean_c||'')}"></td><td><input data-k="sd_c" value="${esc(e.sd_c||'')}"></td><td><input class="wide" data-k="source" value="${esc(e.source||'')}" placeholder="Table 2, p. 7"></td><td><input type="checkbox" data-k="verified" ${e.verified?'checked':''}></td></tr>`}).join('');
  }
  function shortTitle(t){ t=String(t||''); return t.length>85?t.slice(0,82)+'…':t; }
  function saveExtraction(){
    project.analysis_outcome=$('analysisOutcome').value.trim();
    document.querySelectorAll('#extractionBody tr[data-pmid]').forEach(row=>{
      const e={}; row.querySelectorAll('[data-k]').forEach(el=>{e[el.dataset.k]=el.type==='checkbox'?el.checked:el.value.trim();});
      project.extraction[row.dataset.pmid]=e;
    });
    project.meta=null; saveProject(); setStatus('extractionStatus','Extraction saved. Only rows marked Verified are eligible for pooling.','ok');
  }

  function metaData(){
    return includedStudies().map(s=>{
      const e=project.extraction?.[s.pmid]; if(!e||!e.verified)return null;
      const vals=['n_i','mean_i','sd_i','n_c','mean_c','sd_c'].map(k=>num(e[k])); if(!vals.every(finite)||vals[0]<=1||vals[3]<=1||vals[2]<0||vals[5]<0)return null;
      const [ni,mi,sdi,nc,mc,sdc]=vals; const effect=mi-mc; const variance=(sdi*sdi/ni)+(sdc*sdc/nc); if(!(variance>0))return null;
      return {pmid:s.pmid,title:s.title,n_i:ni,n_c:nc,effect,variance,se:Math.sqrt(variance),source:e.source||''};
    }).filter(Boolean);
  }
  function runMetaAnalysis(){
    saveExtraction(); const rows=metaData();
    if(rows.length<2){ project.meta=null; saveProject(); $('metaResult').innerHTML='<div class="empty">At least two verified studies with complete numeric data are required.</div>'; $('forest').hidden=true; return; }
    const sw=rows.reduce((a,r)=>a+1/r.variance,0), swy=rows.reduce((a,r)=>a+r.effect/r.variance,0); const fixed=swy/sw;
    const Q=rows.reduce((a,r)=>a+(1/r.variance)*Math.pow(r.effect-fixed,2),0), df=rows.length-1;
    const sw2=rows.reduce((a,r)=>a+Math.pow(1/r.variance,2),0), C=sw-(sw2/sw); const tau2=Math.max(0,(Q-df)/C);
    const wr=rows.map(r=>1/(r.variance+tau2)), swr=wr.reduce((a,b)=>a+b,0); const random=rows.reduce((a,r,i)=>a+wr[i]*r.effect,0)/swr; const se=Math.sqrt(1/swr);
    const i2=Q>0?Math.max(0,(Q-df)/Q)*100:0; const meta={k:rows.length,outcome:project.analysis_outcome||project.protocol.primary_outcome,fixed,random,se,ci_low:random-1.96*se,ci_high:random+1.96*se,Q,df,tau2,i2,rows};
    project.meta=meta; saveProject(); renderMeta();
  }
  function fmt(x,d=2){return Number(x).toFixed(d)}
  function renderMeta(){
    const m=project.meta; if(!m){$('metaResult').innerHTML='<div class="empty">No analysis yet.</div>';$('forest').hidden=true;return;}
    $('metaResult').innerHTML=`<strong>${esc(m.outcome||'Continuous outcome')}</strong><div class="metric-grid"><div class="metric"><strong>${m.k}</strong><span>Studies pooled</span></div><div class="metric"><strong>${fmt(m.random)}</strong><span>Random-effects MD</span></div><div class="metric"><strong>${fmt(m.i2,1)}%</strong><span>I²</span></div><div class="metric"><strong>${fmt(m.tau2,3)}</strong><span>τ² (DL)</span></div></div><p>Random-effects MD: <strong>${fmt(m.random)} [95% CI ${fmt(m.ci_low)} to ${fmt(m.ci_high)}]</strong>. Fixed-effect MD: ${fmt(m.fixed)}. Q=${fmt(m.Q,2)}, df=${m.df}.</p><p class="small">Interpretation is not generated automatically. Confirm that outcome definitions, units, time points and comparators are clinically compatible before using the pooled estimate.</p>`;
    $('forest').hidden=false; $('forest').innerHTML=forestSvg(m);
  }
  function forestSvg(m){
    const rows=m.rows.map(r=>({...r,lo:r.effect-1.96*r.se,hi:r.effect+1.96*r.se})); const all=[...rows.flatMap(r=>[r.lo,r.hi]),m.ci_low,m.ci_high,0]; let min=Math.min(...all),max=Math.max(...all); const pad=(max-min||1)*.12; min-=pad; max+=pad;
    const W=900,L=340,R=120,plotW=W-L-R,rowH=36,H=75+rowH*(rows.length+1); const x=v=>L+(v-min)/(max-min)*plotW;
    let s=`<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Forest plot"><text x="10" y="24" font-size="14" font-weight="700">Study</text><text x="${W-112}" y="24" font-size="13" font-weight="700">MD [95% CI]</text><line x1="${x(0)}" x2="${x(0)}" y1="38" y2="${H-25}" stroke="#9aa8b6" stroke-dasharray="4 4"/>`;
    rows.forEach((r,i)=>{const y=55+i*rowH;s+=`<text x="10" y="${y+4}" font-size="12">${esc(shortTitle(r.title))}</text><line x1="${x(r.lo)}" x2="${x(r.hi)}" y1="${y}" y2="${y}" stroke="#324b64" stroke-width="2"/><circle cx="${x(r.effect)}" cy="${y}" r="5" fill="#1f4e79"/><text x="${W-112}" y="${y+4}" font-size="11">${fmt(r.effect)} [${fmt(r.lo)}, ${fmt(r.hi)}]</text>`;});
    const y=55+rows.length*rowH, cx=x(m.random), lx=x(m.ci_low), hx=x(m.ci_high); s+=`<text x="10" y="${y+4}" font-size="12" font-weight="700">Random effects</text><polygon points="${lx},${y} ${cx},${y-7} ${hx},${y} ${cx},${y+7}" fill="#1f4e79"/><text x="${W-112}" y="${y+4}" font-size="11" font-weight="700">${fmt(m.random)} [${fmt(m.ci_low)}, ${fmt(m.ci_high)}]</text></svg>`; return s;
  }

  async function generateDraft(){
    if(!project.protocol?.frozen){setStatus('draftStatus','Freeze the protocol first.','error');return;}
    if(!project.meta){setStatus('draftStatus','Run and validate the meta-analysis first.','error');return;}
    setStatus('draftStatus','Generating draft from validated project data…'); $('generateDraft').disabled=true;
    try{
      const payload={language:project.language,question:project.question,protocol:project.protocol,studies:includedStudies().map(s=>({pmid:s.pmid,title:s.title,journal:s.journal,pubdate:s.pubdate,authors:s.authors})),extraction:project.extraction,meta:project.meta};
      const data=await api('/api/review/draft',payload); project.draft=data.draft||''; saveProject(); $('draftOutput').textContent=project.draft; setStatus('draftStatus','Draft generated. It remains an editorial draft and must be scientifically reviewed.','ok');
    }catch(e){setStatus('draftStatus',e.message,'error');} finally{$('generateDraft').disabled=false;}
  }

  function exportJson(){saveProtocolIfEditable();saveExtractionIfVisible(); download(`${slug(project.name||'review-project')}.json`,JSON.stringify(project,null,2),'application/json');}
  function exportCsv(){saveExtraction(); const rows=[['PMID','Title','Outcome','N intervention','Mean intervention','SD intervention','N control','Mean control','SD control','Source','Verified']]; includedStudies().forEach(s=>{const e=project.extraction[s.pmid]||{};rows.push([s.pmid,s.title,project.analysis_outcome,e.n_i,e.mean_i,e.sd_i,e.n_c,e.mean_c,e.sd_c,e.source,e.verified?'yes':'no']);}); download(`${slug(project.name||'review')}-extraction.csv`,rows.map(r=>r.map(csvCell).join(',')).join('\n'),'text/csv');}
  function csvCell(v){v=String(v??'');return /[",\n]/.test(v)?'"'+v.replace(/"/g,'""')+'"':v;}
  function download(name,text,type){const b=new Blob([text],{type}),u=URL.createObjectURL(b),a=document.createElement('a');a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);}
  function slug(s){return String(s).toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'').slice(0,70)||'review-project';}
  function saveProtocolIfEditable(){if(!project.protocol?.frozen)project.protocol=readProtocol();project.question=$('question').value.trim();project.name=$('projectName').value.trim();project.language=$('projectLanguage').value;saveProject();}
  function saveExtractionIfVisible(){if(!$('panel-extraction').hidden)saveExtraction();}

  document.querySelectorAll('.review-step').forEach(b=>b.addEventListener('click',()=>showStep(b.dataset.step)));
  $('generateProtocol').addEventListener('click',generateProtocol);
  $('freezeProtocol').addEventListener('click',freezeProtocol); $('unfreezeProtocol').addEventListener('click',unfreezeProtocol); $('saveProtocol').addEventListener('click',saveProtocol);
  $('searchPubmed').addEventListener('click',searchPubmed); $('clearCandidates').addEventListener('click',()=>{if(confirm('Clear all candidate studies and screening decisions?')){project.candidates=[];project.extraction={};project.meta=null;saveProject();renderStudies();}});
  $('saveExtraction').addEventListener('click',saveExtraction); $('runMeta').addEventListener('click',runMetaAnalysis); $('generateDraft').addEventListener('click',generateDraft);
  $('exportJson').addEventListener('click',exportJson); $('exportCsv').addEventListener('click',exportCsv);
  $('copyDraft').addEventListener('click',async()=>{await navigator.clipboard.writeText(project.draft||'');setStatus('draftStatus','Draft copied to clipboard.','ok');});
  $('newProject').addEventListener('click',()=>{if(confirm('Start a new project? Export the current project first if needed.')){project=blankProject();saveProject();bindProjectToForm();renderStudies();showStep('question');setStatus('questionStatus','New project ready.');}});
  $('importJson').addEventListener('change',async e=>{const f=e.target.files?.[0];if(!f)return;try{const p=JSON.parse(await f.text());if(!p||p.version!==1)throw new Error('Unsupported project file.');project=p;saveProject();bindProjectToForm();renderStudies();showStep('question');setStatus('questionStatus','Project imported.','ok');}catch(err){setStatus('questionStatus',err.message,'error');}e.target.value='';});

  bindProjectToForm(); renderStudies(); renderMeta();
})();
