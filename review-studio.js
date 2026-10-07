(() => {
  'use strict';

  const STORAGE_KEY = 'kr_review_studio_project_v1';
  const UI_STATE_KEY = 'kr_review_studio_ui_v1';
  const $ = id => document.getElementById(id);
  const num = v => Number.parseFloat(v);
  const finite = v => Number.isFinite(v);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

  let project = loadProject() || blankProject();
  let evidenceAutoRunning=false;
  let evidenceAutoStop=false;

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
  function loadUiState(){
    try { return JSON.parse(localStorage.getItem(UI_STATE_KEY)) || {}; } catch { return {}; }
  }
  function saveUiState(patch){
    const next={...loadUiState(),...patch};
    localStorage.setItem(UI_STATE_KEY,JSON.stringify(next));
    return next;
  }
  function setStatus(id, text, kind=''){
    const el=$(id); el.textContent=text; el.className='review-status'+(kind?' '+kind:'');
  }
  function showStep(step){
    const allowed=new Set(['evidence','question','protocol','screening','extraction','analysis','draft']);
    if(!allowed.has(step))step='evidence';
    document.querySelectorAll('.review-step').forEach(b=>b.classList.toggle('active', b.dataset.step===step));
    document.querySelectorAll('[id^="panel-"]').forEach(p=>p.hidden = p.id !== `panel-${step}`);
    saveUiState({active_step:step});
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
    const opts = payload === undefined
      ? {method:'GET', headers:{'Accept':'application/json'}}
      : {method:'POST', headers:{'Content-Type':'application/json','Accept':'application/json'}, body:JSON.stringify(payload)};
    const r=await fetch(path,opts);
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

  let evidenceAreas=[];
  async function loadEvidenceAreas(){
    try{
      const d=await api('/api/review/evidence/areas');
      evidenceAreas=d.areas||[];
      const sel=$('evidenceArea');
      sel.innerHTML='<option value="">Select an area…</option>'+evidenceAreas.map(a=>`<option value="${esc(a.slug)}">${esc(a.label)} (${a.total})</option>`).join('');
      const savedArea=String(loadUiState().evidence_area||'');
      if(savedArea && evidenceAreas.some(a=>a.slug===savedArea)){
        sel.value=savedArea;
        await refreshEvidence();
        await loadEvidenceSynthesis();
        await loadEvidenceMap();
        await loadContradictionExplorer();
        await loadEvidenceConclusion();
        await loadPublicEvidence();
      }
    }catch(e){setStatus('evidenceStatus',e.message,'error');}
  }
  function evidenceCardHtml(c){
    const list=v=>Array.isArray(v)?(v.length?v.join('; '):'not reported'):(v||'not reported');
    const common=`<p><strong>Population:</strong> ${esc(c.population||'not reported')}<br><strong>Sample size:</strong> ${esc(c.sample_size_details||c.sample_size||'not reported')}<br><strong>Intervention:</strong> ${esc(c.intervention||'not reported')}<br><strong>Comparator:</strong> ${esc(c.comparator||'not reported')}<br><strong>Duration:</strong> ${esc(c.duration||'not reported')}<br><strong>Primary outcome(s):</strong> ${esc(list(c.primary_outcomes))}<br><strong>Effect direction:</strong> ${esc(c.effect_direction||'not reported')} · <strong>Statistical significance:</strong> ${esc(c.statistical_significance||'not reported')}</p>`;
    let specific='';
    if(c.publication_type==='systematic_review_meta_analysis'||c.publication_type==='narrative_review') specific=`<p><strong>Review studies:</strong> ${esc(c.review_studies_included??'not reported')} · <strong>Participants:</strong> ${esc(c.review_participants??'not reported')}<br><strong>Study types:</strong> ${esc(c.review_study_types||'not reported')}<br><strong>Pooled effect:</strong> ${esc(c.pooled_effect||'not reported')}<br><strong>Heterogeneity:</strong> ${esc(c.heterogeneity||'not reported')}<br><strong>Risk of bias / certainty:</strong> ${esc(c.risk_of_bias_or_certainty||'not reported')}</p>`;
    else if(String(c.evidence_domain)==='preclinical'||String(c.publication_type).includes('preclinical')) specific=`<p><strong>Species:</strong> ${esc(c.animal_species||'not reported')}<br><strong>Model:</strong> ${esc(c.animal_model||'not reported')}<br><strong>Mechanistic targets:</strong> ${esc(list(c.mechanistic_targets))}</p>`;
    else specific=`<p><strong>Randomized:</strong> ${esc(c.randomized||'not reported')} · <strong>Controlled:</strong> ${esc(c.controlled||'not reported')} · <strong>Orientation:</strong> ${esc(c.time_orientation||'not reported')}<br><strong>Phenotype:</strong> ${esc(c.population_phenotype||'not reported')}</p>`;
    return `<article class="study-card"><h3>${esc(c.title||('PMID '+c.pmid))}</h3><div class="study-meta">PMID ${esc(c.pmid)} · ${esc(c.publication_type||c.study_design||'')} · ${esc(c.study_design||'')} · ${esc(c.evidence_domain||'')} · purpose: ${esc(c.study_purpose||'')} · source: ${esc(c.source_level||'')} · confidence: ${esc(c.extraction_confidence||'')}</div>${common}${specific}<p><strong>Main result:</strong> ${esc(c.main_result||'not reported')}</p><p class="small"><strong>Limitations:</strong> ${esc(list(c.limitations))}</p><div class="study-actions"><a class="screen-btn" href="https://pubmed.ncbi.nlm.nih.gov/${encodeURIComponent(c.pmid)}/" target="_blank" rel="noopener">PubMed ↗</a></div></article>`;
  }
  async function refreshEvidence(){const area=$('evidenceArea').value;if(!area){$('evTotal').textContent=$('evProcessed').textContent=$('evAbstract').textContent=$('evRemaining').textContent='—';$('evidenceCards').innerHTML='<div class="empty">Choose an area first.</div>';$('largeCorpusNote').hidden=true;return null;}setStatus('evidenceStatus','Loading Evidence Lab status…');try{const d=await api('/api/review/evidence/status?area='+encodeURIComponent(area));$('evTotal').textContent=d.area.total;$('evProcessed').textContent=d.processed;$('evAbstract').textContent=d.source_counts.abstract_available;$('evRemaining').textContent=d.remaining;$('evidenceCards').innerHTML=(d.cards||[]).length?(d.cards||[]).map(evidenceCardHtml).join(''):'<div class="empty">No Evidence Cards generated for this area yet.</div>';const large=!!d.large_corpus;$('largeCorpusNote').hidden=!large;if(large){const indexed=d.indexed_cards==null?'':` Compact index: ${d.indexed_cards}/${d.processed}.`;$('largeCorpusText').textContent=`${d.area.total} Library studies. Automatic processing is resumable and synthesis uses a hierarchical large-corpus index.${indexed}`;}setStatus('evidenceStatus',`${d.processed} of ${d.area.total} studies processed. Abstract available: ${d.source_counts.abstract_available}; PMC-linked: ${d.source_counts.pmc_linked}; metadata only: ${d.source_counts.metadata_only}. Nothing is public.`, 'ok');return d;}catch(e){setStatus('evidenceStatus',e.message,'error');return null;}}
  async function processEvidence(){const area=$('evidenceArea').value;if(!area){setStatus('evidenceStatus','Choose a clinical area first.','error');return;}const btn=$('evidenceProcess');btn.disabled=true;setStatus('evidenceStatus','Extracting the next Evidence Card batch…');try{const d=await api('/api/review/evidence/process',{area,batch:Number($('evidenceBatch').value)||6});setStatus('evidenceStatus',`Processed ${d.processed_now||0} studies. ${d.remaining||0} remaining.`, 'ok');await refreshEvidence();await loadEvidenceMap();await loadContradictionExplorer();await loadEvidenceConclusion();await loadPublicEvidence();}catch(e){setStatus('evidenceStatus',e.message,'error');}finally{btn.disabled=false;}}
  async function autoProcessEvidence(){
    const area=$('evidenceArea').value;if(!area){setStatus('evidenceStatus','Choose a clinical area first.','error');return;}
    if(evidenceAutoRunning)return; evidenceAutoRunning=true;evidenceAutoStop=false;$('evidenceAutoProcess').disabled=true;$('evidenceProcess').disabled=true;$('evidenceStopAuto').disabled=false;
    let cycles=0;
    try{
      while(!evidenceAutoStop){
        const d=await api('/api/review/evidence/process',{area,batch:10});cycles++;
        setStatus('evidenceStatus',`Automatic processing: ${d.processed||0} processed · ${d.remaining||0} remaining${d.warnings?.length?` · ${d.warnings.length} warning(s)`:''}.`,d.warnings?.length?'':'ok');
        $('evProcessed').textContent=d.processed??'—';$('evRemaining').textContent=d.remaining??'—';
        if(!Number(d.remaining||0))break;
        if(cycles%10===0)await refreshEvidence();
        await new Promise(r=>setTimeout(r,1100));
      }
      const d=await refreshEvidence();
      setStatus('evidenceStatus',evidenceAutoStop?`Automatic processing stopped. ${d?.remaining??'—'} studies remain; completed cards are saved and can be resumed.`:`Automatic processing complete. ${d?.processed??'—'} Evidence Cards are available.`,'ok');
      await loadEvidenceMap();await loadContradictionExplorer();await loadEvidenceConclusion();await loadPublicEvidence();
    }catch(e){setStatus('evidenceStatus',`Automatic processing paused: ${e.message}. Completed Evidence Cards were saved; press Auto-process corpus to resume.`,'error');}
    finally{evidenceAutoRunning=false;$('evidenceAutoProcess').disabled=false;$('evidenceProcess').disabled=false;$('evidenceStopAuto').disabled=true;}
  }

  let evidenceMapData=null;
  const evidenceClassLabel=v=>({human_clinical:'Human clinical',reviews:'Reviews',preclinical:'Preclinical',other:'Other'})[v]||v;
  const relevanceLabel=v=>({direct:'Direct',supporting:'Supporting',contextual:'Contextual',not_evaluable:'Not evaluable',exclude:'Excluded'})[v]||v;
  const publicationTypeLabel=v=>String(v||'other').replaceAll('_',' ').replace(/\b\w/g,m=>m.toUpperCase());
  function resetEvidenceMap(message='Choose a clinical area to build the map.'){evidenceMapData=null;$('evidenceMapSummary').innerHTML=`<div class="empty">${esc(message)}</div>`;$('evidenceMapMatrix').innerHTML='';$('evidenceMapResults').innerHTML='<div class="empty">No mapped Evidence Cards loaded.</div>';$('evidenceMapType').innerHTML='<option value="">All</option>';setStatus('evidenceMapStatus','Map not loaded.');}
  function evidenceMapCardHtml(c){
    const direction=String(c.effect_direction||'not_reported').replaceAll('_',' ');
    return `<article class="evidence-map-card" data-pmid="${esc(c.pmid)}"><div class="evidence-map-card-top"><div><strong>${esc(c.title||('PMID '+c.pmid))}</strong><div class="study-meta">PMID ${esc(c.pmid)}${c.year?` · ${esc(c.year)}`:''} · ${esc(publicationTypeLabel(c.publication_type))}</div></div><span class="map-pill map-${esc(c.relevance)}">${esc(relevanceLabel(c.relevance))}</span></div><div class="map-card-tags"><span>${esc(evidenceClassLabel(c.evidence_class))}</span><span>${esc(direction)}</span>${c.randomized==='yes'?'<span>Randomized</span>':''}${c.controlled==='yes'?'<span>Controlled</span>':''}</div><p class="small">${esc(c.main_result||'No extracted result.')}</p><p class="small map-reason"><strong>Map rationale:</strong> ${esc(c.relevance_reason||'')}</p><a class="screen-btn" href="https://pubmed.ncbi.nlm.nih.gov/${encodeURIComponent(c.pmid)}/" target="_blank" rel="noopener">PubMed ↗</a></article>`;
  }
  function applyEvidenceMapFilters(){
    if(!evidenceMapData)return;
    const cls=$('evidenceMapClass').value,rel=$('evidenceMapRelevance').value,type=$('evidenceMapType').value,dir=$('evidenceMapDirection').value;
    const cards=(evidenceMapData.cards||[]).filter(c=>(!cls||c.evidence_class===cls)&&(!rel||c.relevance===rel)&&(!type||c.publication_type===type)&&(!dir||c.effect_direction===dir));
    $('evidenceMapResults').innerHTML=cards.length?cards.map(evidenceMapCardHtml).join(''):'<div class="empty">No Evidence Cards match the selected filters.</div>';
    setStatus('evidenceMapStatus',`${cards.length} of ${evidenceMapData.cards_mapped||0} mapped Evidence Cards shown.`,'ok');
  }
  function setEvidenceMapCell(evidenceClass,relevance){
    if(!evidenceMapData)return;
    $('evidenceMapClass').value=evidenceClass||'';
    $('evidenceMapRelevance').value=relevance||'';
    $('evidenceMapType').value='';
    $('evidenceMapDirection').value='';
    const cards=(evidenceMapData.cards||[]).filter(c=>(!evidenceClass||c.evidence_class===evidenceClass)&&(!relevance||c.relevance===relevance));
    $('evidenceMapResults').innerHTML=cards.length?cards.map(evidenceMapCardHtml).join(''):'<div class="empty">No Evidence Cards in this map cell.</div>';
    setStatus('evidenceMapStatus',`${cards.length} Evidence Cards in ${evidenceClass?evidenceClassLabel(evidenceClass):'all classes'} / ${relevance?relevanceLabel(relevance):'all relevance levels'}.`,'ok');
  }
  function renderEvidenceMap(d){
    evidenceMapData=d;
    const r=d.relevance_counts||{}, dc=d.direction_counts||{};
    $('evidenceMapSummary').innerHTML=`<div class="map-summary-chip"><strong>${Number(d.cards_mapped||0)}</strong><span>Mapped</span></div><div class="map-summary-chip"><strong>${Number(r.direct||0)}</strong><span>Direct</span></div><div class="map-summary-chip"><strong>${Number(r.supporting||0)}</strong><span>Supporting</span></div><div class="map-summary-chip"><strong>${Number(r.contextual||0)}</strong><span>Contextual</span></div><div class="map-summary-chip"><strong>${Number(r.not_evaluable||0)}</strong><span>Not evaluable</span></div><div class="map-summary-chip"><strong>${Number(dc.favorable||0)}</strong><span>Favorable</span></div><div class="map-summary-chip"><strong>${Number(dc.mixed||0)}</strong><span>Mixed</span></div>`;
    const rows=['human_clinical','reviews','preclinical','other'], cols=['direct','supporting','contextual','not_evaluable','exclude'], matrix=d.matrix||{};
    $('evidenceMapMatrix').innerHTML=`<div class="map-grid map-grid-head"><div>Evidence class</div>${cols.map(c=>`<div>${esc(relevanceLabel(c))}</div>`).join('')}</div>`+rows.map(row=>`<div class="map-grid"><div class="map-row-label">${esc(evidenceClassLabel(row))}</div>${cols.map(col=>`<button type="button" class="map-cell" data-map-class="${esc(row)}" data-map-rel="${esc(col)}" data-col-label="${esc(relevanceLabel(col))}"><em class="map-cell-label">${esc(relevanceLabel(col))}</em><strong>${Number(matrix?.[row]?.[col]||0)}</strong><span>studies</span></button>`).join('')}</div>`).join('');
    $('evidenceMapMatrix').querySelectorAll('.map-cell').forEach(b=>b.addEventListener('click',()=>setEvidenceMapCell(b.dataset.mapClass,b.dataset.mapRel)));
    const types=[...new Set((d.cards||[]).map(c=>c.publication_type).filter(Boolean))].sort();
    $('evidenceMapType').innerHTML='<option value="">All</option>'+types.map(t=>`<option value="${esc(t)}">${esc(publicationTypeLabel(t))}</option>`).join('');
    applyEvidenceMapFilters();
  }
  async function loadEvidenceMap(){
    const area=$('evidenceArea').value;if(!area){resetEvidenceMap();return;}
    setStatus('evidenceMapStatus','Loading deterministic Evidence Map…');
    try{const d=await api('/api/review/evidence/map?area='+encodeURIComponent(area));renderEvidenceMap(d);}
    catch(e){setStatus('evidenceMapStatus',e.message,'error');$('evidenceMapResults').innerHTML='<div class="empty">Evidence Map unavailable.</div>';}
  }

  let contradictionData=null;
  const contradictionStatusLabel=v=>({discordant:'Discordant',mixed:'Mixed',consistent_favorable:'Consistent favorable signal',consistent_null_or_unfavorable:'Consistent null / unfavorable',limited:'Limited',insufficient:'Insufficient'})[v]||v;
  const contradictionSignalLabel=v=>({heterogeneous:'Heterogeneous direct human evidence',mixed_with_favorable_signal:'Mixed evidence with a favorable signal',favorable_signal_with_limited_evidence:'Favorable signal with limited evidence',insufficient:'Insufficient outcome-level evidence'})[v]||v;
  const domainDirectionLabel=v=>({favorable:'Favorable',mixed:'Mixed',neutral:'Neutral / null',unfavorable:'Unfavorable',not_reported:'Not reported'})[v]||v;
  function resetContradictionExplorer(message='Choose a clinical area to compare direct human evidence.'){contradictionData=null;$('contradictionSummary').innerHTML=`<div class="empty">${esc(message)}</div>`;$('contradictionGroups').innerHTML='<div class="empty">No outcome comparison loaded.</div>';setStatus('contradictionStatus','Explorer not loaded.');}
  function contradictionStudyHtml(x){
    const n=x.sample_size!==null&&x.sample_size!==undefined&&String(x.sample_size)!==''?` · n=${esc(x.sample_size)}`:'';
    return `<article class="contradiction-study direction-${esc(x.domain_direction)}"><div class="contradiction-study-head"><div><strong>${esc(x.title||('PMID '+x.pmid))}</strong><div class="study-meta">PMID ${esc(x.pmid)}${x.year?` · ${esc(x.year)}`:''}${n} · ${esc(publicationTypeLabel(x.publication_type))}${x.randomized==='yes'?' · randomized':''}${x.controlled==='yes'?' · controlled':''}</div></div><span class="direction-pill direction-${esc(x.domain_direction)}">${esc(domainDirectionLabel(x.domain_direction))}</span></div><p class="small"><strong>Intervention:</strong> ${esc(x.intervention||'not reported')}${x.comparator?`<br><strong>Comparator:</strong> ${esc(x.comparator)}`:''}</p><p class="small"><strong>Result:</strong> ${esc(x.main_result||'not reported')}</p><a class="screen-btn" href="https://pubmed.ncbi.nlm.nih.gov/${encodeURIComponent(x.pmid)}/" target="_blank" rel="noopener">PubMed ↗</a></article>`;
  }
  function renderContradictionExplorer(d){
    contradictionData=d;
    $('contradictionSummary').innerHTML=`<div class="contradiction-chip"><strong>${Number(d.direct_human_studies||0)}</strong><span>Direct human studies</span></div><div class="contradiction-chip"><strong>${Number(d.outcome_domains||0)}</strong><span>Outcome domains</span></div><div class="contradiction-chip warn"><strong>${Number(d.discordant_domains||0)}</strong><span>Discordant</span></div><div class="contradiction-chip mixed"><strong>${Number(d.mixed_domains||0)}</strong><span>Mixed</span></div><div class="contradiction-chip good"><strong>${Number(d.consistent_favorable_domains||0)}</strong><span>Consistent favorable</span></div>`;
    const groups=Array.isArray(d.groups)?d.groups:[];
    $('contradictionGroups').innerHTML=groups.length?groups.map(g=>{
      const c=g.counts||{};
      const counts=`${Number(c.favorable||0)} favorable · ${Number(c.mixed||0)} mixed · ${Number(c.neutral||0)} neutral/null · ${Number(c.unfavorable||0)} unfavorable`;
      return `<section class="contradiction-domain status-${esc(g.status)}"><div class="contradiction-domain-head"><div><h4>${esc(g.label||g.domain)}</h4><div class="small">${esc(counts)} · ${Number((g.studies||[]).length)} study entries</div></div><span class="contradiction-status status-${esc(g.status)}">${esc(contradictionStatusLabel(g.status))}</span></div><div class="contradiction-study-list">${(g.studies||[]).map(contradictionStudyHtml).join('')}</div></section>`;
    }).join(''):'<div class="empty">No direct human outcome evidence available for comparison.</div>';
    setStatus('contradictionStatus',`${contradictionSignalLabel(d.conclusion_signal)}. This explorer compares outcome domains; it does not replace the approved synthesis.`,'ok');
  }
  async function loadContradictionExplorer(){
    const area=$('evidenceArea').value;if(!area){resetContradictionExplorer();return;}
    setStatus('contradictionStatus','Loading outcome-level comparison…');
    try{const d=await api('/api/review/evidence/contradictions?area='+encodeURIComponent(area));renderContradictionExplorer(d);}
    catch(e){setStatus('contradictionStatus',e.message,'error');$('contradictionGroups').innerHTML='<div class="empty">Contradiction Explorer unavailable.</div>';}
  }

  const conclusionDomainList=(arr,empty='None identified')=>Array.isArray(arr)&&arr.length?`<ul>${arr.map(x=>`<li><strong>${esc(x.label||x.domain)}</strong></li>`).join('')}</ul>`:`<p class="small">${esc(empty)}</p>`;
  function resetEvidenceConclusion(message='Approve a current synthesis to generate the evidence conclusion.'){
    $('evidenceConclusionSummary').innerHTML=`<div class="empty">${esc(message)}</div>`;
    $('evidenceConclusionDetails').innerHTML='';
    setStatus('evidenceConclusionStatus','Conclusion not loaded.');
  }
  function renderEvidenceConclusion(d){
    $('evidenceConclusionSummary').innerHTML=`<div class="conclusion-chip"><strong>${esc(d.signal||'—')}</strong><span>Overall signal</span></div><div class="conclusion-chip"><strong>${esc(d.maturity||'—')}</strong><span>Evidence maturity</span></div><div class="conclusion-chip"><strong>${Number(d.direct_human_studies||0)}</strong><span>Direct human studies</span></div><div class="conclusion-chip"><strong>${Number(d.clinical_trials||0)}</strong><span>Clinical trials</span></div>`;
    $('evidenceConclusionDetails').innerHTML=`<div class="conclusion-callout"><h4>Structured interpretation</h4><p>${esc(d.interpretation||'')}</p></div><div class="conclusion-columns"><section><h4>Most consistent favorable domains</h4>${conclusionDomainList(d.consistent_favorable_domains,'No domain met the consistency rule.')}</section><section><h4>Mixed / uncertain domains</h4>${conclusionDomainList([...(d.mixed_domains||[]),...(d.discordant_domains||[])],'No mixed or discordant domains identified.')}</section></div><div class="conclusion-columns"><section><h4>Main limitations</h4>${Array.isArray(d.limitations)&&d.limitations.length?`<ul>${d.limitations.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:'<p class="small">No limitations recorded in the approved synthesis.</p>'}</section><section><h4>Research gaps</h4>${Array.isArray(d.research_gaps)&&d.research_gaps.length?`<ul>${d.research_gaps.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:'<p class="small">No research gaps recorded in the approved synthesis.</p>'}</section></div><div class="approved-boundary"><h4>Approved clinical bottom line</h4><p><strong>${esc(d.approved_bottom_line||'Not available.')}</strong></p><p class="small">${esc(d.note||'')}</p></div>`;
    setStatus('evidenceConclusionStatus',`Conclusion anchored to the approved synthesis${d.approval?.approved_at?` of ${new Date(d.approval.approved_at).toLocaleString()}`:''}.`,'ok');
  }
  async function loadEvidenceConclusion(){
    const area=$('evidenceArea').value;if(!area){resetEvidenceConclusion();return;}
    setStatus('evidenceConclusionStatus','Loading approved evidence conclusion…');
    try{const d=await api('/api/review/evidence/conclusion?area='+encodeURIComponent(area));renderEvidenceConclusion(d);}
    catch(e){resetEvidenceConclusion(e.message);setStatus('evidenceConclusionStatus',e.message,'error');}
  }

  function resetPublicEvidence(message='Approve the current synthesis, then publish manually when ready.'){
    const badge=$('publicEvidenceBadge');badge.textContent='Not published';badge.className='protocol-lock';
    $('publicEvidencePublish').disabled=true;$('publicEvidenceUnpublish').disabled=true;$('publicEvidenceOpen').hidden=true;$('publicEvidenceOpen').href='#';
    $('publicEvidencePreview').innerHTML=`<div class="empty">${esc(message)}</div>`;
    setStatus('publicEvidenceStatus','Nothing is published automatically.');
  }
  function publicEvidencePreviewHtml(b){
    if(!b)return '<div class="empty">No public snapshot exists for this area.</div>';
    const fav=(b.consistent_favorable_domains||[]).map(x=>x.label||x),mixed=(b.mixed_domains||[]).map(x=>x.label||x);
    const list=(a,empty)=>Array.isArray(a)&&a.length?`<ul>${a.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:`<p class="small">${esc(empty)}</p>`;
    return `<div class="public-preview"><h4>${esc(b.area?.label||'Approved evidence brief')}</h4><p><strong>${esc(b.signal||'')}</strong> · maturity: ${esc(b.maturity||'—')} · ${Number(b.direct_human_studies||0)} direct human studies · ${Number(b.clinical_trials||0)} clinical trials</p><p>${esc(b.approved_overall_interpretation||b.interpretation||'')}</p><div class="public-preview-grid"><section><h4>Consistent favorable domains</h4>${list(fav,'None identified.')}</section><section><h4>Mixed / uncertain domains</h4>${list(mixed,'None identified.')}</section></div><p><strong>Clinical bottom line:</strong> ${esc(b.approved_bottom_line||'')}</p><p class="small">Published snapshot: ${b.published_at?new Date(b.published_at).toLocaleString():'—'} · no live AI call for visitors.</p></div>`;
  }
  function renderPublicEvidence(d){
    const b=d?.published||null,badge=$('publicEvidenceBadge'),can=!!d?.can_publish;
    $('publicEvidencePublish').disabled=!can;$('publicEvidenceUnpublish').disabled=!b;
    if(b){badge.textContent='Published';badge.className='protocol-lock review-state-approved';$('publicEvidenceOpen').hidden=false;$('publicEvidenceOpen').href=d.public_url||`/evidence/${encodeURIComponent(d.area?.slug||'')}`;$('publicEvidencePreview').innerHTML=publicEvidencePreviewHtml(b);setStatus('publicEvidenceStatus',d.approval_current?`Public snapshot published ${b.published_at?new Date(b.published_at).toLocaleString():''}. It remains fixed until you publish again or unpublish it.`:`Public snapshot remains live, but the current evidence state is not approved. Re-review and approve before replacing the public snapshot.`,d.approval_current?'ok':'error');}
    else{badge.textContent='Not published';badge.className='protocol-lock';$('publicEvidenceOpen').hidden=true;$('publicEvidenceOpen').href='#';$('publicEvidencePreview').innerHTML='<div class="empty">No public snapshot exists for this area.</div>';setStatus('publicEvidenceStatus',can?'Current synthesis is approved. Publishing requires a separate manual action.':'A current approved synthesis is required before publication.');}
  }
  async function loadPublicEvidence(){
    const area=$('evidenceArea').value;if(!area){resetPublicEvidence();return;}
    try{const d=await api('/api/review/evidence/publication?area='+encodeURIComponent(area));renderPublicEvidence(d);}
    catch(e){resetPublicEvidence(e.message);setStatus('publicEvidenceStatus',e.message,'error');}
  }
  async function publicEvidenceAction(action){
    const area=$('evidenceArea').value;if(!area){setStatus('publicEvidenceStatus','Choose a clinical area first.','error');return;}
    if(action==='publish'&&!confirm('Publish a fixed public Evidence Brief from the current approved synthesis? Visitors will not trigger Groq calls.'))return;
    if(action==='unpublish'&&!confirm('Remove this Evidence Brief from the public website?'))return;
    const buttons=[$('publicEvidencePublish'),$('publicEvidenceUnpublish')];buttons.forEach(x=>x.disabled=true);
    try{const d=await api('/api/review/evidence/publication',{area,action});renderPublicEvidence(d);}
    catch(e){setStatus('publicEvidenceStatus',e.message,'error');await loadPublicEvidence();}
  }

  function resetAskEvidence(message='No question asked yet.'){
    $('askEvidenceAnswer').innerHTML=`<div class="empty">${esc(message)}</div>`;
    setStatus('askEvidenceStatus','Ready when the current synthesis is approved.');
  }
  function askEvidenceHtml(d){
    const claims=Array.isArray(d.claims)&&d.claims.length?`<div class="ask-claims">${d.claims.map(x=>`<div class="ask-claim"><p>${esc(x.text||'')}</p><div class="small">${pmidLinks(x.pmids||[])}</div></div>`).join('')}</div>`:'<p class="small">No source-locked claims were available for this question.</p>';
    return `<div class="ask-answer"><div class="ask-answer-top"><span class="map-pill">${esc(String(d.support_level||'not_supported').replaceAll('_',' '))}</span><span class="small">${Number(d.cards_considered||0)} considered · ${Number(d.pmids?.length||0)} cited</span></div><p class="ask-summary"><strong>${esc(d.summary||'')}</strong></p>${claims}${d.caveat?`<div class="notice"><strong>Caveat.</strong> ${esc(d.caveat)}</div>`:''}</div>`;
  }
  async function askEvidence(){
    const area=$('evidenceArea').value,question=$('askEvidenceQuestion').value.trim();
    if(!area){setStatus('askEvidenceStatus','Choose a clinical area first.','error');return;}
    if(!question){setStatus('askEvidenceStatus','Enter an evidence question.','error');return;}
    const btn=$('askEvidenceSubmit');btn.disabled=true;setStatus('askEvidenceStatus','Answering from approved Evidence Cards only…');
    try{const d=await api('/api/review/evidence/ask',{area,question});$('askEvidenceAnswer').innerHTML=askEvidenceHtml(d);setStatus('askEvidenceStatus',`Answer source-locked to ${d.pmids?.length||0} cited PMID${(d.pmids?.length||0)===1?'':'s'}.`,'ok');}
    catch(e){$('askEvidenceAnswer').innerHTML='<div class="empty">No answer generated.</div>';setStatus('askEvidenceStatus',e.message,'error');}
    finally{btn.disabled=false;}
  }

  function pmidLinks(pmids){return (pmids||[]).map(p=>`<a href="https://pubmed.ncbi.nlm.nih.gov/${encodeURIComponent(p)}/" target="_blank" rel="noopener">PMID ${esc(p)}</a>`).join(', ');}
  function synthesisHtml(s){
    if(!s)return '<div class="empty">No synthesis generated for this area yet.</div>';
    const items=(arr,field)=>Array.isArray(arr)&&arr.length?'<ul>'+arr.map(x=>typeof x==='string'?`<li>${esc(x)}</li>`:`<li>${esc(x[field]||'')}${x.pmids?.length?` <span class="small">(${pmidLinks(x.pmids)})</span>`:''}</li>`).join('')+'</ul>':'<p class="small">No specific items identified.</p>';
    const processed=Number(s.cards_processed??s.cards_analyzed??0),included=Number(s.cards_analyzed??0),excluded=Number(s.cards_excluded??Math.max(0,processed-included)),sent=Number(s.cards_synthesized??s.cards_sent_to_model??included),chunks=Number(s.synthesis_chunks||0);
    const profile=s.evidence_profile||{};
    const profileRows=[['Clinical trials',profile.clinical_trial],['Observational',profile.observational],['Systematic reviews / meta-analyses',profile.systematic_review_meta_analysis],['Narrative reviews',profile.narrative_review],['Preclinical animal',profile.preclinical_animal],['Mechanistic human',profile.mechanistic_human],['Mechanistic preclinical',profile.mechanistic_preclinical],['Case reports / series',profile.case_report_series],['Protocols',profile.protocol],['Other',profile.other]].filter(x=>Number(x[1]||0)>0);
    const profileHtml=profileRows.length?'<ul>'+profileRows.map(([k,v])=>`<li>${esc(k)}: <strong>${Number(v||0)}</strong></li>`).join('')+'</ul>':'<p class="small">Evidence profile unavailable for this saved synthesis. Regenerate it to add the audit profile.</p>';
    const rel=s.relevance_profile||{};
    const excludedCards=Array.isArray(s.excluded_cards)?s.excluded_cards:[];
    const metadataExcluded=excludedCards.filter(x=>String(x.reason||'').toLowerCase().includes('metadata-only')).length;
    const irrelevantExcluded=excludedCards.length-metadataExcluded;
    const relHtml=s.relevance_profile?`<ul><li>Direct evidence: <strong>${Number(rel.direct||0)}</strong></li><li>Supporting evidence: <strong>${Number(rel.supporting||0)}</strong></li><li>Contextual evidence: <strong>${Number(rel.contextual||0)}</strong></li><li>Not evaluable / metadata-only: <strong>${metadataExcluded}</strong></li><li>Excluded as not relevant: <strong>${irrelevantExcluded}</strong></li></ul>`:'<p class="small">Relevance profile unavailable for this saved synthesis. Regenerate it to add relevance screening.</p>';
    const audit=Array.isArray(s.relevance_cards)?s.relevance_cards:[];
    const contextual=audit.filter(x=>x.level==='contextual');
    const contextualHtml=contextual.length?'<ul>'+contextual.map(x=>`<li><a href="https://pubmed.ncbi.nlm.nih.gov/${encodeURIComponent(x.pmid)}/" target="_blank" rel="noopener">PMID ${esc(x.pmid)}</a>${x.title?` — ${esc(x.title)}`:''}<br><span class="small">${esc(x.reason||'contextual evidence')}</span></li>`).join('')+'</ul>':'<p class="small">No contextual-only cards.</p>';
    const excludedHtml=Array.isArray(s.excluded_cards)&&s.excluded_cards.length?'<ul>'+s.excluded_cards.map(x=>`<li><a href="https://pubmed.ncbi.nlm.nih.gov/${encodeURIComponent(x.pmid)}/" target="_blank" rel="noopener">PMID ${esc(x.pmid)}</a>${x.title?` — ${esc(x.title)}`:''}<br><span class="small">Reason: ${esc(x.reason||'non-evaluable')}</span></li>`).join('')+'</ul>':'<p class="small">No excluded cards.</p>';
    return `<article class="study-card"><div class="study-meta">Generated ${esc(s.generated_at||'')} · ${processed} processed · ${included} included · ${excluded} excluded · ${sent} synthesized${chunks?` in ${chunks} batches`:''} · consistency: ${esc(s.evidence_consistency||'not assessed')}</div><h3>Evidence profile</h3>${profileHtml}<h3>Evidence relevance</h3>${relHtml}<h3>Contextual evidence</h3>${contextualHtml}<h3>Excluded from synthesis</h3>${excludedHtml}<h3>Overall interpretation</h3><p>${esc(s.overall_interpretation||'Not available.')}</p><h3>Human clinical evidence</h3><p>${esc(s.human_clinical||'Insufficient evidence in the processed cards.')}</p><h3>Reviews / meta-analyses</h3><p>${esc(s.reviews_meta_analyses||'Insufficient evidence in the processed cards.')}</p><h3>Preclinical & mechanistic evidence</h3><p>${esc(s.preclinical_mechanistic||'Insufficient evidence in the processed cards.')}</p><h3>Main findings</h3>${items(s.main_findings,'finding')}<h3>Conflicting evidence</h3>${items(s.conflicting_evidence,'issue')}<h3>Limitations</h3>${items(s.limitations)}<h3>Research gaps</h3>${items(s.research_gaps)}<h3>Provisional bottom line</h3><p><strong>${esc(s.bottom_line||'Not available.')}</strong></p><p class="small">Private provisional synthesis. Not a formal GRADE assessment and not published to the public website.</p></article>`;
  }
  function reviewStatusLabel(status){
    return ({draft:'Draft',reviewed:'Reviewed',approved:'Approved',changes_pending_review:'Changes pending review'})[status]||'Draft';
  }
  function reviewBadgeClass(status){
    if(status==='approved')return 'protocol-lock review-state-approved';
    if(status==='reviewed')return 'protocol-lock review-state-reviewed';
    if(status==='changes_pending_review')return 'protocol-lock review-state-changed';
    return 'protocol-lock review-state-draft';
  }
  function diffRows(obj){
    const entries=Object.entries(obj||{}); if(!entries.length)return '';
    return '<ul>'+entries.map(([k,v])=>`<li>${esc(k.replaceAll('_',' '))}: ${Number(v.before||0)} → <strong>${Number(v.after||0)}</strong>${Number(v.delta||0)?` (${Number(v.delta)>0?'+':''}${Number(v.delta)})`:''}</li>`).join('')+'</ul>';
  }
  function claimChangeList(arr,field){
    if(!Array.isArray(arr)||!arr.length)return '';
    return '<ul>'+arr.map(x=>`<li>${esc(x?.[field]||'')}${x?.pmids?.length?` <span class="small">(${pmidLinks(x.pmids)})</span>`:''}</li>`).join('')+'</ul>';
  }
  function whatChangedHtml(changes,review){
    if(!changes?.baseline){return '<div class="notice"><strong>No approved baseline yet.</strong> Approve the current synthesis to establish the comparison baseline.</div>';}
    if(!changes.has_changes){return '<div class="notice review-no-changes"><strong>No changes since the approved synthesis.</strong> The current evidence state matches the approved snapshot.</div>';}
    const blocks=[];
    if(changes.new_cards?.length)blocks.push(`<h4>New Evidence Cards</h4><p>${changes.new_cards.map(x=>esc(x)).join(', ')}</p>`);
    if(changes.removed_cards?.length)blocks.push(`<h4>Removed Evidence Cards</h4><p>${changes.removed_cards.map(x=>esc(x)).join(', ')}</p>`);
    if(Object.keys(changes.profile_changes||{}).length)blocks.push(`<h4>Evidence profile changes</h4>${diffRows(changes.profile_changes)}`);
    if(Object.keys(changes.relevance_changes||{}).length)blocks.push(`<h4>Relevance changes</h4>${diffRows(changes.relevance_changes)}`);
    if(changes.main_findings_added?.length)blocks.push(`<h4>Main findings added</h4>${claimChangeList(changes.main_findings_added,'finding')}`);
    if(changes.main_findings_removed?.length)blocks.push(`<h4>Main findings removed</h4>${claimChangeList(changes.main_findings_removed,'finding')}`);
    if(changes.conflicts_added?.length)blocks.push(`<h4>Conflicting evidence added</h4>${claimChangeList(changes.conflicts_added,'issue')}`);
    if(changes.conflicts_removed?.length)blocks.push(`<h4>Conflicting evidence removed</h4>${claimChangeList(changes.conflicts_removed,'issue')}`);
    if(changes.overall_interpretation_changed)blocks.push('<h4>Overall interpretation changed</h4><p class="small">The current wording differs from the approved snapshot.</p>');
    if(changes.bottom_line_changed)blocks.push('<h4>Bottom line changed</h4><p class="small">The current wording differs from the approved snapshot.</p>');
    return `<div class="notice review-changes"><strong>Changes detected since approval.</strong> Review them before approving the updated synthesis.</div>${blocks.join('')}`;
  }
  function resetEvidenceReview(message='Load a saved synthesis to check its review status.'){
    const badge=$('evidenceReviewBadge'); badge.textContent='Draft'; badge.className='protocol-lock review-state-draft';
    $('evidenceReviewNote').value='';
    $('evidenceMarkReviewed').disabled=false;
    $('evidenceApprove').disabled=true;
    $('evidenceReopen').disabled=true;
    setStatus('evidenceReviewStatus',message);
    $('evidenceWhatChanged').innerHTML='<div class="empty">No approved baseline yet.</div>';
  }
  function renderEvidenceReview(d){
    const r=d?.review||{}, status=r.effective_status||r.status||'draft';
    const badge=$('evidenceReviewBadge'); badge.textContent=reviewStatusLabel(status); badge.className=reviewBadgeClass(status);
    $('evidenceReviewNote').value=r.note||'';
    $('evidenceMarkReviewed').disabled=status==='reviewed'||status==='approved';
    $('evidenceApprove').disabled=status!=='reviewed';
    $('evidenceReopen').disabled=status==='draft';
    const who=status==='approved'?(r.approved_by||''):(status==='reviewed'?(r.reviewed_by||''):'');
    const when=status==='approved'?(r.approved_at||''):(status==='reviewed'?(r.reviewed_at||''):'');
    let msg=`Review status: ${reviewStatusLabel(status)}.`;
    if(who||when)msg+=` ${who?`By ${who}`:''}${when?`${who?' · ':''}${new Date(when).toLocaleString()}`:''}.`;
    if(status==='changes_pending_review')msg+=' The evidence state has changed since the last approval.';
    setStatus('evidenceReviewStatus',msg,status==='approved'?'ok':(status==='changes_pending_review'?'error':''));
    $('evidenceWhatChanged').innerHTML=whatChangedHtml(d?.changes,r);
  }
  async function loadEvidenceReview(){
    const area=$('evidenceArea').value;
    if(!area){resetEvidenceReview('Choose a clinical area first.');return;}
    try{const d=await api('/api/review/evidence/review?area='+encodeURIComponent(area));renderEvidenceReview(d);}
    catch(e){setStatus('evidenceReviewStatus',e.message,'error');$('evidenceWhatChanged').innerHTML='<div class="empty">Review state unavailable until a saved synthesis exists.</div>';}
  }
  async function evidenceReviewAction(action){
    const area=$('evidenceArea').value;if(!area){setStatus('evidenceReviewStatus','Choose a clinical area first.','error');return;}
    if(action==='approve'&&!confirm('Approve the current synthesis as the reviewed baseline? This does not publish it to the public website.'))return;
    const buttons=[$('evidenceMarkReviewed'),$('evidenceApprove'),$('evidenceReopen'),$('evidenceRefreshReview')];buttons.forEach(b=>b.disabled=true);
    try{const d=await api('/api/review/evidence/review',{area,action,note:$('evidenceReviewNote').value.trim()});renderEvidenceReview(d);await loadEvidenceConclusion();await loadPublicEvidence();}
    catch(e){setStatus('evidenceReviewStatus',e.message,'error');buttons.forEach(b=>b.disabled=false);if(action!=='review')$('evidenceApprove').disabled=true;}
  }
  async function loadEvidenceSynthesis(){const area=$('evidenceArea').value;if(!area){setStatus('synthesisStatus','Choose a clinical area first.','error');resetEvidenceReview('Choose a clinical area first.');return;}resetEvidenceReview('Loading review status…');setStatus('synthesisStatus','Loading saved synthesis…');try{const d=await api('/api/review/evidence/synthesis?area='+encodeURIComponent(area));$('evidenceSynthesis').innerHTML=synthesisHtml(d.synthesis);setStatus('synthesisStatus',d.synthesis?`Saved synthesis loaded: ${d.synthesis.cards_processed??d.synthesis.cards_analyzed} processed · ${d.synthesis.cards_analyzed} included · ${d.synthesis.cards_excluded??0} excluded.`:'No saved synthesis for this area yet.',d.synthesis?'ok':'');if(d.synthesis)await loadEvidenceReview();else resetEvidenceReview('No saved synthesis for this area yet.');}catch(e){setStatus('synthesisStatus',e.message,'error');resetEvidenceReview('Review state unavailable.');}}
  async function generateEvidenceSynthesis(){const area=$('evidenceArea').value;if(!area){setStatus('synthesisStatus','Choose a clinical area first.','error');return;}const btn=$('evidenceSynthesize');btn.disabled=true;setStatus('synthesisStatus','Starting provisional synthesis…');try{for(let step=0;step<5000;step++){const d=await api('/api/review/evidence/synthesize',{area});if(d.done&&d.synthesis){$('evidenceSynthesis').innerHTML=synthesisHtml(d.synthesis);setStatus('synthesisStatus',`Provisional synthesis: ${d.synthesis.cards_processed??d.synthesis.cards_analyzed} processed · ${d.synthesis.cards_analyzed} included · ${d.synthesis.cards_excluded??0} excluded. Nothing has been published.`,'ok');await loadEvidenceReview();await loadPublicEvidence();return;}const p=d.progress||{};let msg=p.message||'';if(p.phase==='large_index')msg=msg||`Large Corpus index: ${Number(p.completed||0)}/${Number(p.total||0)} cards prepared.`;else if(p.phase==='chunks')msg=`Hierarchical synthesis: ${Number(p.completed||0)}/${Number(p.total||0)} batches completed. Checkpoint saved.`;else if(!msg)msg=`Synthesis progress: ${Number(p.completed||0)}/${Number(p.total||0)} completed.`;setStatus('synthesisStatus',msg,'ok');const wait=Math.max(900,Math.min(65000,Number(p.wait_seconds||0)*1000));await new Promise(r=>setTimeout(r,wait));}throw new Error('Synthesis reached the safety step limit. Press Generate synthesis to resume from saved checkpoints.');}catch(e){setStatus('synthesisStatus',e.message,'error');}finally{btn.disabled=false;}}

  document.querySelectorAll('.review-step').forEach(b=>b.addEventListener('click',()=>showStep(b.dataset.step)));
  $('generateProtocol').addEventListener('click',generateProtocol);
  $('freezeProtocol').addEventListener('click',freezeProtocol); $('unfreezeProtocol').addEventListener('click',unfreezeProtocol); $('saveProtocol').addEventListener('click',saveProtocol);
  $('searchPubmed').addEventListener('click',searchPubmed); $('clearCandidates').addEventListener('click',()=>{if(confirm('Clear all candidate studies and screening decisions?')){project.candidates=[];project.extraction={};project.meta=null;saveProject();renderStudies();}});
  $('saveExtraction').addEventListener('click',saveExtraction); $('runMeta').addEventListener('click',runMetaAnalysis); $('generateDraft').addEventListener('click',generateDraft);
  $('exportJson').addEventListener('click',exportJson); $('exportCsv').addEventListener('click',exportCsv);
  $('copyDraft').addEventListener('click',async()=>{await navigator.clipboard.writeText(project.draft||'');setStatus('draftStatus','Draft copied to clipboard.','ok');});
  $('newProject').addEventListener('click',()=>{if(confirm('Start a new project? Export the current project first if needed.')){project=blankProject();saveProject();bindProjectToForm();renderStudies();showStep('question');setStatus('questionStatus','New project ready.');}});
  $('importJson').addEventListener('change',async e=>{const f=e.target.files?.[0];if(!f)return;try{const p=JSON.parse(await f.text());if(!p||p.version!==1)throw new Error('Unsupported project file.');project=p;saveProject();bindProjectToForm();renderStudies();showStep('question');setStatus('questionStatus','Project imported.','ok');}catch(err){setStatus('questionStatus',err.message,'error');}e.target.value='';});

  $('evidenceArea').addEventListener('change',()=>{evidenceAutoStop=true;saveUiState({evidence_area:$('evidenceArea').value||''});resetEvidenceMap();resetContradictionExplorer();resetEvidenceConclusion();resetPublicEvidence();resetAskEvidence();refreshEvidence();loadEvidenceSynthesis();loadEvidenceMap();loadContradictionExplorer();loadEvidenceConclusion();loadPublicEvidence();}); $('evidenceRefresh').addEventListener('click',()=>{refreshEvidence();loadEvidenceMap();loadContradictionExplorer();loadEvidenceConclusion();loadPublicEvidence();}); $('evidenceProcess').addEventListener('click',processEvidence); $('evidenceAutoProcess').addEventListener('click',autoProcessEvidence); $('evidenceStopAuto').addEventListener('click',()=>{evidenceAutoStop=true;$('evidenceStopAuto').disabled=true;setStatus('evidenceStatus','Stopping after the current batch…');}); $('evidenceSynthesize').addEventListener('click',generateEvidenceSynthesis); $('evidenceLoadSynthesis').addEventListener('click',()=>{loadEvidenceSynthesis();loadEvidenceMap();loadContradictionExplorer();loadEvidenceConclusion();loadPublicEvidence();}); $('evidenceMarkReviewed').addEventListener('click',()=>evidenceReviewAction('review')); $('evidenceApprove').addEventListener('click',()=>evidenceReviewAction('approve')); $('evidenceReopen').addEventListener('click',()=>evidenceReviewAction('reopen')); $('evidenceRefreshReview').addEventListener('click',()=>{loadEvidenceReview();loadEvidenceConclusion();loadPublicEvidence();}); $('publicEvidencePublish').addEventListener('click',()=>publicEvidenceAction('publish')); $('publicEvidenceUnpublish').addEventListener('click',()=>publicEvidenceAction('unpublish')); $('evidenceRefreshMap').addEventListener('click',loadEvidenceMap); $('evidenceRefreshContradictions').addEventListener('click',()=>{loadContradictionExplorer();loadEvidenceConclusion();}); $('evidenceRefreshConclusion').addEventListener('click',loadEvidenceConclusion); $('askEvidenceSubmit').addEventListener('click',askEvidence); $('askEvidenceClear').addEventListener('click',()=>{$('askEvidenceQuestion').value='';resetAskEvidence();}); $('askEvidenceQuestion').addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key==='Enter')askEvidence();}); $('evidenceMapClass').addEventListener('change',applyEvidenceMapFilters); $('evidenceMapRelevance').addEventListener('change',applyEvidenceMapFilters); $('evidenceMapType').addEventListener('change',applyEvidenceMapFilters); $('evidenceMapDirection').addEventListener('change',applyEvidenceMapFilters);

  bindProjectToForm(); renderStudies(); renderMeta();
  showStep('evidence');
  loadEvidenceAreas();
})();
