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
    try{const d=await api('/api/review/evidence/areas');evidenceAreas=d.areas||[];const sel=$('evidenceArea');sel.innerHTML='<option value="">Select an area…</option>'+evidenceAreas.map(a=>`<option value="${esc(a.slug)}">${esc(a.label)} (${a.total})</option>`).join('');}
    catch(e){setStatus('evidenceStatus',e.message,'error');}
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
  async function refreshEvidence(){const area=$('evidenceArea').value;if(!area){$('evTotal').textContent=$('evProcessed').textContent=$('evAbstract').textContent=$('evRemaining').textContent='—';$('evidenceCards').innerHTML='<div class="empty">Choose an area first.</div>';return;}setStatus('evidenceStatus','Loading Evidence Lab status…');try{const d=await api('/api/review/evidence/status?area='+encodeURIComponent(area));$('evTotal').textContent=d.area.total;$('evProcessed').textContent=d.processed;$('evAbstract').textContent=d.source_counts.abstract_available;$('evRemaining').textContent=d.remaining;$('evidenceCards').innerHTML=(d.cards||[]).length?(d.cards||[]).map(evidenceCardHtml).join(''):'<div class="empty">No Evidence Cards generated for this area yet.</div>';setStatus('evidenceStatus',`${d.processed} of ${d.area.total} studies processed. Abstract available: ${d.source_counts.abstract_available}; PMC-linked: ${d.source_counts.pmc_linked}; metadata only: ${d.source_counts.metadata_only}. Nothing is public.`, 'ok');}catch(e){setStatus('evidenceStatus',e.message,'error');}}
  async function processEvidence(){const area=$('evidenceArea').value;if(!area){setStatus('evidenceStatus','Choose a clinical area first.','error');return;}const btn=$('evidenceProcess');btn.disabled=true;setStatus('evidenceStatus','Extracting the next Evidence Card batch…');try{const d=await api('/api/review/evidence/process',{area,batch:Number($('evidenceBatch').value)||6});setStatus('evidenceStatus',`Processed ${d.processed_now||0} studies. ${d.remaining||0} remaining.`, 'ok');await refreshEvidence();}catch(e){setStatus('evidenceStatus',e.message,'error');}finally{btn.disabled=false;}}

  function pmidLinks(pmids){return (pmids||[]).map(p=>`<a href="https://pubmed.ncbi.nlm.nih.gov/${encodeURIComponent(p)}/" target="_blank" rel="noopener">PMID ${esc(p)}</a>`).join(', ');}
  function synthesisHtml(s){
    if(!s)return '<div class="empty">No synthesis generated for this area yet.</div>';
    const items=(arr,field)=>Array.isArray(arr)&&arr.length?'<ul>'+arr.map(x=>typeof x==='string'?`<li>${esc(x)}</li>`:`<li>${esc(x[field]||'')}${x.pmids?.length?` <span class="small">(${pmidLinks(x.pmids)})</span>`:''}</li>`).join('')+'</ul>':'<p class="small">No specific items identified.</p>';
    const processed=Number(s.cards_processed??s.cards_analyzed??0),included=Number(s.cards_analyzed??0),excluded=Number(s.cards_excluded??Math.max(0,processed-included)),sent=Number(s.cards_sent_to_model??included);
    const profile=s.evidence_profile||{};
    const profileRows=[['Clinical trials',profile.clinical_trial],['Observational',profile.observational],['Systematic reviews / meta-analyses',profile.systematic_review_meta_analysis],['Narrative reviews',profile.narrative_review],['Preclinical animal',profile.preclinical_animal],['Mechanistic human',profile.mechanistic_human],['Mechanistic preclinical',profile.mechanistic_preclinical],['Case reports / series',profile.case_report_series],['Protocols',profile.protocol],['Other',profile.other]].filter(x=>Number(x[1]||0)>0);
    const profileHtml=profileRows.length?'<ul>'+profileRows.map(([k,v])=>`<li>${esc(k)}: <strong>${Number(v||0)}</strong></li>`).join('')+'</ul>':'<p class="small">Evidence profile unavailable for this saved synthesis. Regenerate it to add the audit profile.</p>';
    const excludedHtml=Array.isArray(s.excluded_cards)&&s.excluded_cards.length?'<ul>'+s.excluded_cards.map(x=>`<li><a href="https://pubmed.ncbi.nlm.nih.gov/${encodeURIComponent(x.pmid)}/" target="_blank" rel="noopener">PMID ${esc(x.pmid)}</a>${x.title?` — ${esc(x.title)}`:''}<br><span class="small">Reason: ${esc(x.reason||'non-evaluable')}</span></li>`).join('')+'</ul>':'<p class="small">No excluded cards.</p>';
    return `<article class="study-card"><div class="study-meta">Generated ${esc(s.generated_at||'')} · ${processed} processed · ${included} included · ${excluded} excluded · ${sent} sent to synthesis model · consistency: ${esc(s.evidence_consistency||'not assessed')}</div><h3>Evidence profile</h3>${profileHtml}<h3>Excluded from synthesis</h3>${excludedHtml}<h3>Overall interpretation</h3><p>${esc(s.overall_interpretation||'Not available.')}</p><h3>Human clinical evidence</h3><p>${esc(s.human_clinical||'Insufficient evidence in the processed cards.')}</p><h3>Reviews / meta-analyses</h3><p>${esc(s.reviews_meta_analyses||'Insufficient evidence in the processed cards.')}</p><h3>Preclinical & mechanistic evidence</h3><p>${esc(s.preclinical_mechanistic||'Insufficient evidence in the processed cards.')}</p><h3>Main findings</h3>${items(s.main_findings,'finding')}<h3>Conflicting evidence</h3>${items(s.conflicting_evidence,'issue')}<h3>Limitations</h3>${items(s.limitations)}<h3>Research gaps</h3>${items(s.research_gaps)}<h3>Provisional bottom line</h3><p><strong>${esc(s.bottom_line||'Not available.')}</strong></p><p class="small">Private provisional synthesis. Not a formal GRADE assessment and not published to the public website.</p></article>`;
  }
  async function loadEvidenceSynthesis(){const area=$('evidenceArea').value;if(!area){setStatus('synthesisStatus','Choose a clinical area first.','error');return;}setStatus('synthesisStatus','Loading saved synthesis…');try{const d=await api('/api/review/evidence/synthesis?area='+encodeURIComponent(area));$('evidenceSynthesis').innerHTML=synthesisHtml(d.synthesis);setStatus('synthesisStatus',d.synthesis?`Saved synthesis loaded: ${d.synthesis.cards_processed??d.synthesis.cards_analyzed} processed · ${d.synthesis.cards_analyzed} included · ${d.synthesis.cards_excluded??0} excluded.`:'No saved synthesis for this area yet.',d.synthesis?'ok':'');}catch(e){setStatus('synthesisStatus',e.message,'error');}}
  async function generateEvidenceSynthesis(){const area=$('evidenceArea').value;if(!area){setStatus('synthesisStatus','Choose a clinical area first.','error');return;}const btn=$('evidenceSynthesize');btn.disabled=true;setStatus('synthesisStatus','Generating a provisional synthesis from cached Evidence Cards…');try{const d=await api('/api/review/evidence/synthesize',{area});$('evidenceSynthesis').innerHTML=synthesisHtml(d.synthesis);setStatus('synthesisStatus',`Provisional synthesis: ${d.synthesis.cards_processed??d.synthesis.cards_analyzed} processed · ${d.synthesis.cards_analyzed} included · ${d.synthesis.cards_excluded??0} excluded. Nothing has been published.`, 'ok');}catch(e){setStatus('synthesisStatus',e.message,'error');}finally{btn.disabled=false;}}

  document.querySelectorAll('.review-step').forEach(b=>b.addEventListener('click',()=>showStep(b.dataset.step)));
  $('generateProtocol').addEventListener('click',generateProtocol);
  $('freezeProtocol').addEventListener('click',freezeProtocol); $('unfreezeProtocol').addEventListener('click',unfreezeProtocol); $('saveProtocol').addEventListener('click',saveProtocol);
  $('searchPubmed').addEventListener('click',searchPubmed); $('clearCandidates').addEventListener('click',()=>{if(confirm('Clear all candidate studies and screening decisions?')){project.candidates=[];project.extraction={};project.meta=null;saveProject();renderStudies();}});
  $('saveExtraction').addEventListener('click',saveExtraction); $('runMeta').addEventListener('click',runMetaAnalysis); $('generateDraft').addEventListener('click',generateDraft);
  $('exportJson').addEventListener('click',exportJson); $('exportCsv').addEventListener('click',exportCsv);
  $('copyDraft').addEventListener('click',async()=>{await navigator.clipboard.writeText(project.draft||'');setStatus('draftStatus','Draft copied to clipboard.','ok');});
  $('newProject').addEventListener('click',()=>{if(confirm('Start a new project? Export the current project first if needed.')){project=blankProject();saveProject();bindProjectToForm();renderStudies();showStep('question');setStatus('questionStatus','New project ready.');}});
  $('importJson').addEventListener('change',async e=>{const f=e.target.files?.[0];if(!f)return;try{const p=JSON.parse(await f.text());if(!p||p.version!==1)throw new Error('Unsupported project file.');project=p;saveProject();bindProjectToForm();renderStudies();showStep('question');setStatus('questionStatus','Project imported.','ok');}catch(err){setStatus('questionStatus',err.message,'error');}e.target.value='';});

  $('evidenceArea').addEventListener('change',()=>{refreshEvidence();loadEvidenceSynthesis();}); $('evidenceRefresh').addEventListener('click',refreshEvidence); $('evidenceProcess').addEventListener('click',processEvidence); $('evidenceSynthesize').addEventListener('click',generateEvidenceSynthesis); $('evidenceLoadSynthesis').addEventListener('click',loadEvidenceSynthesis);

  bindProjectToForm(); renderStudies(); renderMeta(); loadEvidenceAreas();
})();
