const SUPABASE_URL = "https://kfctugbpwmjdupmtfjen.supabase.co";
const SUPABASE_PUBLISHABLE_KEY = "sb_publishable_fz-WHqnfABeqFiTjBz8Utg_psM2G6sY";
const SESSION_MAX_AGE = 60 * 60 * 24 * 7; // 7 giorni

function parseCookies(request) {
  const raw = request.headers.get("Cookie") || "";
  const out = {};
  for (const part of raw.split(";")) {
    const i = part.indexOf("=");
    if (i > 0) {
      const k = part.slice(0, i).trim();
      const v = part.slice(i + 1).trim();
      try { out[k] = decodeURIComponent(v); } catch { out[k] = v; }
    }
  }
  return out;
}

function b64urlEncodeBytes(bytes) {
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function b64urlDecodeBytes(value) {
  const pad = "=".repeat((4 - (value.length % 4)) % 4);
  const base64 = value.replace(/-/g, "+").replace(/_/g, "/") + pad;
  const raw = atob(base64);
  return Uint8Array.from(raw, c => c.charCodeAt(0));
}

function b64urlEncodeText(text) {
  return b64urlEncodeBytes(new TextEncoder().encode(text));
}

function b64urlDecodeText(value) {
  return new TextDecoder().decode(b64urlDecodeBytes(value));
}

async function hmacKey(secret) {
  return crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign", "verify"]
  );
}

async function signSession(payload, secret) {
  const body = b64urlEncodeText(JSON.stringify(payload));
  const key = await hmacKey(secret);
  const sig = new Uint8Array(
    await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(body))
  );
  return `${body}.${b64urlEncodeBytes(sig)}`;
}

async function verifySession(token, secret) {
  if (!token || !secret) return null;
  const parts = token.split(".");
  if (parts.length !== 2) return null;

  const [body, sigText] = parts;
  let payload;
  try {
    payload = JSON.parse(b64urlDecodeText(body));
  } catch {
    return null;
  }

  if (!payload?.sub || !payload?.exp) return null;
  if (payload.exp <= Math.floor(Date.now() / 1000)) return null;

  try {
    const key = await hmacKey(secret);
    const ok = await crypto.subtle.verify(
      "HMAC",
      key,
      b64urlDecodeBytes(sigText),
      new TextEncoder().encode(body)
    );
    return ok ? payload : null;
  } catch {
    return null;
  }
}

function sessionCookie(value, maxAge = SESSION_MAX_AGE) {
  return `kr_session=${encodeURIComponent(value)}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${maxAge}`;
}

function clearCookie(name) {
  return `${name}=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0`;
}

function redirectToLogin(request, reason = "login") {
  const u = new URL("/library-access", request.url);
  u.searchParams.set("reason", reason);
  return Response.redirect(u.toString(), 302);
}

async function validateSupabaseLogin(accessToken) {
  if (!accessToken) return null;

  const r = await fetch(`${SUPABASE_URL}/auth/v1/user`, {
    headers: {
      "apikey": SUPABASE_PUBLISHABLE_KEY,
      "Authorization": `Bearer ${accessToken}`
    }
  });

  if (!r.ok) return null;
  return r.json();
}

async function fetchProfile(accessToken, userId) {
  const r = await fetch(
    `${SUPABASE_URL}/rest/v1/library_profiles?user_id=eq.${encodeURIComponent(userId)}&select=first_name,last_name,email&limit=1`,
    {
      headers: {
        "apikey": SUPABASE_PUBLISHABLE_KEY,
        "Authorization": `Bearer ${accessToken}`,
        "Accept": "application/json"
      }
    }
  );

  if (!r.ok) return null;
  const rows = await r.json();
  return Array.isArray(rows) && rows.length ? rows[0] : null;
}

function isAdminSession(session, env) {
  if (!session?.email || !env.ADMIN_EMAIL) return false;
  return session.email.trim().toLowerCase() === env.ADMIN_EMAIL.trim().toLowerCase();
}

function adminPageHtml() {
  return `<!doctype html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="robots" content="noindex,nofollow,noarchive">
  <title>Amministrazione Library — Ketogenic Research</title>
  <style>
    :root{font-family:Arial,Helvetica,sans-serif;color:#0b2d3b;background:#f5f9fb}
    *{box-sizing:border-box}
    body{margin:0}
    .wrap{max-width:760px;margin:70px auto;padding:24px}
    .card{background:#fff;border:1px solid #d8e5ea;border-radius:16px;padding:32px;box-shadow:0 10px 30px rgba(11,45,59,.08)}
    h1{margin:0 0 12px;font-size:28px}
    p{line-height:1.55;color:#49636e}
    .btn{display:inline-block;margin-top:18px;padding:14px 22px;border-radius:10px;background:#0f6b7a;color:#fff;text-decoration:none;font-weight:700}
    .back{display:inline-block;margin-top:22px;color:#0f6b7a;text-decoration:none}
  </style>
</head>
<body>
  <main class="wrap">
    <section class="card">
      <h1>Amministrazione Scientific Library</h1>
      <p>Esporta in Excel tutti gli utenti registrati presenti in <code>library_profiles</code>.</p>
      <a class="btn" href="/admin/export-users">Esporta utenti in Excel</a><br>
      <a class="back" href="/library">← Torna alla Library</a>
    </section>
  </main>
</body>
</html>`;
}

async function exportUsersXlsx(env) {
  if (!env.ADMIN_EXPORT_SECRET) {
    return new Response("ADMIN_EXPORT_SECRET non configurato su Cloudflare.", {
      status: 500,
      headers: { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store" }
    });
  }

  const upstream = await fetch(`${SUPABASE_URL}/functions/v1/export-library-users`, {
    method: "GET",
    headers: {
      "x-admin-export-secret": env.ADMIN_EXPORT_SECRET,
      "Accept": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    }
  });

  if (!upstream.ok) {
    const detail = await upstream.text().catch(() => "");
    return new Response(
      `Export non riuscito (${upstream.status}).${detail ? `\n${detail}` : ""}`,
      {
        status: 502,
        headers: { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store" }
      }
    );
  }

  const headers = new Headers();
  headers.set(
    "Content-Type",
    upstream.headers.get("Content-Type") ||
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
  );
  headers.set(
    "Content-Disposition",
    upstream.headers.get("Content-Disposition") ||
      'attachment; filename="ketogenic-research-utenti.xlsx"'
  );
  headers.set("Cache-Control", "private, no-store");
  headers.set("X-Robots-Tag", "noindex, noarchive, nofollow");

  return new Response(upstream.body, { status: 200, headers });
}


function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "private, no-store",
      "X-Robots-Tag": "noindex, noarchive, nofollow"
    }
  });
}

async function requireReviewAdmin(request, env) {
  const cookies = parseCookies(request);
  const session = await verifySession(cookies.kr_session || "", env.SESSION_SECRET);
  if (!session) return { ok:false, response:redirectToLogin(request,"login") };
  if (!isAdminSession(session, env)) return { ok:false, response:jsonResponse({error:"Administrator access required."},403) };
  return { ok:true, session };
}

function extractJsonObject(text) {
  let raw = String(text || "").trim();
  if (!raw) throw new Error("The model returned an empty response.");
  // Tolerate Markdown fences and harmless prose around a JSON object.
  raw = raw.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/i, "").trim();
  try { return JSON.parse(raw); } catch {}
  const first = raw.indexOf("{");
  const last = raw.lastIndexOf("}");
  if (first >= 0 && last > first) {
    const candidate = raw.slice(first, last + 1);
    try { return JSON.parse(candidate); } catch {}
  }
  throw new Error("The model did not return valid JSON.");
}

async function groqJson(env, messages) {
  if (!env.GROQ_API_KEY) throw new Error("GROQ_API_KEY is not configured in Cloudflare.");
  const r = await fetch("https://api.groq.com/openai/v1/chat/completions", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${env.GROQ_API_KEY}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      model: env.GROQ_MODEL || "openai/gpt-oss-120b",
      temperature: 0.1,
      messages
    })
  });
  if (!r.ok) throw new Error(`AI service error (${r.status}).`);
  const data = await r.json();
  return extractJsonObject(data?.choices?.[0]?.message?.content || "");
}

async function groqJsonLimited(env, messages, maxCompletionTokens=1100) {
  if (!env.GROQ_API_KEY) throw new Error("GROQ_API_KEY is not configured in Cloudflare.");
  const endpoint="https://api.groq.com/openai/v1/chat/completions";
  const model=env.GROQ_MODEL || "openai/gpt-oss-120b";
  const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  let lastError=null, jsonRepairUsed=false;
  // Provider-aware loop: 429 is transient and is retried using Retry-After/provider text.
  // JSON repair is attempted at most once so a malformed answer cannot create an endless loop.
  for(let attempt=0; attempt<5; attempt++){
    const attemptMessages=jsonRepairUsed ? [...messages,{role:"system",content:"REPAIR: Return exactly one complete valid JSON object matching the requested keys. No Markdown, commentary or trailing text."}] : messages;
    let r;
    try{
      r=await fetch(endpoint,{method:"POST",headers:{"Authorization":`Bearer ${env.GROQ_API_KEY}`,"Content-Type":"application/json"},body:JSON.stringify({model,temperature:0.1,max_completion_tokens:maxCompletionTokens,reasoning_effort:"low",response_format:{type:"json_object"},messages:attemptMessages})});
    }catch(e){lastError=new Error(`AI synthesis network error: ${e?.message||"request failed"}`); if(attempt<4){await sleep(1200*(attempt+1));continue;} break;}
    if(!r.ok){
      let detail=""; try{const j=await r.json();detail=String(j?.error?.message||j?.message||"");}catch{try{detail=await r.text();}catch{}}
      const failedGeneration=/failed_generation|failed to generate/i.test(detail);
      if(r.status===429 && !failedGeneration){
        const h=Number(r.headers.get("retry-after"));
        const m=detail.match(/try again in\s*([0-9.]+)s/i);
        const waitMs=Math.min(20000,Math.max(1500,Math.ceil(((Number.isFinite(h)&&h>0?h:(m?Number(m[1]):2))+0.8)*1000)));
        lastError=new Error(`AI synthesis rate limit (429); retrying after ${Math.ceil(waitMs/1000)}s.`);
        if(attempt<4){await sleep(waitMs);continue;}
      }
      if(failedGeneration || ((r.status===400||r.status===422)&&/response_format|json/i.test(detail))){
        // Compatibility fallback for providers/models that reject JSON mode.
        r=await fetch(endpoint,{method:"POST",headers:{"Authorization":`Bearer ${env.GROQ_API_KEY}`,"Content-Type":"application/json"},body:JSON.stringify({model,temperature:0.1,max_completion_tokens:maxCompletionTokens,reasoning_effort:"low",messages:attemptMessages})});
        if(r.ok){const data=await r.json();try{return extractJsonObject(data?.choices?.[0]?.message?.content||"");}catch(e){lastError=e;if(!jsonRepairUsed){jsonRepairUsed=true;continue;}}}
      }
      lastError=new Error(`AI synthesis service error (${r.status})${detail?`: ${detail.slice(0,700)}`:""}`);
      if([401,403,413].includes(r.status)) throw lastError;
      if(attempt<4){await sleep(1000*(attempt+1));continue;}
      break;
    }
    const data=await r.json();
    try{return extractJsonObject(data?.choices?.[0]?.message?.content||"");}
    catch(e){lastError=e;if(!jsonRepairUsed){jsonRepairUsed=true;continue;}break;}
  }
  throw new Error(`AI synthesis failed after controlled retries: ${lastError?.message||"invalid response"}`);
}

async function groqTextLimited(env, messages, maxCompletionTokens=650) {
  if (!env.GROQ_API_KEY) throw new Error("GROQ_API_KEY is not configured in Cloudflare.");
  const endpoint="https://api.groq.com/openai/v1/chat/completions";
  const model=env.GROQ_MODEL || "openai/gpt-oss-120b";
  const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  let lastError=null;
  for(let attempt=0;attempt<5;attempt++){
    let r;
    try{r=await fetch(endpoint,{method:"POST",headers:{"Authorization":`Bearer ${env.GROQ_API_KEY}`,"Content-Type":"application/json"},body:JSON.stringify({model,temperature:0.1,max_completion_tokens:maxCompletionTokens,reasoning_effort:"low",messages})});}
    catch(e){lastError=new Error(`AI synthesis network error: ${e?.message||"request failed"}`);if(attempt<4){await sleep(1200*(attempt+1));continue;}break;}
    if(!r.ok){
      let detail="";try{const j=await r.json();detail=String(j?.error?.message||j?.message||"");}catch{try{detail=await r.text();}catch{}}
      const failedGeneration=/failed_generation|failed to generate/i.test(detail);
      if(r.status===429 && !failedGeneration){
        const h=Number(r.headers.get("retry-after")),m=detail.match(/try again in\s*([0-9.]+)s/i);
        const waitMs=Math.min(20000,Math.max(1500,Math.ceil(((Number.isFinite(h)&&h>0?h:(m?Number(m[1]):2))+0.8)*1000)));
        lastError=new Error(`AI synthesis rate limit (429); retrying after ${Math.ceil(waitMs/1000)}s.`);if(attempt<4){await sleep(waitMs);continue;}
      }
      lastError=new Error(`AI synthesis service error (${r.status})${detail?`: ${detail.slice(0,700)}`:""}`);
      if(failedGeneration || [400,401,403,413,422].includes(r.status)) throw lastError;
      if(attempt<4){await sleep(1000*(attempt+1));continue;}break;
    }
    const data=await r.json();const out=String(data?.choices?.[0]?.message?.content||"").trim();if(out)return out;
    lastError=new Error("AI synthesis returned an empty response.");
  }
  throw new Error(`AI synthesis failed after controlled retries: ${lastError?.message||"invalid response"}`);
}

async function groqText(env, messages) {
  if (!env.GROQ_API_KEY) throw new Error("GROQ_API_KEY is not configured in Cloudflare.");
  const r = await fetch("https://api.groq.com/openai/v1/chat/completions", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${env.GROQ_API_KEY}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      model: env.GROQ_MODEL || "openai/gpt-oss-120b",
      temperature: 0.15,
      messages
    })
  });
  if (!r.ok) throw new Error(`AI service error (${r.status}).`);
  const data = await r.json();
  return String(data?.choices?.[0]?.message?.content || "").trim();
}

async function handleProtocolApi(request, env) {
  const body = await request.json().catch(() => ({}));
  const question = String(body.question || "").trim();
  const language = String(body.language || "English").trim();
  if (!question) return jsonResponse({ error: "Research question is required." }, 400);
  const system = `You are a systematic-review methodologist. Convert a research question into a conservative, auditable protocol draft. Do not invent study results. Return ONLY a JSON object with these exact keys: title, review_type, population, intervention, comparator, outcomes, primary_outcome, study_designs, inclusion_criteria, exclusion_criteria, subgroups, pubmed_query. Arrays are allowed for all fields except title, review_type, primary_outcome and pubmed_query. The PubMed query must be syntactically usable and should balance sensitivity and specificity. Use ${language}. If the question does not support a field, keep it broad and explicitly mark it for investigator confirmation.`;
  const protocol = await groqJson(env, [{ role: "system", content: system }, { role: "user", content: question }]);
  return jsonResponse({ protocol });
}

async function handlePubmedApi(request, env) {
  const body = await request.json().catch(() => ({}));
  const query = String(body.query || "").trim();
  const retmax = Math.max(1, Math.min(200, Number(body.retmax) || 100));
  if (!query) return jsonResponse({ error: "PubMed query is required." }, 400);
  const common = new URLSearchParams({ db: "pubmed", term: query, retmode: "json", retmax: String(retmax), sort: "relevance" });
  if (env.NCBI_API_KEY) common.set("api_key", env.NCBI_API_KEY);
  const search = await fetch(`https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?${common.toString()}`, { headers: { "User-Agent": "KetogenicResearchHub-ReviewStudio/1.0 (info@ketogenicresearch.org)" } });
  if (!search.ok) throw new Error(`PubMed search failed (${search.status}).`);
  const sj = await search.json();
  const ids = sj?.esearchresult?.idlist || [];
  if (!ids.length) return jsonResponse({ count: 0, studies: [] });
  const summaryParams = new URLSearchParams({ db: "pubmed", id: ids.join(","), retmode: "json" });
  if (env.NCBI_API_KEY) summaryParams.set("api_key", env.NCBI_API_KEY);
  const sum = await fetch(`https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?${summaryParams.toString()}`, { headers: { "User-Agent": "KetogenicResearchHub-ReviewStudio/1.0 (info@ketogenicresearch.org)" } });
  if (!sum.ok) throw new Error(`PubMed summary failed (${sum.status}).`);
  const j = await sum.json();
  const studies = ids.map(id => {
    const s = j?.result?.[id] || {};
    return {
      pmid: String(id),
      title: s.title || "",
      journal: s.fulljournalname || s.source || "",
      pubdate: s.pubdate || "",
      authors: Array.isArray(s.authors) ? s.authors.map(a => a.name).filter(Boolean) : [],
      doi: Array.isArray(s.articleids) ? (s.articleids.find(a => a.idtype === "doi")?.value || "") : ""
    };
  });
  return jsonResponse({ count: Number(sj?.esearchresult?.count || studies.length), returned: studies.length, studies });
}

async function handleDraftApi(request, env) {
  const body = await request.json().catch(() => ({}));
  if (!body.protocol?.frozen) return jsonResponse({ error: "Protocol must be frozen before drafting." }, 400);
  if (!body.meta?.k || body.meta.k < 2) return jsonResponse({ error: "A validated meta-analysis is required before drafting." }, 400);
  const packet = JSON.stringify({
    question: body.question,
    protocol: body.protocol,
    studies: body.studies,
    extraction: body.extraction,
    meta: body.meta
  });
  if (packet.length > 120000) return jsonResponse({ error: "Project packet is too large for the draft endpoint." }, 413);
  const language = String(body.language || "English");
  const system = `You are drafting a systematic review from a LOCKED evidence packet supplied by the investigator. Use only the supplied packet. Do not add external studies, numbers, citations, mechanisms or conclusions. Distinguish observed results from interpretation. If information is missing, state that it was not supplied. Write in ${language}. Produce these sections: Title, Structured abstract, Introduction, Methods, Results, Discussion, Limitations, Conclusion. In Methods explicitly state that final eligibility and quantitative extraction were investigator-validated. In Results report the supplied meta-analysis values exactly. Do not claim PRISMA compliance unless the packet establishes all required elements.`;
  const draft = await groqText(env, [{ role: "system", content: system }, { role: "user", content: packet }]);
  return jsonResponse({ draft });
}


const EVIDENCE_LAB_STATE_PREFIX = "evidence-lab:v2:state:";
const EVIDENCE_LAB_CARD_PREFIX = "evidence-lab:v2:card:";
const EVIDENCE_LAB_SCHEMA_VERSION = 2;

function evidenceLabSlug(v){ return String(v||"").toLowerCase().replace(/[^a-z0-9-]/g,"").slice(0,100); }
async function evidenceLabIndex(request,env){
  const idx=await assetJson(request,env,"_evidence-lab-index.json");
  return idx && Array.isArray(idx.areas) ? idx : {generated_at:null,areas:[]};
}
async function evidenceLabState(env,slug){
  return (await env.SITE_ADMIN.get(EVIDENCE_LAB_STATE_PREFIX+slug,"json")) || {processed:[],failed:[],updated_at:null};
}
async function handleEvidenceAreas(request,env){
  const idx=await evidenceLabIndex(request,env);
  const areas=[];
  for(const a of idx.areas){ const st=await evidenceLabState(env,a.slug); areas.push({slug:a.slug,label:a.label,total:a.count,processed:(st.processed||[]).length,failed:(st.failed||[]).length,updated_at:st.updated_at}); }
  return jsonResponse({generated_at:idx.generated_at,areas});
}
async function handleEvidenceStatus(request,env){
  const url=new URL(request.url), slug=evidenceLabSlug(url.searchParams.get("area"));
  const idx=await evidenceLabIndex(request,env), area=idx.areas.find(a=>a.slug===slug); if(!area)return jsonResponse({error:"Clinical area not found."},404);
  const st=await evidenceLabState(env,slug), processed=new Set(st.processed||[]);
  const sample=[]; for(const pmid of [...processed].slice(-12).reverse()){const c=await env.SITE_ADMIN.get(EVIDENCE_LAB_CARD_PREFIX+slug+":"+pmid,"json");if(c)sample.push(c);}
  const withAbstract=area.studies.filter(x=>x.has_abstract).length, withPmc=area.studies.filter(x=>x.pmcid).length;
  return jsonResponse({area:{slug,label:area.label,total:area.count},processed:processed.size,remaining:Math.max(0,area.count-processed.size),failed:(st.failed||[]).length,source_counts:{pmc_linked:withPmc,abstract_available:withAbstract,metadata_only:area.count-withAbstract},updated_at:st.updated_at,cards:sample});
}
const EVIDENCE_LAB_SYNTHESIS_PREFIX = "evidence-lab:v2:synthesis:";

function compactEvidenceCard(c){
  return {pmid:c.pmid,title:c.title,publication_type:c.publication_type,study_design:c.study_design,evidence_domain:c.evidence_domain,study_purpose:c.study_purpose,population:c.population,sample_size:c.sample_size,sample_size_details:c.sample_size_details,intervention:c.intervention,comparator:c.comparator,duration:c.duration,primary_outcomes:c.primary_outcomes,effect_direction:c.effect_direction,statistical_significance:c.statistical_significance,randomized:c.randomized,controlled:c.controlled,review_studies_included:c.review_studies_included,review_participants:c.review_participants,pooled_effect:c.pooled_effect,heterogeneity:c.heterogeneity,risk_of_bias_or_certainty:c.risk_of_bias_or_certainty,animal_species:c.animal_species,animal_model:c.animal_model,mechanistic_targets:c.mechanistic_targets,main_result:c.main_result,limitations:c.limitations,source_level:c.source_level,extraction_confidence:c.extraction_confidence};
}
async function handleEvidenceSynthesisGet(request,env){
  const url=new URL(request.url), slug=evidenceLabSlug(url.searchParams.get("area"));
  if(!slug)return jsonResponse({error:"Clinical area is required."},400);
  const saved=await env.SITE_ADMIN.get(EVIDENCE_LAB_SYNTHESIS_PREFIX+slug,"json");
  return jsonResponse({synthesis:saved||null});
}
function evidenceRelevance(c,areaLabel){
  const norm=v=>String(v??"").toLowerCase().normalize("NFKD").replace(/[\u0300-\u036f]/g,"");
  const join=v=>Array.isArray(v)?v.map(x=>typeof x==="string"?x:JSON.stringify(x)).join(" "):String(v??"");
  const title=norm(c.title), intervention=norm(c.intervention), result=norm(c.main_result), population=norm(c.population), model=norm(c.animal_model), targets=norm(join(c.mechanistic_targets));
  const all=[title,intervention,result,population,model,targets,norm(c.study_design),norm(join(c.primary_outcomes))].join(" ");
  const keto=/(ketogenic|ketosis|ketone|beta[- ]?hydroxybutyrate|β[- ]?hydroxybutyrate|d[- ]?beta[- ]?hydroxybutyrate|hydroxybutyrate|\bbhb\b|medium[- ]?chain triglycer|\bmct\b|ketoflex|low[- ]?carbohydrate)/;
  const ketoIntervention=keto.test(intervention);
  const areaNorm=norm(areaLabel);
  const areaWords=areaNorm.split(/[^a-z0-9]+/).filter(x=>x.length>3 && !["disease","syndrome","disorder"].includes(x));
  const areaDirect=areaWords.length===0 || areaWords.some(w=>all.includes(w));
  const type=String(c.publication_type||"other");
  const human=["clinical_trial","observational","case_report_series","mechanistic_human"].includes(type);
  const preclinical=["preclinical_animal","mechanistic_preclinical"].includes(type);
  const review=["systematic_review_meta_analysis","narrative_review"].includes(type);

  // Disease-model evidence can be directly relevant even when the disease name is absent from
  // the abstract fields (common in toxin/cell models). These markers are deliberately narrow.
  let diseaseModelDirect=false;
  if(areaNorm.includes("parkinson")){
    diseaseModelDirect=/(mptp|6[- ]?ohda|6[- ]?hydroxydopamine|rotenone|dopaminergic|substantia nigra|striatal dopamine|synphilin|alpha[- ]?synuclein|α[- ]?synuclein)/.test(all);
  }
  const diseaseSpecific=areaDirect || diseaseModelDirect;

  // MCT-related metabolic substrates are supporting—not direct—evidence when tested in a
  // disease-specific model. They must never be promoted to human efficacy evidence by this rule.
  const metabolicSupport=/(octanoic acid|caprylic acid|c8\b|medium[- ]?chain fatty|pantethine)/.test(all);

  if(human && ketoIntervention && areaDirect) return {level:"direct",reason:"human evidence directly evaluating a ketogenic/ketone intervention in the selected clinical area"};
  if(review && areaDirect && keto.test(title+" "+result)){
    const focused=keto.test(title) && areaWords.some(w=>title.includes(w));
    return focused?{level:"direct",reason:"review directly focused on ketogenic/ketone evidence in the selected clinical area"}:{level:"contextual",reason:"review provides broader context in which ketogenic/ketone evidence is only one component"};
  }
  if(preclinical && diseaseSpecific && (ketoIntervention || keto.test(result+" "+targets+" "+title))) return {level:"supporting",reason:"ketone/ketogenic mechanism tested in a disease-specific preclinical or mechanistic model"};
  if(preclinical && diseaseSpecific && metabolicSupport) return {level:"supporting",reason:"ketogenic-metabolism/MCT-related substrate tested in a disease-specific model; supportive mechanistic evidence, not direct ketogenic-diet efficacy evidence"};
  if(!keto.test(all)) return {level:"exclude",reason:"no ketogenic/ketone-specific evidence in the extracted card and no disease-specific ketogenic-metabolism support signal"};
  if(diseaseSpecific && keto.test(all)) return {level:"supporting",reason:"ketogenic/ketone evidence supports disease-specific biological plausibility but is not direct clinical efficacy evidence"};
  return {level:"contextual",reason:"ketogenic/ketone evidence is present but is not directly focused on the selected clinical question"};
}
async function handleEvidenceSynthesize(request,env){
  if(!env.SITE_ADMIN)return jsonResponse({error:"Evidence Lab storage (SITE_ADMIN) is not configured."},503);
  if(!env.GROQ_API_KEY)return jsonResponse({error:"GROQ_API_KEY is not configured."},503);
  const body=await request.json().catch(()=>({})), slug=evidenceLabSlug(body.area);
  const idx=await evidenceLabIndex(request,env), area=idx.areas.find(a=>a.slug===slug);
  if(!area)return jsonResponse({error:"Clinical area not found."},404);
  const st=await evidenceLabState(env,slug), ids=(st.processed||[]).map(String);
  if(ids.length<12)return jsonResponse({error:`At least 12 Evidence Cards are required for a provisional synthesis. Currently available: ${ids.length}.`},400);

  const raw=[];
  for(const pmid of ids.slice(-500)){
    const c=await env.SITE_ADMIN.get(EVIDENCE_LAB_CARD_PREFIX+slug+":"+pmid,"json");
    if(c)raw.push(c);
  }
  if(raw.length<12)return jsonResponse({error:"Not enough readable Evidence Cards for synthesis."},400);

  const counts={clinical:0,review:0,preclinical:0,mechanistic:0,other:0,abstract:0,metadata:0};
  for(const c of raw){const d=String(c.evidence_domain||"other"); counts[d]=(counts[d]||0)+1; counts[c.source_level==="abstract"?"abstract":"metadata"]++;}
  const evidenceBearing=raw.filter(c=>c.source_level==="abstract" || c.source_level==="full_text");
  const excluded=raw.filter(c=>!(c.source_level==="abstract" || c.source_level==="full_text")).map(c=>({pmid:String(c.pmid||""),title:String(c.title||""),reason:"metadata-only / no evidence-bearing abstract or full text"}));
  if(evidenceBearing.length<8)return jsonResponse({error:`Only ${evidenceBearing.length} evidence-bearing cards are available; metadata-only records are excluded from synthesis.`},400);

  // Relevance is computed deterministically from the locked Evidence Card fields. It does not
  // require another model call and therefore cannot consume synthesis TPM or drift between runs.
  const relevance_profile={direct:0,supporting:0,contextual:0,exclude:0};
  const relevance_cards=[];
  for(const c of evidenceBearing){const rel=evidenceRelevance(c,area.label); relevance_profile[rel.level]++; relevance_cards.push({card:c,...rel});}
  for(const x of relevance_cards.filter(x=>x.level==="exclude")) excluded.push({pmid:String(x.card.pmid||""),title:String(x.card.title||""),reason:x.reason});
  const usable=relevance_cards.filter(x=>x.level!=="exclude");
  if(usable.length<8)return jsonResponse({error:`Only ${usable.length} relevant evidence-bearing cards remain after relevance screening.`},400);

  const evidence_profile={clinical_trial:0,observational:0,systematic_review_meta_analysis:0,narrative_review:0,preclinical_animal:0,mechanistic_human:0,mechanistic_preclinical:0,case_report_series:0,protocol:0,other:0};
  for(const x of usable){const k=String(x.card.publication_type||"other"); if(Object.prototype.hasOwnProperty.call(evidence_profile,k))evidence_profile[k]++; else evidence_profile.other++;}

  const clip=(v,n)=>String(v??"").replace(/\s+/g," ").trim().slice(0,n);
  const arr=(v,n=4,m=90)=>Array.isArray(v)?v.slice(0,n).map(x=>clip(typeof x==="string"?x:(x?.outcome||x?.name||JSON.stringify(x)),m)).filter(Boolean):[];
  const nano=usable.map(x=>{const c=x.card;return {
    p:String(c.pmid||""), rel:x.level,
    t:clip(c.publication_type||"other",24), d:clip(c.study_design||"",32), n:clip(c.sample_size||c.sample_size_details||"",22),
    pop:clip(c.population||"",48), i:clip(c.intervention||"",48), cmp:clip(c.comparator||"",32), dur:clip(c.duration||"",18),
    o:arr(c.primary_outcomes,2,38), dir:clip(c.effect_direction||"",12), sig:clip(c.statistical_significance||"",10),
    r:clip(c.main_result||c.pooled_effect||"",105), lim:clip(c.limitations||c.risk_of_bias_or_certainty||"",55)
  }});
  const profileLabels={clinical_trial:"clinical trials",observational:"observational studies",systematic_review_meta_analysis:"systematic reviews/meta-analyses",narrative_review:"narrative reviews",preclinical_animal:"preclinical animal studies",mechanistic_human:"mechanistic human studies",mechanistic_preclinical:"mechanistic preclinical studies",case_report_series:"case reports/series",protocol:"protocols",other:"other"};
  const exactProfile=Object.fromEntries(Object.entries(evidence_profile).map(([k,v])=>[profileLabels[k]||k,v]));
  const relevanceAudit=relevance_cards.map(x=>({pmid:String(x.card.pmid||""),title:String(x.card.title||""),level:x.level,reason:x.reason}));
  // Hierarchical synthesis: bounded chunks, persisted checkpoints, then a compact final pass.
  // This keeps every included card represented without exceeding a single-request TPM envelope.
  const chunkSize=10;
  const chunks=[]; for(let i=0;i<nano.length;i+=chunkSize) chunks.push(nano.slice(i,i+chunkSize));
  const checkpointKey=`evidence-lab:v2:synthesis-checkpoint:${slug}:v13`;
  const corpusFingerprint=nano.map(x=>x.p).join(",")+"|"+JSON.stringify(exactProfile)+"|"+JSON.stringify(relevance_profile);
  let checkpoint=await env.SITE_ADMIN.get(checkpointKey,"json").catch(()=>null);
  if(!checkpoint || checkpoint.fingerprint!==corpusFingerprint) checkpoint={fingerprint:corpusFingerprint,chunks:{}};
  const chunkSystem=`Compress this chunk of structured Evidence Cards for a PRIVATE scientific synthesis. Use ONLY supplied cards. Preserve study type, relevance level, direction, conflicts, limitations and PMID traceability. direct may inform the selected clinical question; supporting is indirect/mechanistic and cannot establish clinical efficacy; contextual is background only. Do not infer missing facts. Return concise PLAIN TEXT, not JSON, with these exact headings: SUMMARY; HUMAN; REVIEWS; PRECLINICAL; FINDINGS; CONFLICTS; LIMITATIONS. Put PMIDs beside every evidence claim. Maximum 180 words. Be terse. Include only the strongest findings/conflicts and preserve PMID traceability.`;
  const chunkSummaries=[];
  let nextMissing=-1;
  for(let ci=0;ci<chunks.length;ci++){
    const cards=chunks[ci], key=String(ci), cs=checkpoint.chunks[key];
    if(!cs){nextMissing=ci;break;}
    chunkSummaries.push({chunk:ci+1,pmids:cards.map(x=>x.p),summary:cs});
  }
  // One HTTP request performs at most ONE AI chunk. This prevents browser/Worker timeouts.
  if(nextMissing>=0){
    const ci=nextMissing, cards=chunks[ci], key=String(ci);
    const packet=JSON.stringify({area:area.label,chunk:ci+1,total_chunks:chunks.length,evidence_cards:cards});
    let cs;
    try{cs=await groqTextLimited(env,[{role:"system",content:chunkSystem},{role:"user",content:packet}],320);}
    catch(e){return jsonResponse({error:`Evidence synthesis chunk ${ci+1}/${chunks.length} failed: ${e?.message||"AI service error"}`,progress:{phase:"chunks",completed:ci,total:chunks.length,cards_processed:raw.length,cards_usable:usable.length}},502);}
    checkpoint.chunks[key]=cs;
    try{await env.SITE_ADMIN.put(checkpointKey,JSON.stringify(checkpoint),{expirationTtl:86400});}
    catch(e){return jsonResponse({error:`Chunk ${ci+1} generated but checkpoint save failed: ${e?.message||"storage error"}`},500);}
    return jsonResponse({ok:true,done:false,progress:{phase:"chunks",completed:ci+1,total:chunks.length,cards_processed:raw.length,cards_usable:usable.length}});
  }
  // All chunk checkpoints exist. Rebuild their ordered summaries; this request performs only the final synthesis.
  for(let ci=0;ci<chunks.length;ci++){const cards=chunks[ci],cs=String(checkpoint.chunks[String(ci)]||"").replace(/\s+/g," ").trim();chunkSummaries.push({chunk:ci+1,pmids:cards.map(x=>x.p),summary:cs.slice(0,2400)});}
  const finalPacket=JSON.stringify({area:area.label,library_total:area.count,cards_processed:raw.length,cards_included:usable.length,cards_excluded:excluded.length,EXACT_EVIDENCE_PROFILE:exactProfile,EXACT_RELEVANCE_PROFILE:relevance_profile,all_included_pmids:nano.map(x=>x.p),chunk_summaries:chunkSummaries});
  if(finalPacket.length>22000)return jsonResponse({error:`Final synthesis packet remains too large (${finalPacket.length} characters) after bounded chunk compression. Checkpoints were preserved; no studies were dropped.`,diagnostic:{cards_processed:raw.length,cards_usable:usable.length,total_chunks:chunks.length,final_packet_chars:finalPacket.length}},413);
  const finalSystem=`You are producing a PRIVATE, PROVISIONAL scientific evidence synthesis from hierarchical summaries of structured Evidence Cards. Use ONLY the supplied packet. All included studies have already been represented in chunk_summaries. EXACT_EVIDENCE_PROFILE and EXACT_RELEVANCE_PROFILE are deterministic ground truth and MUST NOT be recalculated, merged or contradicted. direct may support conclusions for the selected clinical question; supporting may support plausibility but NOT establish clinical efficacy; contextual is background only and MUST NOT support efficacy/safety conclusions. Clinical trials and observational studies are separate. Reviews are not additional independent primary studies. Never present preclinical benefit as demonstrated clinical efficacy. Never infer causality from observational evidence. DO NOT write PMID numbers, bracketed numeric citations, or aggregate study counts in any prose field. Citation identifiers are supplied separately through the pmids arrays for main_findings/conflicting_evidence and will be validated and rendered by code. Do not state counts such as “seven trials” or “two observational studies”; the application inserts exact deterministic counts. This is NOT a formal GRADE assessment. Return ONLY valid JSON with keys: overall_interpretation (string), evidence_consistency (consistent|mostly_consistent|mixed|conflicting|insufficient), human_clinical (string), reviews_meta_analyses (string), preclinical_mechanistic (string), main_findings (array of {finding,pmids}), conflicting_evidence (array of {issue,pmids}), limitations (array of strings), research_gaps (array of strings), bottom_line (string).`;

  let out;
  try{out=await groqJsonLimited(env,[{role:"system",content:finalSystem},{role:"user",content:finalPacket}],1100);}
  catch(e){return jsonResponse({error:`Evidence synthesis final stage failed: ${e?.message||"AI service error"}. Chunk checkpoints were preserved; retry Generate synthesis to resume without repeating completed chunks.`,diagnostic:{cards_processed:raw.length,cards_usable:usable.length,cards_synthesized:nano.length,completed_chunks:chunks.length,final_packet_chars:finalPacket.length}},502);}

  // Deterministic citation validator. The model may only attach a PMID to a section whose
  // evidence class matches the locked Evidence Card. This prevents a review being cited as an
  // observational/animal study (and analogous cross-domain citation drift).
  const cardByPmid=new Map(usable.map(x=>[String(x.card.pmid||""),{card:x.card,rel:x.level}]));
  const allowed=new Set(cardByPmid.keys());
  const pubType=pmid=>String(cardByPmid.get(String(pmid))?.card?.publication_type||"other");
  const sectionAllows=(section,pmid)=>{
    const t=pubType(pmid);
    if(section==="human") return t==="clinical_trial"||t==="observational"||t==="mechanistic_human"||t==="case_report_series";
    if(section==="reviews") return t==="systematic_review_meta_analysis"||t==="narrative_review";
    if(section==="preclinical") return t==="preclinical_animal"||t==="mechanistic_preclinical";
    return allowed.has(String(pmid));
  };
  const citedPmids=text=>[...String(text||"").matchAll(/(?:PMID\s*)?(\d{7,9})/gi)].map(m=>m[1]).filter(x=>allowed.has(x));
  const sanitizeSection=(text,section)=>{
    const parts=String(text||"").split(/(?<=[.!?])\s+/);
    return parts.filter(sentence=>{const ps=citedPmids(sentence);return !ps.length||ps.every(p=>sectionAllows(section,p));}).join(" ").trim();
  };
  const classifyClaim=text=>{const q=String(text||"").toLowerCase();
    if(/animal|mouse|mice|rat|zebrafish|mptp|rotenone|6[- ]?ohda|in vitro|cell|dopaminergic neuron|preclinical/.test(q))return "preclinical";
    if(/systematic review|meta-analysis|meta analysis|narrative review|review/.test(q))return "reviews";
    if(/trial|rct|randomi|participant|patient|human|observational|cohort|voice handicap|updrs|nmss|cognitive|levodopa/.test(q))return "human";
    return "any";};
  const cleanPmids=(v,claim="")=>{const section=classifyClaim(claim);return Array.isArray(v)?v.map(String).filter(x=>allowed.has(x)&&(section==="any"||sectionAllows(section,x))).slice(0,12):[];};
  const citation_validation={removed_section_sentences:[],removed_claim_citations:[]};
  const validateSection=(value,section)=>{const before=String(value||"");const after=sanitizeSection(before,section);if(after!==before)citation_validation.removed_section_sentences.push(section);return after;};
  const mapClaims=(items,label)=> (Array.isArray(items)?items:[]).slice(0,label==="finding"?8:6).map(x=>{const txt=String(x?.[label]||"");const original=Array.isArray(x?.pmids)?x.pmids.map(String):[];const pmids=cleanPmids(original,txt);if(pmids.length!==original.filter(p=>allowed.has(p)).length)citation_validation.removed_claim_citations.push({type:label,text:txt.slice(0,140)});return {[label]:txt,pmids};}).filter(x=>x[label]);
  // Final scientific lock: prose cannot carry model-generated citation numbers or aggregate
  // study counts. Exact counts come from Evidence Cards; PMID arrays are validated separately.
  const stripModelCitations=(value)=>String(value||"")
    .replace(/\[\s*(?:PMID\s*)?\d{3,9}(?:\s*[,;]\s*(?:PMID\s*)?\d{3,9})*\s*\]/gi,"")
    .replace(/\((?:PMID\s*)?\d{7,9}(?:\s*[,;]\s*(?:PMID\s*)?\d{7,9})*\)/gi,"")
    .replace(/\bPMID\s*:?\s*\d{3,9}\b/gi,"")
    .replace(/【\s*\d{3,9}\s*】/g,"")
    .replace(/\s{2,}/g," ").trim();
  const humanPrefix=`Exact evidence profile: ${evidence_profile.clinical_trial} clinical trials; ${evidence_profile.observational} observational studies; ${evidence_profile.mechanistic_human} mechanistic human studies; ${evidence_profile.case_report_series} case reports/series.`;
  const reviewPrefix=`Exact evidence profile: ${evidence_profile.systematic_review_meta_analysis} systematic reviews/meta-analyses; ${evidence_profile.narrative_review} narrative reviews.`;
  const preclinicalPrefix=`Exact evidence profile: ${evidence_profile.preclinical_animal} preclinical animal studies; ${evidence_profile.mechanistic_preclinical} mechanistic preclinical studies.`;
  const lockedSection=(value,section,prefix)=>`${prefix} ${stripModelCitations(validateSection(value,section))}`.trim();
  const synthesis={schema_version:13,area_slug:slug,area_label:area.label,generated_at:new Date().toISOString(),library_total:area.count,cards_processed:raw.length,cards_analyzed:usable.length,cards_excluded:excluded.length,cards_sent_to_model:nano.length,cards_synthesized:nano.length,synthesis_chunks:chunks.length,excluded_cards:excluded,evidence_profile,relevance_profile,relevance_cards:relevanceAudit,counts,citation_validation,evidence_consistency:String(out?.evidence_consistency||"insufficient"),overall_interpretation:stripModelCitations(out?.overall_interpretation),human_clinical:lockedSection(out?.human_clinical,"human",humanPrefix),reviews_meta_analyses:lockedSection(out?.reviews_meta_analyses,"reviews",reviewPrefix),preclinical_mechanistic:lockedSection(out?.preclinical_mechanistic,"preclinical",preclinicalPrefix),main_findings:mapClaims(out?.main_findings,"finding").map(x=>({finding:stripModelCitations(x.finding),pmids:x.pmids})),conflicting_evidence:mapClaims(out?.conflicting_evidence,"issue").map(x=>({issue:stripModelCitations(x.issue),pmids:x.pmids})),limitations:(Array.isArray(out?.limitations)?out.limitations:[]).map(stripModelCitations).slice(0,8),research_gaps:(Array.isArray(out?.research_gaps)?out.research_gaps:[]).map(stripModelCitations).slice(0,8),bottom_line:stripModelCitations(out?.bottom_line)};
  try{await env.SITE_ADMIN.put(EVIDENCE_LAB_SYNTHESIS_PREFIX+slug,JSON.stringify(synthesis)); await env.SITE_ADMIN.delete(checkpointKey).catch(()=>{});}
  catch(e){return jsonResponse({error:`Synthesis generated but KV save failed: ${e?.message||"unknown storage error"}`},500);}
  return jsonResponse({ok:true,done:true,synthesis,progress:{phase:"complete",completed:chunks.length,total:chunks.length}});
}

async function handleEvidenceProcess(request,env){
  const body=await request.json().catch(()=>({}));
  const slug=evidenceLabSlug(body.area), batch=Math.max(1,Math.min(10,Number(body.batch)||6));
  if(!env.SITE_ADMIN)return jsonResponse({error:"Evidence Lab storage (SITE_ADMIN) is not configured."},503);
  const idx=await evidenceLabIndex(request,env), area=idx.areas.find(a=>a.slug===slug);
  if(!area)return jsonResponse({error:"Clinical area not found."},404);
  const st=await evidenceLabState(env,slug), done=new Set(st.processed||[]), failed=Array.isArray(st.failed)?st.failed:[];
  const todo=area.studies.filter(x=>!done.has(String(x.pmid))).slice(0,batch);
  if(!todo.length)return jsonResponse({ok:true,processed_now:0,processed:done.size,remaining:0,complete:true,warnings:[]});

  // PubMed is enrichment, not a single point of failure. Evidence Lab can still save a
  // metadata card if NCBI is temporarily unavailable and retry that PMID later.
  const abstracts={}, warnings=[];
  try{
    const ep=new URLSearchParams({db:"pubmed",id:todo.map(x=>x.pmid).join(","),retmode:"xml"});
    if(env.NCBI_API_KEY)ep.set("api_key",env.NCBI_API_KEY);
    const er=await fetch(`https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?${ep.toString()}`,{headers:{"User-Agent":"KetogenicResearchHub-EvidenceLab/1.1 (info@ketogenicresearch.org)"}});
    if(!er.ok) throw new Error(`PubMed HTTP ${er.status}`);
    const xml=await er.text();
    const clean=t=>String(t||"").replace(/<[^>]+>/g," ").replace(/&lt;/g,"<").replace(/&gt;/g,">").replace(/&amp;/g,"&").replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/\s+/g," ").trim();
    for(const part of xml.split(/<PubmedArticle>/i).slice(1)){
      const pm=part.match(/<PMID[^>]*>(\d+)<\/PMID>/i); if(!pm)continue;
      const abs=[...part.matchAll(/<AbstractText[^>]*>([\s\S]*?)<\/AbstractText>/gi)].map(m=>clean(m[1])).filter(Boolean).join(" ");
      if(abs)abstracts[pm[1]]=abs;
    }
  }catch(e){warnings.push(`PubMed enrichment unavailable: ${e?.message||e}`);}

  const now=new Date().toISOString();
  const fallback=src=>({schema_version:EVIDENCE_LAB_SCHEMA_VERSION,pmid:String(src.pmid),publication_type:"other",study_design:"not extracted",evidence_domain:"other",study_purpose:"other",population:"not reported",sample_size:null,sample_size_details:"not reported",intervention:"not reported",comparator:"not reported",duration:"not reported",primary_outcomes:[],secondary_outcomes:[],effect_direction:"not_reported",statistical_significance:"not_reported",randomized:"not_applicable",controlled:"not_applicable",time_orientation:"not_applicable",population_phenotype:"not reported",review_studies_included:null,review_participants:null,review_study_types:"not reported",pooled_effect:"not reported",heterogeneity:"not reported",risk_of_bias_or_certainty:"not reported",animal_species:"not applicable",animal_model:"not applicable",mechanistic_targets:[],main_result:"AI extraction pending",limitations:["not reported"],source_level:abstracts[src.pmid]?"abstract":"metadata",extraction_confidence:"low"});
  const extracted=new Map();

  // Keep each AI request deliberately small. Large multi-abstract calls were fragile on
  // Cloudflare/Groq and could make the whole request fail with a platform 500.
  const aiSystem=`You are an evidence-extraction engine for a scientific Evidence Lab. Use ONLY the supplied record. Do not infer facts that are not explicitly supported by the title/abstract. Return ONLY valid JSON as {"cards":[...]}, exactly one card per PMID.

COMMON FIELDS required for every card: schema_version (integer 2), pmid, publication_type, study_design, evidence_domain, study_purpose, population, sample_size, sample_size_details, intervention, comparator, duration, primary_outcomes (array), secondary_outcomes (array), effect_direction, statistical_significance, main_result, limitations (array), source_level, extraction_confidence.

Allowed publication_type: clinical_trial, observational, systematic_review_meta_analysis, narrative_review, preclinical_animal, mechanistic_human, mechanistic_preclinical, case_report_series, protocol, other. evidence_domain: clinical, preclinical, mechanistic, review, other. study_purpose: efficacy, safety, mechanism, association, diagnostic, feasibility, mixed, other. effect_direction: favorable, neutral, unfavorable, mixed, not_reported. statistical_significance: yes, no, mixed, not_reported. source_level: abstract or metadata. extraction_confidence: high, moderate, low.

CLINICAL TRIAL / OBSERVATIONAL fields: randomized (yes/no/not_reported/not_applicable), controlled (yes/no/not_reported/not_applicable), time_orientation (prospective/retrospective/cross_sectional/not_reported/not_applicable), population_phenotype.
SYSTEMATIC REVIEW / META-ANALYSIS fields: review_studies_included (number or null), review_participants (number or null), review_study_types, pooled_effect, heterogeneity, risk_of_bias_or_certainty. Do not treat a review as if it were a single trial.
PRECLINICAL fields: animal_species, animal_model, mechanistic_targets (array).
For fields not applicable to a publication type use "not applicable" or null/[] as appropriate. Never invent sample size, randomization, significance, effect estimates, limitations or certainty. If the abstract does not report something, use "not reported". Preserve whether evidence is human clinical versus animal/preclinical. main_result must be factual, concise, and must not turn association into causation.`
  if(env.GROQ_API_KEY){
    for(let i=0;i<todo.length;i+=2){
      const group=todo.slice(i,i+2);
      const packet=group.map(x=>({pmid:String(x.pmid),title:x.title,year:x.year,doi:x.doi,evidence_label:x.evidence,source:abstracts[x.pmid]?"PubMed abstract":"metadata only",abstract:String(abstracts[x.pmid]||"").slice(0,6500)}));
      try{
        const out=await groqJson(env,[{role:"system",content:aiSystem},{role:"user",content:JSON.stringify(packet)}]);
        for(const c of (Array.isArray(out?.cards)?out.cards:[])) if(c?.pmid) extracted.set(String(c.pmid),c);
      }catch(e){
        warnings.push(`AI batch retry for PMID ${group.map(x=>x.pmid).join(", ")}: ${e?.message||e}`);
        // Retry individually so one malformed/oversized record cannot block its neighbour.
        for(const x of group){
          const one={pmid:String(x.pmid),title:x.title,year:x.year,doi:x.doi,evidence_label:x.evidence,source:abstracts[x.pmid]?"PubMed abstract":"metadata only",abstract:String(abstracts[x.pmid]||"").slice(0,5000)};
          try{
            const retry=await groqJson(env,[{role:"system",content:aiSystem},{role:"user",content:JSON.stringify([one])}]);
            const card=Array.isArray(retry?.cards)?retry.cards.find(c=>String(c?.pmid)===String(x.pmid)):null;
            if(card) extracted.set(String(x.pmid),card); else warnings.push(`AI returned no card for PMID ${x.pmid}.`);
          }catch(re){warnings.push(`AI extraction failed for PMID ${x.pmid}: ${re?.message||re}`);}
        }
      }
    }
  }else warnings.push("GROQ_API_KEY is not configured; cards were saved for later AI extraction.");

  let processedNow=0;
  for(const src of todo){
    const pmid=String(src.pmid), c=extracted.get(pmid)||fallback(src);
    c.schema_version=EVIDENCE_LAB_SCHEMA_VERSION; c.pmid=pmid; c.title=src.title; c.doi=src.doi; c.year=src.year; c.area=slug; c.extracted_at=now;
    // Only mark genuinely AI-extracted cards as processed. Fallback cards stay retryable.
    try{
      await env.SITE_ADMIN.put(EVIDENCE_LAB_CARD_PREFIX+slug+":"+pmid,JSON.stringify(c));
      if(extracted.has(pmid)){done.add(pmid);processedNow++;}
    }catch(e){warnings.push(`Storage failed for PMID ${pmid}: ${e?.message||e}`);}
  }
  const next={processed:[...done],failed,updated_at:now};
  await env.SITE_ADMIN.put(EVIDENCE_LAB_STATE_PREFIX+slug,JSON.stringify(next));
  return jsonResponse({ok:true,processed_now:processedNow,attempted:todo.length,processed:done.size,remaining:Math.max(0,area.count-done.size),warnings});
}

const SITE_ADMIN_CONFIG_KEY = "site-admin:config:v1";
const SITE_ADMIN_PAGE_PREFIX = "site-admin:page:";

function safeSlug(v) { return String(v || "").toLowerCase().trim().replace(/[^a-z0-9-]+/g,"-").replace(/^-+|-+$/g,"").slice(0,80); }
function siteAdminJson(data,status=200){ return new Response(JSON.stringify(data),{status,headers:{"Content-Type":"application/json; charset=utf-8","Cache-Control":"no-store"}}); }
async function requireSiteAdmin(request, env) {
  const cookies=parseCookies(request);
  const session=await verifySession(cookies.kr_session || "", env.SESSION_SECRET);
  if(!session) return {ok:false,response:redirectToLogin(request,"login")};
  if(!isAdminSession(session,env)) return {ok:false,response:new Response("Accesso non autorizzato.",{status:403,headers:{"Cache-Control":"no-store"}})};
  return {ok:true,session};
}
async function getSiteAdminConfig(env){
  if(!env.SITE_ADMIN) throw new Error("SITE_ADMIN binding non configurato.");
  const saved=await env.SITE_ADMIN.get(SITE_ADMIN_CONFIG_KEY,"json");
  if(saved) return saved;
  return {menu:[]};
}

const SITE_ADMIN_CONTENT_PREFIX = "site-admin:content:";
const SITE_ADMIN_LIBRARY_EXCLUSIONS = "site-admin:library-exclusions:v1";
const SITE_ADMIN_EXTENDED_KEY = "site-admin:extended:v1";
const SITE_ADMIN_MEDIA_PREFIX = "site-admin:media:";
const SITE_ADMIN_HISTORY_PREFIX = "site-admin:history:";
function safeMediaId(v){return String(v||"").replace(/[^a-zA-Z0-9_-]/g,"").slice(0,90)}
async function getExtendedConfig(env){return (await env.SITE_ADMIN.get(SITE_ADMIN_EXTENDED_KEY,"json"))||{director_photo:"",clinical_icons:{},committee:{title:"Scientific Committee",intro:"",published:false,members:[]}}}
function cleanExtended(b){const c=b&&typeof b==="object"?b:{};const committee=c.committee&&typeof c.committee==="object"?c.committee:{};return {director_photo:String(c.director_photo||"").slice(0,500),clinical_icons:c.clinical_icons&&typeof c.clinical_icons==="object"?c.clinical_icons:{},committee:{title:String(committee.title||"Scientific Committee").slice(0,160),intro:String(committee.intro||"").slice(0,1200),published:!!committee.published,members:Array.isArray(committee.members)?committee.members.slice(0,100).map(m=>({name:String(m.name||"").slice(0,160),role:String(m.role||"").slice(0,200),affiliation:String(m.affiliation||"").slice(0,300),bio:String(m.bio||"").slice(0,3000),photo:String(m.photo||"").slice(0,500),cv:String(m.cv||"").slice(0,500),orcid:String(m.orcid||"").slice(0,300),linkedin:String(m.linkedin||"").slice(0,500)})):[]}}}
function committeeHtml(c){const e=x=>String(x||"").replace(/[&<>"]/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[ch]));const members=(c.members||[]).map(m=>`<article style="border:1px solid #dce5ef;border-radius:14px;padding:18px;margin:14px 0;display:grid;grid-template-columns:${m.photo?'120px ':''}1fr;gap:18px">${m.photo?`<img src="${e(m.photo)}" alt="${e(m.name)}" style="width:120px;height:140px;object-fit:cover;border-radius:10px">`:''}<div><h2 style="margin-top:0">${e(m.name)}</h2>${m.role?`<p><strong>${e(m.role)}</strong></p>`:''}${m.affiliation?`<p>${e(m.affiliation)}</p>`:''}${m.bio?`<p>${e(m.bio)}</p>`:''}<p>${m.orcid?`<a href="${e(m.orcid)}">ORCID</a> `:''}${m.linkedin?`<a href="${e(m.linkedin)}">LinkedIn</a> `:''}${m.cv?`<a href="${e(m.cv)}">Curriculum PDF</a>`:''}</p></div></article>`).join('');return `<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="index,follow"><title>${e(c.title)}</title></head><body style="margin:0;background:#f5f8fc;color:#17324d;font-family:Arial,Helvetica,sans-serif"><main style="max-width:980px;margin:40px auto;padding:24px"><p><a href="https://ketogenicresearch.org/">← Ketogenic Research Hub</a></p><h1>${e(c.title)}</h1>${c.intro?`<p style="font-size:1.1rem;line-height:1.6">${e(c.intro)}</p>`:''}${members}</main></body></html>`}

function safeContentPath(v){ const x=String(v||"").replace(/^\/+/,""); if(!/^(?:[a-zA-Z0-9._-]+\.html|articles\/[a-zA-Z0-9._-]+\.html)$/.test(x)) return ""; return x; }
async function assetText(request,env,path){ const u=new URL('/'+path.replace(/^\/+/,''),request.url); const r=await env.ASSETS.fetch(new Request(u.toString(),{method:'GET'})); if(!r.ok) return null; return r.text(); }
async function assetJson(request,env,path){ const t=await assetText(request,env,path); return t?JSON.parse(t):[]; }
async function contentState(env,path){ return env.SITE_ADMIN.get(SITE_ADMIN_CONTENT_PREFIX+path,'json'); }
async function excludedPmids(env){ return (await env.SITE_ADMIN.get(SITE_ADMIN_LIBRARY_EXCLUSIONS,'json')) || []; }
async function deletedArticlePaths(env){
  if(!env.SITE_ADMIN) return [];
  const out=[]; let cursor=undefined;
  do {
    const page=await env.SITE_ADMIN.list({prefix:SITE_ADMIN_CONTENT_PREFIX,cursor});
    for(const k of page.keys){
      const path=k.name.slice(SITE_ADMIN_CONTENT_PREFIX.length);
      if(!path.startsWith("articles/")) continue;
      const st=await env.SITE_ADMIN.get(k.name,"json");
      if(st?.deleted) out.push(path);
    }
    cursor=page.list_complete?undefined:page.cursor;
  } while(cursor);
  return out;
}
async function handlePublicContent(request,env,url){
  const path=safeContentPath(url.searchParams.get('path')); if(!path) return siteAdminJson({error:'Invalid path'},400);
  if(!env.SITE_ADMIN) return siteAdminJson({},404);
  const st=await contentState(env,path); const h={"Access-Control-Allow-Origin":"https://ketogenicresearch.org","Cache-Control":"no-store","Content-Type":"application/json; charset=utf-8"};
  if(!st) return new Response('{}',{status:404,headers:h});
  return new Response(JSON.stringify({deleted:!!st.deleted,html:st.deleted?'':String(st.html||'')}),{headers:h});
}
async function applyLibraryExclusions(response,env){
  if(!response.ok||!env.SITE_ADMIN) return response; const ids=(await excludedPmids(env)).filter(x=>/^\d+$/.test(String(x))).slice(0,1000); if(!ids.length)return response;
  let rw=new HTMLRewriter(); for(const id of ids) rw=rw.on(`article[data-pmid="${id}"]`,{element(e){e.remove();}}); return rw.transform(response);
}
async function applyClinicalIconOverrides(response,request,env){
  if(!response.ok||!env.SITE_ADMIN)return response;const cfg=await getExtendedConfig(env);const icons=cfg.clinical_icons||{};if(!Object.keys(icons).length)return response;let areas=[];try{const st=await assetJson(request,env,"_admin-status.json");areas=st.clinical_areas||[]}catch(e){}let rw=new HTMLRewriter();for(const a of areas){const src=icons[a.slug];if(!src)continue;const label=String(a.label||"").replaceAll('"','\\"');rw=rw.on(`span.kr-area-icon[data-icon-for="${label}"] img`,{element(e){e.setAttribute("src",src)}})}return rw.transform(response);
}

async function saveContentHistory(env,path,state){const stamp=new Date().toISOString();const id=stamp.replace(/[:.]/g,"-")+"-"+crypto.randomUUID().slice(0,6);await env.SITE_ADMIN.put(SITE_ADMIN_HISTORY_PREFIX+path+":"+id,JSON.stringify({id,path,saved_at:stamp,state:state||null}),{expirationTtl:60*60*24*90});}
async function handleSiteAdminApi(request,env,url){
  const auth=await requireSiteAdmin(request,env); if(!auth.ok) return auth.response;
  if(!env.SITE_ADMIN) return siteAdminJson({error:"SITE_ADMIN binding non configurato."},500);
  try {
    if(url.pathname==="/api/site-admin/manifests" && request.method==="GET") {
      const pages=await assetJson(request,env,"_admin-pages.json"), articles=await assetJson(request,env,"_admin-articles.json"), library=await assetJson(request,env,"_admin-library.json"), defaultMenu=await assetJson(request,env,"_admin-menu.json");
      for(const x of [...pages,...articles]){const st=await contentState(env,x.path);x.override=!!st;x.deleted=!!st?.deleted;}
      return siteAdminJson({pages,articles,library,defaultMenu});
    }
    if(url.pathname==="/api/site-admin/content") {
      if(request.method==="GET"){const path=safeContentPath(url.searchParams.get("path"));if(!path)return siteAdminJson({error:"Percorso non valido."},400);const original=url.searchParams.get("original")==="1";const st=await contentState(env,path);if(!original&&st?.deleted)return siteAdminJson({path,deleted:true,html:""});if(!original&&st?.html)return siteAdminJson({path,override:true,html:st.html});const html=await assetText(request,env,"_admin-source/"+path+".txt");return html===null?siteAdminJson({error:"Contenuto non trovato."},404):siteAdminJson({path,html,original:true});}
      const b=await request.json().catch(()=>({}));const path=safeContentPath(b.path);if(!path)return siteAdminJson({error:"Percorso non valido."},400);
      if(request.method==="PUT"){await saveContentHistory(env,path,await contentState(env,path));await env.SITE_ADMIN.put(SITE_ADMIN_CONTENT_PREFIX+path,JSON.stringify({html:String(b.html||""),deleted:false,updated_at:new Date().toISOString()}));return siteAdminJson({ok:true});}
      if(request.method==="POST"&&b.action==="delete"){await saveContentHistory(env,path,await contentState(env,path));await env.SITE_ADMIN.put(SITE_ADMIN_CONTENT_PREFIX+path,JSON.stringify({deleted:true,updated_at:new Date().toISOString()}));return siteAdminJson({ok:true});}
      if(request.method==="DELETE"|| (request.method==="POST"&&b.action==="restore")){await saveContentHistory(env,path,await contentState(env,path));await env.SITE_ADMIN.delete(SITE_ADMIN_CONTENT_PREFIX+path);return siteAdminJson({ok:true});}
    }
    if(url.pathname==="/api/site-admin/history") {const path=safeContentPath(url.searchParams.get("path"));if(!path)return siteAdminJson({error:"Percorso non valido."},400);const prefix=SITE_ADMIN_HISTORY_PREFIX+path+":";if(request.method==="GET"){const l=await env.SITE_ADMIN.list({prefix});const history=[];for(const k of l.keys){const h=await env.SITE_ADMIN.get(k.name,"json");if(h)history.push(h)}history.sort((a,b)=>String(b.saved_at).localeCompare(String(a.saved_at)));return siteAdminJson({history:history.slice(0,30)});}if(request.method==="POST"){const b=await request.json().catch(()=>({}));const key=prefix+String(b.id||"");const h=await env.SITE_ADMIN.get(key,"json");if(!h)return siteAdminJson({error:"Versione non trovata."},404);await saveContentHistory(env,path,await contentState(env,path));if(h.state)await env.SITE_ADMIN.put(SITE_ADMIN_CONTENT_PREFIX+path,JSON.stringify(h.state));else await env.SITE_ADMIN.delete(SITE_ADMIN_CONTENT_PREFIX+path);return siteAdminJson({ok:true});}}
    if(url.pathname==="/api/site-admin/library-exclusions") {
      let ids=await excludedPmids(env); if(request.method==="GET")return siteAdminJson({excluded:ids});const b=await request.json().catch(()=>({}));const pmid=String(b.pmid||"");if(!/^\d+$/.test(pmid))return siteAdminJson({error:"PMID non valido."},400);
      if(request.method==="POST"&&!ids.includes(pmid))ids.push(pmid);if(request.method==="DELETE")ids=ids.filter(x=>x!==pmid);await env.SITE_ADMIN.put(SITE_ADMIN_LIBRARY_EXCLUSIONS,JSON.stringify(ids));return siteAdminJson({ok:true,excluded:ids});
    }
    if(url.pathname==="/api/site-admin/config") {
      if(request.method==="GET") return siteAdminJson(await getSiteAdminConfig(env));
      if(request.method==="PUT") { const b=await request.json().catch(()=>({})); const cfg={menu:Array.isArray(b.menu)?b.menu:[]}; await env.SITE_ADMIN.put(SITE_ADMIN_CONFIG_KEY,JSON.stringify(cfg)); return siteAdminJson({ok:true,config:cfg}); }
    }
    if(url.pathname==="/api/site-admin/extended-config") {
      if(request.method==="GET") return siteAdminJson({config:await getExtendedConfig(env)});
      if(request.method==="PUT"){const cfg=cleanExtended(await request.json().catch(()=>({})));await env.SITE_ADMIN.put(SITE_ADMIN_EXTENDED_KEY,JSON.stringify(cfg));return siteAdminJson({ok:true,config:cfg});}
    }
    if(url.pathname==="/api/site-admin/media") {
      if(request.method==="GET"){const list=await env.SITE_ADMIN.list({prefix:SITE_ADMIN_MEDIA_PREFIX});const media=[];for(const k of list.keys){const m=await env.SITE_ADMIN.get(k.name,"json");if(m)media.push({id:m.id,name:m.name,type:m.type,url:"https://library.ketogenicresearch.org/media/"+m.id,created_at:m.created_at});}media.sort((a,b)=>String(b.created_at).localeCompare(String(a.created_at)));return siteAdminJson({media});}
      if(request.method==="POST"){const b=await request.json().catch(()=>({}));const data=String(b.data||"");if(!/^data:(?:image\/(?:png|jpeg|webp|svg\+xml)|application\/pdf);base64,/.test(data))return siteAdminJson({error:"Formato file non consentito."},400);if(data.length>3100000)return siteAdminJson({error:"File troppo grande."},413);const id=Date.now().toString(36)+"-"+crypto.randomUUID().slice(0,8);const m={id,name:String(b.name||"file").slice(0,180),type:String(b.type||"application/octet-stream").slice(0,80),data,created_at:new Date().toISOString()};await env.SITE_ADMIN.put(SITE_ADMIN_MEDIA_PREFIX+id,JSON.stringify(m));return siteAdminJson({ok:true,id,url:"https://library.ketogenicresearch.org/media/"+id});}
    }
    const mm=url.pathname.match(/^\/api\/site-admin\/media\/([a-zA-Z0-9_-]+)$/);if(mm&&request.method==="DELETE"){await env.SITE_ADMIN.delete(SITE_ADMIN_MEDIA_PREFIX+safeMediaId(mm[1]));return siteAdminJson({ok:true});}
    if(url.pathname==="/api/site-admin/status"&&request.method==="GET"){const st=await assetJson(request,env,"_admin-status.json");return siteAdminJson(st);}
    if(url.pathname==="/api/site-admin/backup"&&request.method==="GET"){const cfg=await getSiteAdminConfig(env),ext=await getExtendedConfig(env),excluded=await excludedPmids(env),pages=[];const pl=await env.SITE_ADMIN.list({prefix:SITE_ADMIN_PAGE_PREFIX});for(const k of pl.keys){const v=await env.SITE_ADMIN.get(k.name,"json");if(v)pages.push(v)}return new Response(JSON.stringify({exported_at:new Date().toISOString(),config:cfg,extended:ext,library_exclusions:excluded,pages},null,2),{headers:{"Content-Type":"application/json; charset=utf-8","Content-Disposition":"attachment; filename=ketogenicresearch-admin-backup.json","Cache-Control":"no-store"}});}
    if(url.pathname==="/api/site-admin/pages") {
      if(request.method==="GET") { const list=await env.SITE_ADMIN.list({prefix:SITE_ADMIN_PAGE_PREFIX}); const pages=[]; for(const k of list.keys){const p=await env.SITE_ADMIN.get(k.name,"json"); if(p) pages.push(p);} pages.sort((a,b)=>String(a.title||"").localeCompare(String(b.title||""))); return siteAdminJson({pages}); }
      if(request.method==="POST") { const b=await request.json().catch(()=>({})); const slug=safeSlug(b.slug||b.title); if(!slug) return siteAdminJson({error:"Slug non valido."},400); const key=SITE_ADMIN_PAGE_PREFIX+slug; if(await env.SITE_ADMIN.get(key)) return siteAdminJson({error:"Slug già esistente."},409); const now=new Date().toISOString(); const page={slug,title:String(b.title||slug).slice(0,160),description:String(b.description||"").slice(0,300),body_html:String(b.body_html||""),status:b.status==="published"?"published":"draft",created_at:now,updated_at:now}; await env.SITE_ADMIN.put(key,JSON.stringify(page)); return siteAdminJson({ok:true,page}); }
    }
    const m=url.pathname.match(/^\/api\/site-admin\/pages\/([a-z0-9-]+)$/);
    if(m){ const key=SITE_ADMIN_PAGE_PREFIX+safeSlug(m[1]);
      if(request.method==="GET"){const page=await env.SITE_ADMIN.get(key,"json"); return page?siteAdminJson({page}):siteAdminJson({error:"Pagina non trovata."},404);}
      if(request.method==="PUT"){const old=await env.SITE_ADMIN.get(key,"json"); if(!old)return siteAdminJson({error:"Pagina non trovata."},404); const b=await request.json().catch(()=>({})); const page={...old,title:String(b.title??old.title).slice(0,160),description:String(b.description??old.description).slice(0,300),body_html:String(b.body_html??old.body_html),status:b.status==="published"?"published":"draft",updated_at:new Date().toISOString()}; await env.SITE_ADMIN.put(key,JSON.stringify(page)); return siteAdminJson({ok:true,page});}
      if(request.method==="DELETE"){await env.SITE_ADMIN.delete(key); return siteAdminJson({ok:true});}
    }
    return siteAdminJson({error:"Endpoint non trovato."},404);
  } catch(e){return siteAdminJson({error:e?.message||"Site Admin error."},500);}
}
function cmsPageHtml(page){ return `<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${String(page.title||"").replace(/[<>&]/g,"")}</title><meta name="description" content="${String(page.description||"").replace(/["<>]/g,"")}"><link rel="stylesheet" href="/style.css"></head><body><main style="max-width:980px;margin:50px auto;padding:24px"><h1>${page.title||""}</h1>${page.body_html||""}</main></body></html>`; }

async function serveRawHtmlAsset(request, env, rawPath, extraHeaders = {}) {
  const assetUrl = new URL(rawPath, request.url);
  const assetRequest = new Request(assetUrl.toString(), { method: "GET", headers: request.headers });
  const r = await env.ASSETS.fetch(assetRequest);
  if (!r.ok) return r;
  const h = new Headers(r.headers);
  h.set("Content-Type", "text/html; charset=utf-8");
  for (const [k, v] of Object.entries(extraHeaders)) h.set(k, v);
  return new Response(r.body, { status: 200, headers: h });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/api/site-public/content" && request.method === "GET") return handlePublicContent(request,env,url);
    if (url.pathname === "/api/site-public/deleted-articles" && request.method === "GET") {
      const deleted=await deletedArticlePaths(env);
      return new Response(JSON.stringify({deleted}),{headers:{"Content-Type":"application/json; charset=utf-8","Access-Control-Allow-Origin":"https://ketogenicresearch.org","Cache-Control":"no-store"}});
    }
    if (url.pathname === "/api/site-public/config" && request.method === "GET") { let cfg=env.SITE_ADMIN?await getSiteAdminConfig(env):{menu:[]}; if(!Array.isArray(cfg.menu)||!cfg.menu.length){try{cfg={menu:await assetJson(request,env,"_admin-menu.json")};}catch(e){cfg={menu:[]};}} if(env.SITE_ADMIN) cfg.extended=await getExtendedConfig(env); return new Response(JSON.stringify(cfg),{headers:{"Content-Type":"application/json; charset=utf-8","Access-Control-Allow-Origin":"https://ketogenicresearch.org","Cache-Control":"no-store"}}); }
    const mediaMatch=url.pathname.match(/^\/media\/([a-zA-Z0-9_-]+)$/);if(mediaMatch&&env.SITE_ADMIN){const m=await env.SITE_ADMIN.get(SITE_ADMIN_MEDIA_PREFIX+safeMediaId(mediaMatch[1]),"json");if(!m)return new Response("Not found",{status:404});const comma=String(m.data||"").indexOf(',');const bytes=Uint8Array.from(atob(String(m.data||"").slice(comma+1)),c=>c.charCodeAt(0));return new Response(bytes,{headers:{"Content-Type":m.type||"application/octet-stream","Cache-Control":"public, max-age=3600","X-Content-Type-Options":"nosniff"}});}
    if((url.pathname==="/scientific-committee"||url.pathname==="/scientific-committee/")&&env.SITE_ADMIN){const c=(await getExtendedConfig(env)).committee;if(!c?.published)return new Response("Not found",{status:404});return new Response(committeeHtml(c),{headers:{"Content-Type":"text/html; charset=utf-8","Cache-Control":"public, max-age=60"}});}

    if ((url.pathname === "/review-studio" || url.pathname === "/review-studio/" || url.pathname === "/review-studio.html") && request.method === "GET") {
      const auth=await requireReviewAdmin(request,env); if(!auth.ok)return auth.response;
      return serveRawHtmlAsset(request,env,"/_raw-review-studio.txt",{"Cache-Control":"private, no-store","X-Robots-Tag":"noindex,nofollow"});
    }
    if (url.pathname.startsWith("/api/review/")) {
      const auth=await requireReviewAdmin(request,env); if(!auth.ok)return auth.response;
      try { if(url.pathname==="/api/review/evidence/areas")return handleEvidenceAreas(request,env); if(url.pathname==="/api/review/evidence/status")return handleEvidenceStatus(request,env); if(url.pathname==="/api/review/evidence/process"&&request.method==="POST")return handleEvidenceProcess(request,env); if(url.pathname==="/api/review/evidence/synthesis"&&request.method==="GET")return handleEvidenceSynthesisGet(request,env); if(url.pathname==="/api/review/evidence/synthesize"&&request.method==="POST")return handleEvidenceSynthesize(request,env); if(url.pathname==="/api/review/protocol")return handleProtocolApi(request,env); if(url.pathname==="/api/review/pubmed")return handlePubmedApi(request,env); if(url.pathname==="/api/review/draft")return handleDraftApi(request,env); return jsonResponse({error:"Not found"},404); } catch(e){ return jsonResponse({error:e?.message||"Review Studio error"},500); }
    }

    // Serve the login document from a non-HTML raw asset. This bypasses
    // Cloudflare Pages HTML canonical redirects, avoiding /library-access loops.
    if ((url.pathname === "/library-access" || url.pathname === "/library-access/" || url.pathname === "/library-access.html") && request.method === "GET") {
      return serveRawHtmlAsset(request, env, "/_raw-library-access.txt", {
        "Cache-Control": "no-store",
        "X-Robots-Tag": "noindex, noarchive, nofollow"
      });
    }

    if (url.pathname.startsWith("/api/site-admin/")) return handleSiteAdminApi(request, env, url);

    if ((url.pathname === "/admin" || url.pathname === "/admin/") && request.method === "GET") {
      const auth = await requireSiteAdmin(request, env); if (!auth.ok) return auth.response;
      return serveRawHtmlAsset(request, env, "/_raw-admin.txt", {
        "Cache-Control": "private, no-store",
        "X-Robots-Tag": "noindex, noarchive,nofollow"
      });
    }

    const cms = url.pathname.match(/^\/p\/([a-z0-9-]+)\/?$/);
    if (cms && env.SITE_ADMIN) { const page=await env.SITE_ADMIN.get(SITE_ADMIN_PAGE_PREFIX+safeSlug(cms[1]),"json"); if(!page||page.status!=="published") return new Response("Not found",{status:404}); return new Response(cmsPageHtml(page),{headers:{"Content-Type":"text/html; charset=utf-8","Cache-Control":"public, max-age=60"}}); }

    if (!env.SESSION_SECRET) {
      return new Response("SESSION_SECRET non configurato su Cloudflare.", {
        status: 500,
        headers: { "Content-Type": "text/plain; charset=utf-8" }
      });
    }

    // Dominio tecnico -> dominio definitivo.
    if (url.hostname === "ketogenicresearch-library.pages.dev") {
      const canonical = new URL(request.url);
      canonical.hostname = "library.ketogenicresearch.org";
      canonical.protocol = "https:";
      return Response.redirect(canonical.toString(), 301);
    }

    // Rotte canoniche.
    if (url.pathname === "/library.html") {
      return Response.redirect("https://library.ketogenicresearch.org/library", 302);
    }

    // Se un vecchio link Home punta a index.html, torna al sito pubblico.
    if (url.pathname === "/index.html") {
      return Response.redirect("https://ketogenicresearch.org/", 302);
    }

    // Il login Supabase viene validato UNA SOLA VOLTA.
    // Poi viene creata una sessione firmata dal Worker, indipendente dai rate limit Auth.
    if (url.pathname === "/auth/session" && request.method === "POST") {
      let payload;
      try {
        payload = await request.json();
      } catch {
        return Response.json({ error: "Invalid request body" }, { status: 400 });
      }

      const accessToken = payload?.access_token || "";
      const user = await validateSupabaseLogin(accessToken);

      if (!user?.id || !user?.email_confirmed_at) {
        return Response.json({ error: "Invalid or unconfirmed Supabase session" }, { status: 401 });
      }

      const profile = await fetchProfile(accessToken, user.id);
      if (!profile) {
        return Response.json({ error: "Library profile not available" }, { status: 403 });
      }

      const now = Math.floor(Date.now() / 1000);
      const session = await signSession({
        sub: user.id,
        email: user.email || profile.email || "",
        first_name: profile.first_name || "",
        last_name: profile.last_name || "",
        iat: now,
        exp: now + SESSION_MAX_AGE
      }, env.SESSION_SECRET);

      const headers = new Headers({
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store"
      });
      headers.append("Set-Cookie", sessionCookie(session));
      // Elimina i vecchi cookie Supabase usati dalle versioni precedenti.
      headers.append("Set-Cookie", clearCookie("kr_access_token"));
      headers.append("Set-Cookie", clearCookie("kr_refresh_token"));

      return new Response(JSON.stringify({ ok: true }), { status: 200, headers });
    }

    if (url.pathname === "/auth/me" && request.method === "GET") {
      const cookies = parseCookies(request);
      const session = await verifySession(cookies.kr_session || "", env.SESSION_SECRET);

      if (!session) {
        return Response.json(
          { authenticated: false },
          { status: 401, headers: { "Cache-Control": "no-store" } }
        );
      }

      return Response.json({
        authenticated: true,
        email: session.email || "",
        first_name: session.first_name || "",
        last_name: session.last_name || ""
      }, {
        headers: { "Cache-Control": "no-store" }
      });
    }

    if (url.pathname === "/auth/logout" && request.method === "POST") {
      const headers = new Headers({
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store"
      });
      headers.append("Set-Cookie", clearCookie("kr_session"));
      headers.append("Set-Cookie", clearCookie("kr_access_token"));
      headers.append("Set-Cookie", clearCookie("kr_refresh_token"));
      return new Response(JSON.stringify({ ok: true }), { status: 200, headers });
    }

    if (
      (url.pathname === "/admin/export-users") &&
      request.method === "GET"
    ) {
      const cookies = parseCookies(request);
      const session = await verifySession(cookies.kr_session || "", env.SESSION_SECRET);

      if (!session) {
        return redirectToLogin(request, "login");
      }

      if (!isAdminSession(session, env)) {
        return new Response("Accesso non autorizzato.", {
          status: 403,
          headers: {
            "Content-Type": "text/plain; charset=utf-8",
            "Cache-Control": "no-store",
            "X-Robots-Tag": "noindex, noarchive, nofollow"
          }
        });
      }

      if (url.pathname === "/admin/export-users") {
        return exportUsersXlsx(env);
      }

      return new Response(adminPageHtml(), {
        status: 200,
        headers: {
          "Content-Type": "text/html; charset=utf-8",
          "Cache-Control": "private, no-store",
          "X-Robots-Tag": "noindex, noarchive, nofollow"
        }
      });
    }

    const protectedPath =
      url.pathname === "/library" ||
      url.pathname === "/library/" ||
      url.pathname.startsWith("/library-chunks/");

    if (!protectedPath) {
      return env.ASSETS.fetch(request);
    }

    const cookies = parseCookies(request);
    const session = await verifySession(cookies.kr_session || "", env.SESSION_SECRET);

    if (!session) {
      return redirectToLogin(request, "login");
    }

    let assetResponse = await env.ASSETS.fetch(request);
    if (url.pathname.startsWith("/library-chunks/")) assetResponse = await applyLibraryExclusions(assetResponse,env);
    if ((assetResponse.headers.get("Content-Type")||"").includes("text/html")) assetResponse = await applyClinicalIconOverrides(assetResponse,request,env);
    const headers = new Headers(assetResponse.headers);
    headers.set("Cache-Control", "private, no-store");
    headers.set("X-Robots-Tag", "noindex, noarchive, nofollow");

    if (isAdminSession(session, env) && assetResponse.ok) {
      const contentType = assetResponse.headers.get("Content-Type") || "";
      if (contentType.includes("text/html")) {
        const rewritten = new HTMLRewriter()
          .on("body", {
            element(element) {
              element.append(`
                <a href="/admin"
                   id="kr-admin-link"
                   style="
                     position:fixed;
                     right:18px;
                     bottom:18px;
                     z-index:99999;
                     padding:10px 14px;
                     border-radius:9px;
                     background:#0f6b7a;
                     color:#fff;
                     text-decoration:none;
                     font:600 14px Arial,Helvetica,sans-serif;
                     box-shadow:0 5px 18px rgba(0,0,0,.18);
                   ">
                  Amministrazione
                </a>
              `, { html: true });
            }
          })
          .transform(assetResponse);

        const rewrittenHeaders = new Headers(rewritten.headers);
        rewrittenHeaders.set("Cache-Control", "private, no-store");
        rewrittenHeaders.set("X-Robots-Tag", "noindex, noarchive, nofollow");

        return new Response(rewritten.body, {
          status: rewritten.status,
          statusText: rewritten.statusText,
          headers: rewrittenHeaders
        });
      }
    }

    return new Response(assetResponse.body, {
      status: assetResponse.status,
      statusText: assetResponse.statusText,
      headers
    });
  }
};
