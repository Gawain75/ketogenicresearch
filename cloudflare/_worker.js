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
  let r;
  try{
    r=await fetch(endpoint,{method:"POST",headers:{"Authorization":`Bearer ${env.GROQ_API_KEY}`,"Content-Type":"application/json"},body:JSON.stringify({model,temperature:0.1,max_completion_tokens:maxCompletionTokens,reasoning_effort:"low",response_format:{type:"json_object"},messages})});
  }catch(e){
    throw new Error(`AI synthesis network error: ${e?.message||"request failed"}. No automatic retry was attempted.`);
  }
  if(!r.ok){
    let detail=""; try{const j=await r.json();detail=String(j?.error?.message||j?.message||"");}catch{try{detail=await r.text();}catch{}}
    throw new Error(`AI synthesis service error (${r.status})${detail?`: ${detail.slice(0,700)}`:""}. No automatic retry was attempted.`);
  }
  const data=await r.json();
  try{return extractJsonObject(data?.choices?.[0]?.message?.content||"");}
  catch(e){throw new Error(`AI synthesis returned invalid JSON: ${e?.message||"parse error"}. No repair/retry request was attempted.`);}
}


async function groqTextSingle(env, messages, maxCompletionTokens=520) {
  if (!env.GROQ_API_KEY) throw new Error("GROQ_API_KEY is not configured in Cloudflare.");
  const endpoint="https://api.groq.com/openai/v1/chat/completions";
  const model=env.GROQ_MODEL || "openai/gpt-oss-120b";
  let r;
  try{
    r=await fetch(endpoint,{method:"POST",headers:{"Authorization":`Bearer ${env.GROQ_API_KEY}`,"Content-Type":"application/json"},body:JSON.stringify({model,temperature:0.1,max_completion_tokens:maxCompletionTokens,reasoning_effort:"low",messages})});
  }catch(e){throw new Error(`AI synthesis network error: ${e?.message||"request failed"}. No automatic retry was attempted.`);}
  if(!r.ok){
    let detail="";try{const j=await r.json();detail=String(j?.error?.message||j?.message||"");}catch{try{detail=await r.text();}catch{}}
    throw new Error(`AI synthesis service error (${r.status})${detail?`: ${detail.slice(0,700)}`:""}. No automatic retry was attempted.`);
  }
  const data=await r.json();
  const out=String(data?.choices?.[0]?.message?.content||"").trim();
  if(!out) throw new Error("AI synthesis returned an empty response. No automatic retry was attempted.");
  return out;
}

function parseFinalNarrativeText(text){
  const keys={OVERALL:"overall_interpretation",CONSISTENCY:"evidence_consistency",HUMAN:"human_clinical",REVIEWS:"reviews_meta_analyses",PRECLINICAL:"preclinical_mechanistic",LIMITATIONS:"limitations",GAPS:"research_gaps",BOTTOM:"bottom_line"};
  const out={limitations:[],research_gaps:[]};
  for(const raw of String(text||"").split(/\r?\n/)){
    const line=raw.trim(); if(!line) continue;
    const m=line.match(/^(OVERALL|CONSISTENCY|HUMAN|REVIEWS|PRECLINICAL|LIMITATIONS|GAPS|BOTTOM)\s*[:|]\s*(.*)$/i);
    if(!m) continue; const tag=m[1].toUpperCase(), val=m[2].trim();
    if(tag==="LIMITATIONS") out.limitations=val.split(/\s*;\s*/).filter(Boolean).slice(0,8);
    else if(tag==="GAPS") out.research_gaps=val.split(/\s*;\s*/).filter(Boolean).slice(0,8);
    else out[keys[tag]]=val;
  }
  const required=["overall_interpretation","evidence_consistency","human_clinical","reviews_meta_analyses","preclinical_mechanistic","bottom_line"];
  if(required.some(k=>!String(out[k]||"").trim())) throw new Error("AI narrative response did not contain all required labelled lines. No automatic retry was attempted.");
  if(!["consistent","mostly_consistent","mixed","conflicting","insufficient"].includes(out.evidence_consistency)) out.evidence_consistency="insufficient";
  return out;
}

function parseFinalClaimsText(text){
  const out={main_findings:[],conflicting_evidence:[]};
  for(const raw of String(text||"").split(/\r?\n/)){
    const line=raw.trim(); if(!line) continue;
    const m=line.match(/^([FC])\|([^|]+)\|(.+)$/i); if(!m) continue;
    const pmids=m[2].split(",").map(x=>x.trim()).filter(x=>/^\d{7,9}$/.test(x));
    const claim=m[3].trim(); if(!pmids.length||!claim) continue;
    if(m[1].toUpperCase()==="F" && out.main_findings.length<8) out.main_findings.push({finding:claim,pmids});
    if(m[1].toUpperCase()==="C" && out.conflicting_evidence.length<6) out.conflicting_evidence.push({issue:claim,pmids});
  }
  if(!out.main_findings.length && !out.conflicting_evidence.length) throw new Error("AI source-lock response contained no parseable sourced claims. No automatic retry was attempted.");
  return out;
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
const EVIDENCE_LAB_COMPACT_PREFIX = "evidence-lab:v2:compact:";
const EVIDENCE_LAB_COMPACT_BUCKETS = 64;
const EVIDENCE_LAB_LARGE_CORPUS_THRESHOLD = 200;
const EVIDENCE_LAB_SCHEMA_VERSION = 2;

function evidenceCompactBucket(pmid){
  const x=String(pmid||""); let h=0; for(let i=0;i<x.length;i++)h=(h*31+x.charCodeAt(i))>>>0; return h%EVIDENCE_LAB_COMPACT_BUCKETS;
}
function evidenceCompactCard(c){
  return {schema_version:Number(c?.schema_version||EVIDENCE_LAB_SCHEMA_VERSION),pmid:String(c?.pmid||""),title:String(c?.title||""),doi:c?.doi||null,year:c?.year||null,publication_type:String(c?.publication_type||"other"),study_design:String(c?.study_design||""),evidence_domain:String(c?.evidence_domain||"other"),study_purpose:String(c?.study_purpose||"other"),population:String(c?.population||""),sample_size:c?.sample_size??null,sample_size_details:String(c?.sample_size_details||""),intervention:String(c?.intervention||""),comparator:String(c?.comparator||""),duration:String(c?.duration||""),primary_outcomes:Array.isArray(c?.primary_outcomes)?c.primary_outcomes:[],secondary_outcomes:Array.isArray(c?.secondary_outcomes)?c.secondary_outcomes:[],effect_direction:String(c?.effect_direction||"not_reported"),statistical_significance:String(c?.statistical_significance||"not_reported"),randomized:String(c?.randomized||"not_reported"),controlled:String(c?.controlled||"not_reported"),time_orientation:String(c?.time_orientation||"not_reported"),population_phenotype:String(c?.population_phenotype||""),review_studies_included:c?.review_studies_included??null,review_participants:c?.review_participants??null,review_study_types:String(c?.review_study_types||""),pooled_effect:String(c?.pooled_effect||""),heterogeneity:String(c?.heterogeneity||""),risk_of_bias_or_certainty:String(c?.risk_of_bias_or_certainty||""),animal_species:String(c?.animal_species||""),animal_model:String(c?.animal_model||""),mechanistic_targets:Array.isArray(c?.mechanistic_targets)?c.mechanistic_targets:[],main_result:String(c?.main_result||""),limitations:Array.isArray(c?.limitations)?c.limitations:[],source_level:String(c?.source_level||"metadata"),extraction_confidence:String(c?.extraction_confidence||"low")};
}
async function evidenceCompactLoad(env,slug){
  const rows=await Promise.all(Array.from({length:EVIDENCE_LAB_COMPACT_BUCKETS},(_,i)=>env.SITE_ADMIN.get(`${EVIDENCE_LAB_COMPACT_PREFIX}${slug}:${i}`,"json").catch(()=>null)));
  const out=new Map(); for(const row of rows){for(const c of (Array.isArray(row?.cards)?row.cards:[])){if(c?.pmid)out.set(String(c.pmid),c);}} return out;
}
async function evidenceCompactPutMany(env,slug,cards){
  const groups=new Map();
  for(const card of cards||[]){if(!card?.pmid)continue;const b=evidenceCompactBucket(card.pmid);if(!groups.has(b))groups.set(b,[]);groups.get(b).push(evidenceCompactCard(card));}
  for(const [b,list] of groups){const key=`${EVIDENCE_LAB_COMPACT_PREFIX}${slug}:${b}`;const row=(await env.SITE_ADMIN.get(key,"json").catch(()=>null))||{schema_version:1,cards:[]};const m=new Map((Array.isArray(row.cards)?row.cards:[]).map(x=>[String(x.pmid),x]));for(const c of list)m.set(String(c.pmid),c);await env.SITE_ADMIN.put(key,JSON.stringify({schema_version:1,updated_at:new Date().toISOString(),cards:[...m.values()]}));}
}

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
  let indexed=null; if(area.count>EVIDENCE_LAB_LARGE_CORPUS_THRESHOLD || processed.size>EVIDENCE_LAB_LARGE_CORPUS_THRESHOLD){const compact=await evidenceCompactLoad(env,slug);indexed=[...processed].filter(x=>compact.has(String(x))).length;}
  return jsonResponse({area:{slug,label:area.label,total:area.count},processed:processed.size,remaining:Math.max(0,area.count-processed.size),failed:(st.failed||[]).length,source_counts:{pmc_linked:withPmc,abstract_available:withAbstract,metadata_only:area.count-withAbstract},large_corpus:area.count>EVIDENCE_LAB_LARGE_CORPUS_THRESHOLD,indexed_cards:indexed,updated_at:st.updated_at,cards:sample});
}
async function handleEvidenceMap(request,env){
  if(!env.SITE_ADMIN)return jsonResponse({error:"Evidence Lab storage (SITE_ADMIN) is not configured."},503);
  const url=new URL(request.url), slug=evidenceLabSlug(url.searchParams.get("area"));
  if(!slug)return jsonResponse({error:"Clinical area is required."},400);
  const idx=await evidenceLabIndex(request,env), area=idx.areas.find(a=>a.slug===slug);
  if(!area)return jsonResponse({error:"Clinical area not found."},404);
  const st=await evidenceLabState(env,slug), cards=[];
  const processedIds=(st.processed||[]).map(String);
  let workCards=[];
  if(area.count>EVIDENCE_LAB_LARGE_CORPUS_THRESHOLD || processedIds.length>EVIDENCE_LAB_LARGE_CORPUS_THRESHOLD){const compact=await evidenceCompactLoad(env,slug);workCards=processedIds.map(p=>compact.get(p)).filter(Boolean);}
  else{for(const pmid of processedIds){const c=await env.SITE_ADMIN.get(EVIDENCE_LAB_CARD_PREFIX+slug+":"+pmid,"json");if(c)workCards.push(c);}}
  const classOf=t=>{t=String(t||"other");if(["clinical_trial","observational","mechanistic_human","case_report_series"].includes(t))return "human_clinical";if(["systematic_review_meta_analysis","narrative_review"].includes(t))return "reviews";if(["preclinical_animal","mechanistic_preclinical"].includes(t))return "preclinical";return "other";};
  const relevance_counts={direct:0,supporting:0,contextual:0,not_evaluable:0,exclude:0}, class_counts={human_clinical:0,reviews:0,preclinical:0,other:0}, direction_counts={favorable:0,mixed:0,neutral:0,unfavorable:0,not_reported:0};
  const matrix={human_clinical:{direct:0,supporting:0,contextual:0,not_evaluable:0,exclude:0},reviews:{direct:0,supporting:0,contextual:0,not_evaluable:0,exclude:0},preclinical:{direct:0,supporting:0,contextual:0,not_evaluable:0,exclude:0},other:{direct:0,supporting:0,contextual:0,not_evaluable:0,exclude:0}};
  for(const c of workCards){
    const pmid=String(c.pmid||"");if(!c)continue;
    const evidenceBearing=c.source_level==="abstract"||c.source_level==="full_text";
    const rel=evidenceBearing?evidenceRelevance(c,area.label):{level:"not_evaluable",reason:"metadata-only / no evidence-bearing abstract or full text"}, evidence_class=classOf(c.publication_type), dir=["favorable","mixed","neutral","unfavorable"].includes(String(c.effect_direction||""))?String(c.effect_direction):"not_reported";
    relevance_counts[rel.level]=(relevance_counts[rel.level]||0)+1;class_counts[evidence_class]=(class_counts[evidence_class]||0)+1;direction_counts[dir]=(direction_counts[dir]||0)+1;matrix[evidence_class][rel.level]=(matrix[evidence_class][rel.level]||0)+1;
    cards.push({pmid:String(c.pmid||pmid),title:String(c.title||""),year:c.year||null,publication_type:String(c.publication_type||"other"),study_design:String(c.study_design||""),evidence_domain:String(c.evidence_domain||"other"),study_purpose:String(c.study_purpose||"other"),effect_direction:dir,statistical_significance:String(c.statistical_significance||"not_reported"),randomized:String(c.randomized||"not_reported"),controlled:String(c.controlled||"not_reported"),source_level:String(c.source_level||"metadata"),extraction_confidence:String(c.extraction_confidence||"low"),main_result:String(c.main_result||""),relevance:rel.level,relevance_reason:rel.reason,evidence_class});
  }
  cards.sort((a,b)=>{const rank={direct:0,supporting:1,contextual:2,not_evaluable:3,exclude:4};const r=(rank[a.relevance]??9)-(rank[b.relevance]??9);if(r)return r;const y=Number(b.year||0)-Number(a.year||0);if(y)return y;return a.title.localeCompare(b.title);});
  return jsonResponse({schema_version:1,generated_at:new Date().toISOString(),area:{slug,label:area.label,total:area.count},cards_mapped:cards.length,relevance_counts,class_counts,direction_counts,matrix,cards});
}

function evidenceOutcomeDomains(card){
  const norm=v=>String(v??"").toLowerCase().normalize("NFKD").replace(/[\u0300-\u036f]/g,"");
  const join=v=>Array.isArray(v)?v.map(x=>typeof x==="string"?x:JSON.stringify(x)).join(" "):String(v??"");
  const text=norm([join(card.primary_outcomes),join(card.secondary_outcomes),card.main_result,card.title].join(" "));
  const defs=[
    ["motor",/(updrs[- ]?iii|updrs part iii|motor symptom|motor score|motor function|bradykines|rigidity|tremor)/],
    ["non_motor",/(non[- ]?motor|nmss|updrs part 1|updrs[- ]?i\b|apathy|sleep|fatigue|mood|constipation)/],
    ["gait_balance",/(timed up and go|\btug\b|gait|freezing|balance|postural)/],
    ["cognition",/(cognit|memory|lexical|executive|attention|moca|mmse)/],
    ["voice",/(voice|vhi|phonat|speech)/],
    ["quality_of_life",/(quality of life|pdq[- ]?39|pdq[- ]?8|adl|iadl|activities of daily living)/],
    ["safety",/(safety|safe|adverse|tolerab|side effect)/],
    ["feasibility_adherence",/(feasib|acceptab|adherence|compliance|dropout|retention)/],
    ["pharmacokinetics",/(pharmacokinetic|levodopa|bioavailability|auc|cmax|tmax)/],
    ["biomarkers_microbiome",/(microbi|biomarker|beta[- ]?hydroxybutyrate|\bbhb\b|ketosis|metabol|inflamm|oxidative)/]
  ];
  const found=defs.filter(([,re])=>re.test(text)).map(([k])=>k);
  return found.length?found:["other_clinical"];
}
function evidenceDomainDirection(card,domain){
  const norm=v=>String(v??"").toLowerCase().normalize("NFKD").replace(/[\u0300-\u036f]/g,"");
  const result=norm(card.main_result||"");
  const chunks=result.split(/(?<=[.!?;])\s+/).filter(Boolean);
  const domainRegex={
    motor:/(updrs[- ]?iii|updrs part iii|motor symptom|motor score|motor function|bradykines|rigidity|tremor)/,
    non_motor:/(non[- ]?motor|nmss|updrs part 1|updrs[- ]?i\b|apathy|sleep|fatigue|mood|constipation)/,
    gait_balance:/(timed up and go|\btug\b|gait|freezing|balance|postural)/,
    cognition:/(cognit|memory|lexical|executive|attention|moca|mmse)/,
    voice:/(voice|vhi|phonat|speech)/,
    quality_of_life:/(quality of life|pdq[- ]?39|pdq[- ]?8|adl|iadl|activities of daily living)/,
    safety:/(safety|safe|adverse|tolerab|side effect)/,
    feasibility_adherence:/(feasib|acceptab|adherence|compliance|dropout|retention)/,
    pharmacokinetics:/(pharmacokinetic|levodopa|bioavailability|auc|cmax|tmax)/,
    biomarkers_microbiome:/(microbi|biomarker|beta[- ]?hydroxybutyrate|\bbhb\b|ketosis|metabol|inflamm|oxidative)/,
    other_clinical:/.*/
  }[domain]||/.*/;
  const relevant=chunks.filter(x=>domainRegex.test(x));
  const text=(relevant.length?relevant:[result]).join(" ");
  const nullish=/(no significant|not significant|no between[- ]?group|no difference|did not improve|did not affect|failed to|unchanged|comparable gains|similar between)/.test(text);
  const adverse=/(worsen|worse|deteriorat|unfavorable|adverse effect|increased symptoms)/.test(text);
  const positive=/(significant improvement|improved|improvement|greater reduction|decreased more|better|favorable|benefit|reduced|ameliorat)/.test(text);
  if(adverse && positive)return "mixed";
  if(adverse)return "unfavorable";
  if(nullish && positive)return "mixed";
  if(nullish)return "neutral";
  if(positive)return "favorable";
  const d=String(card.effect_direction||"not_reported");
  return ["favorable","mixed","neutral","unfavorable"].includes(d)?d:"not_reported";
}
async function handleEvidenceContradictions(request,env){
  if(!env.SITE_ADMIN)return jsonResponse({error:"Evidence Lab storage (SITE_ADMIN) is not configured."},503);
  const url=new URL(request.url), slug=evidenceLabSlug(url.searchParams.get("area"));
  if(!slug)return jsonResponse({error:"Clinical area is required."},400);
  const idx=await evidenceLabIndex(request,env), area=idx.areas.find(a=>a.slug===slug);
  if(!area)return jsonResponse({error:"Clinical area not found."},404);
  const st=await evidenceLabState(env,slug), human=[];
  const processedIds=(st.processed||[]).map(String);
  let workCards=[];
  if(area.count>EVIDENCE_LAB_LARGE_CORPUS_THRESHOLD || processedIds.length>EVIDENCE_LAB_LARGE_CORPUS_THRESHOLD){const compact=await evidenceCompactLoad(env,slug);workCards=processedIds.map(p=>compact.get(p)).filter(Boolean);}
  else{for(const pmid of processedIds){const c=await env.SITE_ADMIN.get(EVIDENCE_LAB_CARD_PREFIX+slug+":"+pmid,"json");if(c)workCards.push(c);}}
  for(const c of workCards){
    const pmid=String(c.pmid||"");
    if(!c || !(c.source_level==="abstract"||c.source_level==="full_text"))continue;
    const rel=evidenceRelevance(c,area.label), type=String(c.publication_type||"");
    if(rel.level!=="direct" || !["clinical_trial","observational","mechanistic_human","case_report_series"].includes(type))continue;
    const domains=evidenceOutcomeDomains(c);
    human.push({pmid:String(c.pmid||pmid),title:String(c.title||""),year:c.year||null,publication_type:type,study_design:String(c.study_design||""),study_purpose:String(c.study_purpose||"other"),randomized:String(c.randomized||"not_reported"),controlled:String(c.controlled||"not_reported"),sample_size:c.sample_size??null,intervention:String(c.intervention||""),comparator:String(c.comparator||""),primary_outcomes:Array.isArray(c.primary_outcomes)?c.primary_outcomes:[],main_result:String(c.main_result||""),effect_direction:String(c.effect_direction||"not_reported"),domains:domains.map(domain=>({domain,direction:evidenceDomainDirection(c,domain)}))});
  }
  const domainLabels={motor:"Motor symptoms",non_motor:"Non-motor symptoms",gait_balance:"Gait / balance",cognition:"Cognition",voice:"Voice / speech",quality_of_life:"Quality of life / ADL",safety:"Safety / tolerability",feasibility_adherence:"Feasibility / adherence",pharmacokinetics:"Pharmacokinetics",biomarkers_microbiome:"Biomarkers / microbiome / ketosis",other_clinical:"Other clinical outcomes"};
  const groups=[];
  for(const domain of Object.keys(domainLabels)){
    const studies=human.flatMap(c=>c.domains.filter(d=>d.domain===domain).map(d=>({...c,domain_direction:d.direction}))).map(({domains,...x})=>x);
    if(!studies.length)continue;
    const counts={favorable:0,mixed:0,neutral:0,unfavorable:0,not_reported:0};for(const x of studies)counts[x.domain_direction]=(counts[x.domain_direction]||0)+1;
    const informative=counts.favorable+counts.mixed+counts.neutral+counts.unfavorable;
    let status="insufficient";
    if(counts.favorable>0&&(counts.neutral>0||counts.unfavorable>0))status="discordant";
    else if(counts.favorable>0&&counts.mixed>0)status="mixed";
    else if(counts.favorable>=2&&!counts.mixed&&!counts.neutral&&!counts.unfavorable)status="consistent_favorable";
    else if((counts.neutral+counts.unfavorable)>=2&&!counts.favorable&&!counts.mixed)status="consistent_null_or_unfavorable";
    else if(informative>=1)status=counts.mixed?"mixed":"limited";
    const priority={discordant:0,mixed:1,consistent_favorable:2,consistent_null_or_unfavorable:3,limited:4,insufficient:5};
    groups.push({domain,label:domainLabels[domain],status,counts,studies,priority:priority[status]??9});
  }
  groups.sort((a,b)=>a.priority-b.priority||b.studies.length-a.studies.length||a.label.localeCompare(b.label));
  const discordant=groups.filter(x=>x.status==="discordant").length, mixed=groups.filter(x=>x.status==="mixed").length, consistent_favorable=groups.filter(x=>x.status==="consistent_favorable").length;
  const conclusion_signal=discordant?"heterogeneous":mixed?"mixed_with_favorable_signal":consistent_favorable?"favorable_signal_with_limited_evidence":"insufficient";
  return jsonResponse({schema_version:1,generated_at:new Date().toISOString(),area:{slug,label:area.label},direct_human_studies:human.length,outcome_domains:groups.length,discordant_domains:discordant,mixed_domains:mixed,consistent_favorable_domains:consistent_favorable,conclusion_signal,groups});
}
async function handleEvidenceConclusion(request,env){
  if(!env.SITE_ADMIN)return jsonResponse({error:"Evidence Lab storage (SITE_ADMIN) is not configured."},503);
  const url=new URL(request.url), slug=evidenceLabSlug(url.searchParams.get("area"));
  if(!slug)return jsonResponse({error:"Clinical area is required."},400);
  const idx=await evidenceLabIndex(request,env), area=idx.areas.find(a=>a.slug===slug);
  if(!area)return jsonResponse({error:"Clinical area not found."},404);
  const reviewKey="evidence-lab:v2:review:"+slug;
  const review={schema_version:1,status:"draft",...((await env.SITE_ADMIN.get(reviewKey,"json"))||{})};
  const current=await evidenceReviewSnapshot(request,env,slug);
  if(!current)return jsonResponse({error:"A saved synthesis is required before a conclusion can be generated."},409);
  const changes=evidenceReviewDiff(review.approved_snapshot,current);
  if(review.status!=="approved" || !review.approved_snapshot)return jsonResponse({error:"The synthesis must be approved before an evidence conclusion is available.",code:"approval_required"},409);
  if(changes.has_changes)return jsonResponse({error:"The evidence state changed after approval. Review and approve the current synthesis before using the conclusion.",code:"approval_outdated",changes},409);

  const cu=new URL(request.url);cu.pathname="/api/review/evidence/contradictions";cu.searchParams.set("area",slug);
  const cr=await handleEvidenceContradictions(new Request(cu.toString(),{method:"GET"}),env);
  const contradiction=await cr.json();
  if(!cr.ok)return jsonResponse({error:contradiction?.error||"Unable to build outcome-level evidence comparison."},cr.status||500);

  const groups=Array.isArray(contradiction.groups)?contradiction.groups:[];
  const favorable=groups.filter(g=>g.status==="consistent_favorable");
  const mixed=groups.filter(g=>g.status==="mixed");
  const discordant=groups.filter(g=>g.status==="discordant");
  const nullish=groups.filter(g=>g.status==="consistent_null_or_unfavorable");
  const profile=current.evidence_profile||{};
  const clinicalTrials=Number(profile.clinical_trial||0);
  const directHuman=Number(contradiction.direct_human_studies||0);
  let maturity="very limited";
  if(directHuman>=6 && clinicalTrials>=4 && discordant.length===0)maturity="developing";
  else if(directHuman>=3 && clinicalTrials>=2)maturity="limited";
  const signal=discordant.length?"heterogeneous / discordant":(mixed.length&&favorable.length)?"favorable signal with outcome-level uncertainty":favorable.length>=2?"favorable signal across several outcome domains":nullish.length>=2?"predominantly null or unfavorable":"insufficiently characterized";
  const interpretation=discordant.length
    ? `Direct human evidence is heterogeneous, with ${discordant.length} discordant outcome domain${discordant.length===1?"":"s"}.`
    : favorable.length&&mixed.length
      ? `Direct human evidence shows a favorable signal in ${favorable.length} outcome domain${favorable.length===1?"":"s"}, while ${mixed.length} domain${mixed.length===1?" remains":"s remain"} mixed.`
      : favorable.length
        ? `Direct human evidence shows a consistent favorable signal in ${favorable.length} outcome domain${favorable.length===1?"":"s"}, without a detected discordant domain.`
        : `Direct human evidence does not show a sufficiently consistent favorable signal across outcome domains.`;
  const limitations=(current.limitations||[]).map(String).filter(Boolean).slice(0,6);
  const gaps=(current.research_gaps||[]).map(String).filter(Boolean).slice(0,6);
  return jsonResponse({
    schema_version:1,generated_at:new Date().toISOString(),area:{slug,label:area.label},
    approval:{approved_at:review.approved_at||null,approved_by:review.approved_by||null,current:true},
    signal,maturity,interpretation,
    direct_human_studies:directHuman,clinical_trials:clinicalTrials,outcome_domains:Number(contradiction.outcome_domains||0),
    consistent_favorable_domains:favorable.map(g=>({domain:g.domain,label:g.label,counts:g.counts})),
    mixed_domains:mixed.map(g=>({domain:g.domain,label:g.label,counts:g.counts})),
    discordant_domains:discordant.map(g=>({domain:g.domain,label:g.label,counts:g.counts})),
    null_or_unfavorable_domains:nullish.map(g=>({domain:g.domain,label:g.label,counts:g.counts})),
    limitations,research_gaps:gaps,
    approved_overall_interpretation:String(current.overall_interpretation||""),
    approved_bottom_line:String(current.bottom_line||""),
    note:"Deterministic interpretation; not a formal GRADE assessment and not a substitute for the approved synthesis."
  });
}

function evidenceAskTokens(value){
  return [...new Set(String(value||"").toLowerCase().normalize("NFKD").replace(/[\u0300-\u036f]/g,"").match(/[a-z0-9]{3,}/g)||[])];
}
function evidenceAskScore(card,question,rel){
  const q=evidenceAskTokens(question); if(!q.length)return 0;
  const fields=[card.title,card.study_purpose,card.population,card.intervention,card.comparator,Array.isArray(card.primary_outcomes)?card.primary_outcomes.join(" "):card.primary_outcomes,card.main_result,card.effect_direction,card.publication_type].join(" ").toLowerCase().normalize("NFKD").replace(/[\u0300-\u036f]/g,"");
  let score=rel==="direct"?5:rel==="supporting"?2:0;
  for(const t of q){if(fields.includes(t))score+=2;if(String(card.title||"").toLowerCase().includes(t))score+=2;}
  return score;
}
async function handleEvidenceAsk(request,env){
  if(!env.SITE_ADMIN)return jsonResponse({error:"Evidence Lab storage (SITE_ADMIN) is not configured."},503);
  if(!env.GROQ_API_KEY)return jsonResponse({error:"GROQ_API_KEY is not configured."},503);
  const body=await request.json().catch(()=>({})), slug=evidenceLabSlug(body.area), question=String(body.question||"").replace(/\s+/g," ").trim();
  if(!slug)return jsonResponse({error:"Clinical area is required."},400);
  if(question.length<4)return jsonResponse({error:"Enter a specific evidence question."},400);
  if(question.length>1200)return jsonResponse({error:"Question is too long (maximum 1200 characters)."},400);
  const idx=await evidenceLabIndex(request,env), area=idx.areas.find(a=>a.slug===slug);if(!area)return jsonResponse({error:"Clinical area not found."},404);
  const review={...evidenceReviewDefault(),...((await env.SITE_ADMIN.get(EVIDENCE_LAB_REVIEW_PREFIX+slug,"json"))||{})};
  const current=await evidenceReviewSnapshot(request,env,slug);if(!current)return jsonResponse({error:"A saved synthesis is required before Ask the Evidence is available."},409);
  const changes=evidenceReviewDiff(review.approved_snapshot,current);
  if(review.status!=="approved" || !review.approved_snapshot || changes.has_changes)return jsonResponse({error:"Ask the Evidence requires a current approved synthesis. Review and approve the current evidence state first.",code:"approval_required"},409);
  const st=await evidenceLabState(env,slug), candidates=[];
  const processedIds=(st.processed||[]).map(String);
  let workCards=[];
  if(area.count>EVIDENCE_LAB_LARGE_CORPUS_THRESHOLD || processedIds.length>EVIDENCE_LAB_LARGE_CORPUS_THRESHOLD){const compact=await evidenceCompactLoad(env,slug);workCards=processedIds.map(p=>compact.get(p)).filter(Boolean);}
  else{for(const pmid of processedIds){const c=await env.SITE_ADMIN.get(EVIDENCE_LAB_CARD_PREFIX+slug+":"+pmid,"json");if(c)workCards.push(c);}}
  for(const c of workCards){
    const pmid=String(c.pmid||"");
    if(!c || !(c.source_level==="abstract"||c.source_level==="full_text"))continue;
    const rel=evidenceRelevance(c,area.label);if(rel.level==="exclude")continue;
    const score=evidenceAskScore(c,question,rel.level);
    candidates.push({score,rel:rel.level,card:c});
  }
  candidates.sort((a,b)=>b.score-a.score || (a.rel==="direct"?-1:1));
  let selected=candidates.filter(x=>x.score>0).slice(0,12);
  if(!selected.length)selected=candidates.filter(x=>x.rel==="direct").slice(0,8);
  if(!selected.length)return jsonResponse({answer:"The current approved Evidence Lab corpus does not contain evidence-bearing cards that can answer this question.",claims:[],pmids:[],support_level:"not_supported",cards_considered:0});
  const allowed=new Set(selected.map(x=>String(x.card.pmid||"")));
  const packet={area:area.label,question,approved_overall_interpretation:current.overall_interpretation,approved_bottom_line:current.bottom_line,evidence:selected.map(x=>({pmid:String(x.card.pmid||""),relevance:x.rel,publication_type:x.card.publication_type,study_design:x.card.study_design,study_purpose:x.card.study_purpose,population:x.card.population,sample_size:x.card.sample_size||x.card.sample_size_details,intervention:x.card.intervention,comparator:x.card.comparator,duration:x.card.duration,primary_outcomes:x.card.primary_outcomes,effect_direction:x.card.effect_direction,statistical_significance:x.card.statistical_significance,main_result:x.card.main_result,limitations:x.card.limitations,source_level:x.card.source_level}))};
  const system=`You answer questions for a PRIVATE scientific Evidence Lab. Use ONLY the supplied approved synthesis boundaries and Evidence Cards. Do not use outside knowledge. Do not infer unreported facts. Answer in the SAME LANGUAGE as the user's question, including summary, claims and caveat. Distinguish direct human evidence from supporting/contextual evidence. Never turn association, feasibility, safety or mechanistic evidence into efficacy. If the supplied cards do not support the requested point, say so explicitly. The approved bottom line is a hard clinical boundary and must not be strengthened. When support_level is mixed, the summary MUST state that the evidence/findings are mixed, non-uniform, or inconsistent, then briefly describe favorable and null/uncertain findings; NEVER use the words discordant, discordance, discordante, or discordanti for a mixed result, because Discordant is a separate Evidence Lab taxonomy state; do not summarize mixed evidence as an overall benefit. Return ONLY JSON with this exact structure: {"summary":"1-3 concise sentences","claims":[{"text":"one factual evidence statement","pmids":["12345678"]}],"support_level":"direct|mixed|indirect|not_supported","caveat":"concise limitation or empty string"}. Every claim must cite one or more PMID values from the supplied evidence. Do not cite a PMID unless that specific supplied card directly supports the claim. Maximum 5 claims.`;
  let out;
  try{out=await groqJsonLimited(env,[{role:"system",content:system},{role:"user",content:JSON.stringify(packet)}],900);}
  catch(e){return jsonResponse({error:`Ask the Evidence failed: ${e?.message||"AI service error"}. No answer was saved.`},502);}
  const claims=[];
  for(const x of (Array.isArray(out?.claims)?out.claims:[]).slice(0,5)){
    const text=String(x?.text||"").replace(/\s+/g," ").trim();
    const pmids=[...new Set((Array.isArray(x?.pmids)?x.pmids:[]).map(String).filter(p=>allowed.has(p)))];
    if(text&&pmids.length)claims.push({text,pmids});
  }
  const cited=[...new Set(claims.flatMap(x=>x.pmids))];
  const support=["direct","mixed","indirect","not_supported"].includes(String(out?.support_level||""))?String(out.support_level):claims.length?"mixed":"not_supported";
  const cleanMixedTaxonomy=text=>{
    let t=String(text||"").replace(/\s+/g," ").trim();
    if(support!=="mixed")return t;
    // Keep UI/scientific taxonomy aligned with Contradiction Explorer: mixed != discordant.
    return t
      .replace(/\bdiscordant evidence\b/gi,"mixed evidence")
      .replace(/\bdiscordant findings\b/gi,"mixed findings")
      .replace(/\bdiscordance\b/gi,"mixed findings")
      .replace(/\bdiscordant\b/gi,"mixed")
      .replace(/\bdiscordanti\b/gi,"non uniformi")
      .replace(/\bdiscordante\b/gi,"non uniforme");
  };
  let summary=cleanMixedTaxonomy(out?.summary);
  if(!claims.length){summary="The supplied approved Evidence Cards do not provide enough source-locked evidence to answer this question.";}
  const safeClaims=claims.map(x=>({...x,text:cleanMixedTaxonomy(x.text)}));
  const caveat=cleanMixedTaxonomy(out?.caveat);
  return jsonResponse({area:{slug,label:area.label},question,summary,claims:safeClaims,pmids:cited,support_level:support,caveat,cards_considered:selected.length,approval:{approved_at:review.approved_at||null,current:true}});
}


const PUBLIC_EVIDENCE_PREFIX = "evidence-public:v1:";
function publicEvidenceEsc(v){return String(v??"").replace(/[&<>\"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));}
function publicEvidenceList(items,empty){const a=Array.isArray(items)?items.filter(Boolean):[];return a.length?`<ul>${a.map(x=>`<li>${publicEvidenceEsc(x)}</li>`).join("")}</ul>`:`<p>${publicEvidenceEsc(empty||"Not available.")}</p>`;}
function publicEvidencePageHtml(b){
  const area=b?.area||{}, approved=b?.source?.approved_at?new Date(b.source.approved_at).toLocaleDateString("en-GB",{year:"numeric",month:"long",day:"numeric"}):"—";
  const published=b?.published_at?new Date(b.published_at).toLocaleDateString("en-GB",{year:"numeric",month:"long",day:"numeric"}):"—";
  const fav=(b.consistent_favorable_domains||[]).map(x=>x.label||x), mixed=(b.mixed_domains||[]).map(x=>x.label||x);
  const faq=Array.isArray(b.faq)?b.faq:[];
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${publicEvidenceEsc(area.label||"Evidence Brief")} | Ketogenic Research Hub</title><meta name="description" content="Approved evidence brief from the Ketogenic Research Hub."><meta name="robots" content="index,follow"><link rel="stylesheet" href="/styles.css"><style>
  body{background:#f6f8fb;color:#18324b}.evidence-public{max-width:980px;margin:0 auto;padding:42px 22px 70px}.evidence-public .top{margin-bottom:24px}.evidence-public .k{font-size:.78rem;letter-spacing:.08em;text-transform:uppercase;font-weight:700;color:#587089}.evidence-public h1{font-size:clamp(2rem,5vw,3.4rem);line-height:1.05;margin:.25rem 0 .7rem}.evidence-public .lead{font-size:1.15rem;line-height:1.65;color:#4e6275}.evidence-public .meta{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0}.evidence-public .pill{padding:7px 11px;border-radius:999px;background:#eaf2f8;font-size:.9rem}.evidence-public .card{background:white;border:1px solid #dce5ed;border-radius:20px;padding:22px;margin:16px 0}.evidence-public .grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.evidence-public h2{font-size:1.25rem;margin:0 0 10px}.evidence-public h3{font-size:1.05rem;margin:18px 0 8px}.evidence-public p,.evidence-public li{line-height:1.62}.evidence-public ul{padding-left:22px;margin:8px 0}.evidence-public .bottom{border-left:5px solid #2b7a4b;background:#eef8f1}.evidence-public .faq details{border-top:1px solid #e2e8ee;padding:14px 0}.evidence-public .faq details:first-child{border-top:0}.evidence-public summary{cursor:pointer;font-weight:700}.evidence-public .note{font-size:.9rem;color:#66788a}.evidence-public a{color:#1f5c8f}@media(max-width:700px){.evidence-public{padding:28px 16px 52px}.evidence-public .grid{grid-template-columns:1fr}.evidence-public .card{padding:18px}}
  </style></head><body><main class="evidence-public"><div class="top"><div class="k">Ketogenic Research Hub · Approved Evidence Brief</div><h1>${publicEvidenceEsc(area.label||"")}</h1><p class="lead">${publicEvidenceEsc(b.approved_overall_interpretation||b.interpretation||"")}</p><div class="meta"><span class="pill">${publicEvidenceEsc(b.signal||"Evidence signal")}</span><span class="pill">Evidence maturity: ${publicEvidenceEsc(b.maturity||"—")}</span><span class="pill">${Number(b.direct_human_studies||0)} direct human studies</span><span class="pill">${Number(b.clinical_trials||0)} clinical trials</span></div></div>
  <section class="card"><h2>What the direct human evidence shows</h2><p>${publicEvidenceEsc(b.interpretation||"")}</p></section>
  <div class="grid"><section class="card"><h2>Most consistent favorable domains</h2>${publicEvidenceList(fav,"No domain met the consistency rule.")}</section><section class="card"><h2>Mixed / uncertain domains</h2>${publicEvidenceList(mixed,"No mixed domains identified.")}</section></div>
  <div class="grid"><section class="card"><h2>Main limitations</h2>${publicEvidenceList(b.limitations,"No limitations recorded.")}</section><section class="card"><h2>Research gaps</h2>${publicEvidenceList(b.research_gaps,"No research gaps recorded.")}</section></div>
  <section class="card bottom"><h2>Clinical bottom line</h2><p><strong>${publicEvidenceEsc(b.approved_bottom_line||"")}</strong></p><p class="note">This is a deterministic summary of the approved Evidence Lab snapshot. It is not a formal GRADE assessment and does not replace clinical judgment.</p></section>
  ${faq.length?`<section class="card faq"><h2>Questions answered by the evidence</h2>${faq.map(x=>`<details><summary>${publicEvidenceEsc(x.question)}</summary><p>${publicEvidenceEsc(x.answer)}</p></details>`).join("")}</section>`:""}
</main></body></html>`;
}
async function handleEvidencePublication(request,env,session){
  if(!env.SITE_ADMIN)return jsonResponse({error:"Evidence Lab storage (SITE_ADMIN) is not configured."},503);
  const url=new URL(request.url);let body={};if(request.method!=="GET")body=await request.json().catch(()=>({}));
  const slug=evidenceLabSlug(body.area||url.searchParams.get("area"));if(!slug)return jsonResponse({error:"Clinical area is required."},400);
  const idx=await evidenceLabIndex(request,env), area=idx.areas.find(a=>a.slug===slug);if(!area)return jsonResponse({error:"Clinical area not found."},404);
  const key=PUBLIC_EVIDENCE_PREFIX+slug, existing=await env.SITE_ADMIN.get(key,"json");
  const review={...evidenceReviewDefault(),...((await env.SITE_ADMIN.get(EVIDENCE_LAB_REVIEW_PREFIX+slug,"json"))||{})};
  const current=await evidenceReviewSnapshot(request,env,slug);
  const changes=current?evidenceReviewDiff(review.approved_snapshot,current):{has_changes:true};
  const can_publish=!!(current&&review.status==="approved"&&review.approved_snapshot&&!changes.has_changes);
  if(request.method==="GET")return jsonResponse({area:{slug,label:area.label},published:existing||null,can_publish,approval_current:can_publish,public_url:`/evidence/${slug}`});
  if(request.method!=="POST")return jsonResponse({error:"Method not allowed."},405);
  const action=String(body.action||"").toLowerCase();
  if(action==="unpublish"){await env.SITE_ADMIN.delete(key);return jsonResponse({ok:true,area:{slug,label:area.label},published:null,can_publish,public_url:`/evidence/${slug}`});}
  if(action!=="publish")return jsonResponse({error:"Action must be publish or unpublish."},400);
  if(!can_publish)return jsonResponse({error:"Only a current approved synthesis can be published. Review and approve the current evidence state first."},409);
  const cu=new URL(request.url);cu.pathname="/api/review/evidence/conclusion";cu.searchParams.set("area",slug);
  const cr=await handleEvidenceConclusion(new Request(cu.toString(),{method:"GET"}),env), conclusion=await cr.json();if(!cr.ok)return jsonResponse({error:conclusion?.error||"Unable to build the approved evidence conclusion."},cr.status||500);
  const now=new Date().toISOString(), who=String(session?.email||"administrator");
  const fav=(conclusion.consistent_favorable_domains||[]).map(x=>({domain:x.domain,label:x.label})), mixed=[...(conclusion.mixed_domains||[]),...(conclusion.discordant_domains||[])].map(x=>({domain:x.domain,label:x.label}));
  const brief={schema_version:1,area:{slug,label:area.label},published_at:now,published_by:who,source:{approved_at:review.approved_at||null,approved_by:review.approved_by||null,synthesis_generated_at:current.synthesis_generated_at||null,cards_processed_current:current.cards_processed_current||0},signal:conclusion.signal,maturity:conclusion.maturity,interpretation:conclusion.interpretation,direct_human_studies:conclusion.direct_human_studies,clinical_trials:conclusion.clinical_trials,consistent_favorable_domains:fav,mixed_domains:mixed,limitations:conclusion.limitations||[],research_gaps:conclusion.research_gaps||[],approved_overall_interpretation:conclusion.approved_overall_interpretation||"",approved_bottom_line:conclusion.approved_bottom_line||"",faq:[{question:"What does the current approved evidence suggest?",answer:conclusion.approved_overall_interpretation||conclusion.interpretation||""},{question:"How consistent is the direct human evidence?",answer:conclusion.interpretation||""},{question:"What are the main limitations?",answer:(conclusion.limitations||[]).join("; ")||"No limitations recorded in the approved synthesis."},{question:"What research is still needed?",answer:(conclusion.research_gaps||[]).join("; ")||"No research gaps recorded in the approved synthesis."},{question:"What is the approved clinical bottom line?",answer:conclusion.approved_bottom_line||""}]};
  await env.SITE_ADMIN.put(key,JSON.stringify(brief));
  return jsonResponse({ok:true,area:{slug,label:area.label},published:brief,can_publish:true,approval_current:true,public_url:`/evidence/${slug}`});
}

const EVIDENCE_LAB_SYNTHESIS_PREFIX = "evidence-lab:v2:synthesis:";
const EVIDENCE_LAB_REVIEW_PREFIX = "evidence-lab:v2:review:";

function evidenceReviewDefault(){
  return {schema_version:1,status:"draft",note:"",reviewed_at:null,reviewed_by:null,reviewed_snapshot:null,approved_at:null,approved_by:null,approved_snapshot:null,updated_at:null};
}
function evidenceClaimKey(x,label){
  const text=String(x?.[label]||"").replace(/\s+/g," ").trim().toLowerCase();
  const pmids=(Array.isArray(x?.pmids)?x.pmids:[]).map(String).sort().join(",");
  return pmids+"|"+text;
}
function evidenceReviewDiff(previous,current){
  if(!previous)return {has_changes:true,baseline:false,new_cards:current.processed_pmids||[],removed_cards:[],profile_changes:{},relevance_changes:{},main_findings_added:current.main_findings||[],main_findings_removed:[],conflicts_added:current.conflicting_evidence||[],conflicts_removed:[],overall_interpretation_changed:false,bottom_line_changed:false};
  const prevIds=new Set((previous.processed_pmids||[]).map(String)), curIds=new Set((current.processed_pmids||[]).map(String));
  const new_cards=[...curIds].filter(x=>!prevIds.has(x)), removed_cards=[...prevIds].filter(x=>!curIds.has(x));
  const objectDiff=(a,b)=>{const out={};for(const k of new Set([...Object.keys(a||{}),...Object.keys(b||{})])){const before=Number(a?.[k]||0),after=Number(b?.[k]||0);if(before!==after)out[k]={before,after,delta:after-before};}return out;};
  const claimDiff=(a,b,label)=>{const am=new Map((a||[]).map(x=>[evidenceClaimKey(x,label),x])),bm=new Map((b||[]).map(x=>[evidenceClaimKey(x,label),x]));return {added:[...bm].filter(([k])=>!am.has(k)).map(([,v])=>v),removed:[...am].filter(([k])=>!bm.has(k)).map(([,v])=>v)};};
  const findings=claimDiff(previous.main_findings,current.main_findings,"finding"), conflicts=claimDiff(previous.conflicting_evidence,current.conflicting_evidence,"issue");
  const profile_changes=objectDiff(previous.evidence_profile,current.evidence_profile), relevance_changes=objectDiff(previous.relevance_profile,current.relevance_profile);
  const overall_interpretation_changed=String(previous.overall_interpretation||"").trim()!==String(current.overall_interpretation||"").trim();
  const bottom_line_changed=String(previous.bottom_line||"").trim()!==String(current.bottom_line||"").trim();
  const has_changes=!!(new_cards.length||removed_cards.length||Object.keys(profile_changes).length||Object.keys(relevance_changes).length||findings.added.length||findings.removed.length||conflicts.added.length||conflicts.removed.length||overall_interpretation_changed||bottom_line_changed);
  return {has_changes,baseline:true,new_cards,removed_cards,profile_changes,relevance_changes,main_findings_added:findings.added,main_findings_removed:findings.removed,conflicts_added:conflicts.added,conflicts_removed:conflicts.removed,overall_interpretation_changed,bottom_line_changed};
}
async function evidenceReviewSnapshot(request,env,slug){
  const u=new URL(request.url);u.pathname="/api/review/evidence/synthesis";u.searchParams.set("area",slug);
  const r=await handleEvidenceSynthesisGet(new Request(u.toString(),{method:"GET"}),env);
  const payload=await r.json();
  if(!r.ok)throw new Error(payload?.error||"Unable to load current synthesis.");
  if(!payload?.synthesis)return null;
  const x=payload.synthesis, st=await evidenceLabState(env,slug);
  return {schema_version:1,captured_at:new Date().toISOString(),synthesis_generated_at:x.generated_at||null,synthesis_schema_version:x.schema_version||null,processed_pmids:(st.processed||[]).map(String).sort(),cards_processed_current:(st.processed||[]).length,cards_analyzed:Number(x.cards_analyzed||0),cards_excluded:Number(x.cards_excluded||0),evidence_profile:x.evidence_profile||{},relevance_profile:x.relevance_profile||{},evidence_consistency:String(x.evidence_consistency||"insufficient"),overall_interpretation:String(x.overall_interpretation||""),human_clinical:String(x.human_clinical||""),main_findings:Array.isArray(x.main_findings)?x.main_findings:[],conflicting_evidence:Array.isArray(x.conflicting_evidence)?x.conflicting_evidence:[],limitations:Array.isArray(x.limitations)?x.limitations:[],research_gaps:Array.isArray(x.research_gaps)?x.research_gaps:[],bottom_line:String(x.bottom_line||"")};
}
async function handleEvidenceReview(request,env,session){
  if(!env.SITE_ADMIN)return jsonResponse({error:"Evidence Lab storage (SITE_ADMIN) is not configured."},503);
  const url=new URL(request.url);let slug=evidenceLabSlug(url.searchParams.get("area"));
  let body={};if(request.method!=="GET"){body=await request.json().catch(()=>({}));slug=evidenceLabSlug(body.area||slug);}
  if(!slug)return jsonResponse({error:"Clinical area is required."},400);
  const idx=await evidenceLabIndex(request,env), area=idx.areas.find(a=>a.slug===slug);if(!area)return jsonResponse({error:"Clinical area not found."},404);
  const key=EVIDENCE_LAB_REVIEW_PREFIX+slug;
  const state={...evidenceReviewDefault(),...((await env.SITE_ADMIN.get(key,"json"))||{})};
  const current=await evidenceReviewSnapshot(request,env,slug);
  if(!current)return jsonResponse({error:"A saved synthesis is required before review."},409);
  if(request.method==="GET"){
    const changes=evidenceReviewDiff(state.approved_snapshot,current);
    const effective_status=state.status==="approved"&&changes.has_changes?"changes_pending_review":state.status;
    return jsonResponse({area:{slug,label:area.label},review:{...state,effective_status,approval_current:state.status==="approved"&&!changes.has_changes},changes,current});
  }
  if(request.method!=="POST")return jsonResponse({error:"Method not allowed."},405);
  const action=String(body.action||"").toLowerCase(), note=String(body.note||"").trim().slice(0,4000), now=new Date().toISOString(), who=String(session?.email||"administrator");
  if(!["review","approve","reopen"].includes(action))return jsonResponse({error:"Action must be review, approve or reopen."},400);
  if(action==="review"){state.status="reviewed";state.reviewed_at=now;state.reviewed_by=who;state.reviewed_snapshot=current;state.note=note;state.updated_at=now;}
  if(action==="approve"){
    if(state.status!=="reviewed" || !state.reviewed_snapshot)return jsonResponse({error:"Mark the current synthesis as reviewed before approval."},409);
    const sinceReview=evidenceReviewDiff(state.reviewed_snapshot,current);
    if(sinceReview.has_changes)return jsonResponse({error:"The evidence state changed after review. Review the current synthesis again before approval.",changes_since_review:sinceReview},409);
    state.status="approved";state.approved_at=now;state.approved_by=who;state.approved_snapshot=current;state.note=note;state.updated_at=now;
  }
  if(action==="reopen"){state.status="draft";state.reviewed_at=null;state.reviewed_by=null;state.reviewed_snapshot=null;state.note=note;state.updated_at=now;}
  await env.SITE_ADMIN.put(key,JSON.stringify(state));
  const changes=evidenceReviewDiff(state.approved_snapshot,current);
  return jsonResponse({ok:true,area:{slug,label:area.label},review:{...state,effective_status:state.status,approval_current:state.status==="approved"&&!changes.has_changes},changes,current});
}

function compactEvidenceCard(c){
  return {pmid:c.pmid,title:c.title,publication_type:c.publication_type,study_design:c.study_design,evidence_domain:c.evidence_domain,study_purpose:c.study_purpose,population:c.population,sample_size:c.sample_size,sample_size_details:c.sample_size_details,intervention:c.intervention,comparator:c.comparator,duration:c.duration,primary_outcomes:c.primary_outcomes,effect_direction:c.effect_direction,statistical_significance:c.statistical_significance,randomized:c.randomized,controlled:c.controlled,review_studies_included:c.review_studies_included,review_participants:c.review_participants,pooled_effect:c.pooled_effect,heterogeneity:c.heterogeneity,risk_of_bias_or_certainty:c.risk_of_bias_or_certainty,animal_species:c.animal_species,animal_model:c.animal_model,mechanistic_targets:c.mechanistic_targets,main_result:c.main_result,limitations:c.limitations,source_level:c.source_level,extraction_confidence:c.extraction_confidence};
}
async function handleEvidenceSynthesisGet(request,env){
  const url=new URL(request.url), slug=evidenceLabSlug(url.searchParams.get("area"));
  if(!slug)return jsonResponse({error:"Clinical area is required."},400);
  const saved=await env.SITE_ADMIN.get(EVIDENCE_LAB_SYNTHESIS_PREFIX+slug,"json");
  if(!saved)return jsonResponse({synthesis:null});

  // READ-ONLY source lock. Loading a saved synthesis must never invoke Groq.
  // Main findings are rendered verbatim from cached Evidence Cards. The human-clinical
  // summary is rebuilt deterministically from current card metadata so it cannot drift
  // out of sync with the source-locked findings shown immediately below it.
  const st=await evidenceLabState(env,slug);
  const idx=await evidenceLabIndex(request,env);
  const area=idx.areas.find(a=>a.slug===slug);
  const directHuman=[], mixedHuman=[];
  let deterministicHumanSummary="";
  if(area){
    const norm=v=>String(v??"").toLowerCase().replace(/\s+/g," ").trim();
    const join=v=>Array.isArray(v)?v.map(x=>typeof x==="string"?x:JSON.stringify(x)).join(" "):String(v??"");
    const isNonEfficacyOnly=c=>{
      const design=norm(c.study_design), purpose=norm(c.study_purpose), outcomes=norm(join(c.primary_outcomes)), result=norm(c.main_result), title=norm(c.title);
      const text=[design,purpose,outcomes,result,title].join(" ");
      const pharmacokinetic=/(pharmacokinetic|pharmacokinetics|\bpk\b|plasma concentration|drug absorption|levodopa kinetics)/.test(text);
      const qualitative=/(qualitative|interview|focus group|thematic analysis|acceptability barrier|adherence barrier|care partner|participant attitudes)/.test(text);
      return pharmacokinetic || qualitative;
    };
    const clinicalPriority=c=>{
      const type=String(c.publication_type||"");
      const randomized=norm(c.randomized)==="yes" ? 4 : 0;
      const controlled=norm(c.controlled)==="yes" ? 3 : 0;
      const purpose=norm(c.study_purpose);
      const purposeScore=purpose==="efficacy"?4:purpose==="mixed"?3:purpose==="feasibility"?1:0;
      const typeScore=type==="clinical_trial"?20:type==="observational"?8:0;
      return typeScore+randomized+controlled+purposeScore;
    };
    const candidates=[];
    for(const pmid of (st.processed||[]).map(String).slice(-500)){
      const c=await env.SITE_ADMIN.get(EVIDENCE_LAB_CARD_PREFIX+slug+":"+pmid,"json");
      if(!c || !(c.source_level==="abstract" || c.source_level==="full_text"))continue;
      const rel=evidenceRelevance(c,area.label);
      const type=String(c.publication_type||"");
      const humanClinical=type==="clinical_trial" || type==="observational";
      const result=String(c.main_result||"").replace(/\s+/g," ").trim();
      if(!humanClinical || rel.level!=="direct" || !result || result==="AI extraction pending" || result==="not reported" || isNonEfficacyOnly(c))continue;
      candidates.push({card:c,pmid:String(c.pmid||pmid),result,priority:clinicalPriority(c)});
    }
    candidates.sort((a,b)=>b.priority-a.priority || Number(b.card.year||0)-Number(a.card.year||0) || a.pmid.localeCompare(b.pmid));
    for(const x of candidates){
      const item={finding:x.result,pmids:[x.pmid],source:"evidence_card_verbatim"};
      directHuman.push(item);
      const signal=[x.card.effect_direction,x.card.statistical_significance,x.result].map(norm).join(" ");
      const mixedDirection=["mixed","neutral","unfavorable"].includes(norm(x.card.effect_direction));
      const nullOrMixedSignificance=["no","mixed"].includes(norm(x.card.statistical_significance));
      const explicitClinicalNull=/(no significant (?:difference|effect|improvement)|not significant|no between-group difference|no between group difference|did not (?:improve|reduce|change|affect) (?!pharmacokinetic)|failed to (?:improve|reduce|show)|comparable gains|inconsistent)/.test(signal);
      if(mixedDirection || nullOrMixedSignificance || explicitClinicalNull)
        mixedHuman.push({issue:x.result,pmids:item.pmids,source:"evidence_card_verbatim"});
    }

    // Deterministic current-state human evidence summary. No generated efficacy prose is reused.
    const profile=saved.evidence_profile||{};
    const randomizedControlled=candidates.filter(x=>String(x.card.publication_type||"")==="clinical_trial" && norm(x.card.randomized)==="yes" && norm(x.card.controlled)==="yes").length;
    const directions={favorable:0,mixed:0,neutral:0,unfavorable:0,not_reported:0};
    for(const x of candidates){
      const d=norm(x.card.effect_direction).replace(/\s+/g,"_");
      if(Object.prototype.hasOwnProperty.call(directions,d))directions[d]++; else directions.not_reported++;
    }
    const directionText=Object.entries(directions).filter(([,n])=>n>0).map(([k,n])=>`${k.replaceAll("_"," ")}: ${n}`).join("; ") || "not reported";
    deterministicHumanSummary=`Exact evidence profile: ${Number(profile.clinical_trial||0)} clinical trials; ${Number(profile.observational||0)} observational studies; ${Number(profile.mechanistic_human||0)} mechanistic human studies; ${Number(profile.case_report_series||0)} case reports/series. Direct ketogenic/ketone human clinical evidence eligible for source-locked findings: ${candidates.length} studies, including ${randomizedControlled} randomized controlled trials. Evidence-card direction labels: ${directionText}. Main findings below reproduce each Evidence Card main_result verbatim; mixed or null comparative results are shown separately under Conflicting evidence.`;
  }
  const out={...saved};
  out.schema_version=23;
  out.claim_generation="deterministic_verbatim_clinical_hierarchy_v23";
  out.human_clinical_generation="deterministic_from_current_evidence_cards";
  if(deterministicHumanSummary)out.human_clinical=deterministicHumanSummary;
  out.main_findings=directHuman.slice(0,8);
  out.conflicting_evidence=mixedHuman.slice(0,6);
  return jsonResponse({synthesis:out});
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
  if(ids.length<1)return jsonResponse({error:"At least 1 Evidence Card is required for a provisional synthesis."},400);

  const largeCorpus=area.count>EVIDENCE_LAB_LARGE_CORPUS_THRESHOLD || ids.length>EVIDENCE_LAB_LARGE_CORPUS_THRESHOLD;
  let raw=[];
  if(largeCorpus){
    const compact=await evidenceCompactLoad(env,slug);
    const missing=ids.filter(p=>!compact.has(String(p)));
    if(missing.length){
      const backfill=[];
      for(const pmid of missing.slice(0,24)){const c=await env.SITE_ADMIN.get(EVIDENCE_LAB_CARD_PREFIX+slug+":"+pmid,"json");if(c)backfill.push(c);}
      if(backfill.length)await evidenceCompactPutMany(env,slug,backfill);
      return jsonResponse({ok:true,done:false,progress:{phase:"large_index",completed:ids.length-missing.length+backfill.length,total:ids.length,cards_processed:ids.length,message:`Large Corpus index: ${Math.min(ids.length,ids.length-missing.length+backfill.length)}/${ids.length} cards prepared. No AI call was made.`}});
    }
    raw=ids.map(p=>compact.get(String(p))).filter(Boolean);
  }else{
    for(const pmid of ids){const c=await env.SITE_ADMIN.get(EVIDENCE_LAB_CARD_PREFIX+slug+":"+pmid,"json");if(c)raw.push(c);}
  }
  if(raw.length<1)return jsonResponse({error:"No readable Evidence Cards are available for synthesis."},400);

  const counts={clinical:0,review:0,preclinical:0,mechanistic:0,other:0,abstract:0,metadata:0};
  for(const c of raw){const d=String(c.evidence_domain||"other"); counts[d]=(counts[d]||0)+1; counts[c.source_level==="abstract"?"abstract":"metadata"]++;}
  const evidenceBearing=raw.filter(c=>c.source_level==="abstract" || c.source_level==="full_text");
  const excluded=raw.filter(c=>!(c.source_level==="abstract" || c.source_level==="full_text")).map(c=>({pmid:String(c.pmid||""),title:String(c.title||""),reason:"metadata-only / no evidence-bearing abstract or full text"}));
  if(evidenceBearing.length<1)return jsonResponse({error:"No evidence-bearing cards are available; metadata-only records are excluded from synthesis."},400);

  // Relevance is computed deterministically from the locked Evidence Card fields. It does not
  // require another model call and therefore cannot consume synthesis TPM or drift between runs.
  const relevance_profile={direct:0,supporting:0,contextual:0,exclude:0};
  const relevance_cards=[];
  for(const c of evidenceBearing){const rel=evidenceRelevance(c,area.label); relevance_profile[rel.level]++; relevance_cards.push({card:c,...rel});}
  for(const x of relevance_cards.filter(x=>x.level==="exclude")) excluded.push({pmid:String(x.card.pmid||""),title:String(x.card.title||""),reason:x.reason});
  const usable=relevance_cards.filter(x=>x.level!=="exclude");
  if(usable.length<1)return jsonResponse({error:"No relevant evidence-bearing cards remain after relevance screening."},400);

  const evidence_profile={clinical_trial:0,observational:0,systematic_review_meta_analysis:0,narrative_review:0,preclinical_animal:0,mechanistic_human:0,mechanistic_preclinical:0,case_report_series:0,protocol:0,other:0};
  for(const x of usable){const k=String(x.card.publication_type||"other"); if(Object.prototype.hasOwnProperty.call(evidence_profile,k))evidence_profile[k]++; else evidence_profile.other++;}

  const clip=(v,n)=>String(v??"").replace(/\s+/g," ").trim().slice(0,n);
  const arr=(v,n=4,m=90)=>Array.isArray(v)?v.slice(0,n).map(x=>clip(typeof x==="string"?x:(x?.outcome||x?.name||JSON.stringify(x)),m)).filter(Boolean):[];
  const nano=usable.map(x=>{const c=x.card;return {
    p:String(c.pmid||""), rel:x.level,
    t:clip(c.publication_type||"other",40), d:clip(c.study_design||"",32), n:clip(c.sample_size||c.sample_size_details||"",22),
    pop:clip(c.population||"",48), i:clip(c.intervention||"",48), cmp:clip(c.comparator||"",32), dur:clip(c.duration||"",18),
    o:arr(c.primary_outcomes,2,38), dir:clip(c.effect_direction||"",12), sig:clip(c.statistical_significance||"",10),
    r:clip(c.main_result||c.pooled_effect||"",105), lim:clip(c.limitations||c.risk_of_bias_or_certainty||"",55)
  }});
  const profileLabels={clinical_trial:"clinical trials",observational:"observational studies",systematic_review_meta_analysis:"systematic reviews/meta-analyses",narrative_review:"narrative reviews",preclinical_animal:"preclinical animal studies",mechanistic_human:"mechanistic human studies",mechanistic_preclinical:"mechanistic preclinical studies",case_report_series:"case reports/series",protocol:"protocols",other:"other"};
  const exactProfile=Object.fromEntries(Object.entries(evidence_profile).map(([k,v])=>[profileLabels[k]||k,v]));
  const relevanceAudit=relevance_cards.map(x=>({pmid:String(x.card.pmid||""),title:String(x.card.title||""),level:x.level,reason:x.reason}));
  // Hierarchical synthesis: bounded chunks, persisted checkpoints, then a compact final pass.
  // This keeps every included card represented without exceeding a single-request TPM envelope.
  const chunkSize=largeCorpus?20:10;
  const stratumOf=x=>["clinical_trial","observational","mechanistic_human","case_report_series"].includes(x.t)?"human":["systematic_review_meta_analysis","narrative_review"].includes(x.t)?"reviews":["preclinical_animal","mechanistic_preclinical"].includes(x.t)?"preclinical":"other";
  const ordered=[]; for(const k of ["human","reviews","preclinical","other"])ordered.push(...nano.filter(x=>stratumOf(x)===k));
  const chunks=[]; for(let i=0;i<ordered.length;i+=chunkSize) chunks.push(ordered.slice(i,i+chunkSize));
  const checkpointKey=`evidence-lab:v2:synthesis-checkpoint:${slug}:v14`;
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
  // TPM-safe final packets. The full chunk summaries remain in KV, but the two final AI calls
  // receive a bounded digest so one request cannot consume most of the 8k TPM allowance.
  // Final packets are compacted deterministically instead of aborting on size.
  // Every chunk remains represented; only redundant prose is shortened. PMID traceability is
  // preserved in the claims packet, while the full chunk summaries remain safely stored in KV.
  const narrativeDigest=chunkSummaries.map(x=>({chunk:x.chunk,summary:String(x.summary||"").slice(0,320)}));
  const claimsDigest=chunkSummaries.map(x=>({chunk:x.chunk,pmids:x.pmids,summary:String(x.summary||"").slice(0,500)}));
  const finalNarrativePacket=JSON.stringify({area:area.label,profile:exactProfile,relevance:relevance_profile,chunks:narrativeDigest});
  const finalClaimsPacket=JSON.stringify({area:area.label,allowed_pmids:nano.map(x=>x.p),chunks:claimsDigest});
  // Finalization is also incremental. Never keep the browser waiting for the entire final synthesis.
  // Phase A generates narrative prose, Phase B generates source-locked findings/conflicts,
  // Phase C assembles + validates + saves without any AI call.
  checkpoint.final = checkpoint.final && typeof checkpoint.final === "object" ? checkpoint.final : {};
  const finalNarrativeSystem=`Produce a PRIVATE provisional scientific synthesis using ONLY the supplied digest. Do not output JSON and do not output PMID numbers. Do not recalculate study counts. Keep direct, supporting and contextual evidence distinct; do not present preclinical findings as clinical efficacy. Output EXACTLY eight labelled lines and nothing else:
OVERALL: one concise sentence
CONSISTENCY: exactly one of consistent, mostly_consistent, mixed, conflicting, insufficient
HUMAN: concise human evidence synthesis
REVIEWS: concise review evidence synthesis
PRECLINICAL: concise preclinical/mechanistic synthesis
LIMITATIONS: semicolon-separated short items
GAPS: semicolon-separated short items
BOTTOM: one concise sentence`;
  if(!checkpoint.final.narrative){
    let part;
    try{const txt=await groqTextSingle(env,[{role:"system",content:finalNarrativeSystem},{role:"user",content:finalNarrativePacket}],520);part=parseFinalNarrativeText(txt);}
    catch(e){return jsonResponse({error:`Evidence synthesis final narrative stage failed: ${e?.message||"AI service error"}. All chunk checkpoints were preserved.`,diagnostic:{cards_processed:raw.length,cards_usable:usable.length,completed_chunks:chunks.length,final_packet_chars:finalNarrativePacket.length},progress:{phase:"final_narrative",completed:0,total:2}},502);}
    checkpoint.final.narrative=part;
    checkpoint.final.claims_not_before=Date.now()+65000;
    try{await env.SITE_ADMIN.put(checkpointKey,JSON.stringify(checkpoint),{expirationTtl:86400});}
    catch(e){return jsonResponse({error:`Final narrative generated but checkpoint save failed: ${e?.message||"storage error"}`},500);}
    return jsonResponse({ok:true,done:false,progress:{phase:"final_narrative",completed:1,total:2,message:"Final narrative checkpoint saved"}});
  }
  const finalClaimsSystem=`Extract ONLY source-locked claims from the supplied digest. Do not output JSON. Every line must have one of these exact formats:
F|PMID[,PMID]|finding text
C|PMID[,PMID]|conflicting-evidence text
Use only PMID values present in allowed_pmids and only when the digest directly supports the claim. Omit any unsourced claim. Maximum 8 F lines and 6 C lines. No headings, bullets, commentary or other text.`;
  if(!checkpoint.final.claims){
    const notBefore=Number(checkpoint.final.claims_not_before||0);
    if(notBefore>Date.now()){
      const waitSeconds=Math.max(1,Math.ceil((notBefore-Date.now())/1000));
      return jsonResponse({ok:true,done:false,progress:{phase:"tpm_cooldown",completed:1,total:2,wait_seconds:waitSeconds,message:`Narrative saved. Waiting ${waitSeconds}s for a fresh Groq TPM window; no AI call was made.`}});
    }
    let part;
    try{const txt=await groqTextSingle(env,[{role:"system",content:finalClaimsSystem},{role:"user",content:finalClaimsPacket}],480);part=parseFinalClaimsText(txt);}
    catch(e){return jsonResponse({error:`Evidence synthesis source-lock stage failed: ${e?.message||"AI service error"}. Narrative and chunk checkpoints were preserved.`,diagnostic:{cards_processed:raw.length,cards_usable:usable.length,completed_chunks:chunks.length,final_packet_chars:finalClaimsPacket.length},progress:{phase:"final_claims",completed:1,total:2}},502);}
    checkpoint.final.claims=part;
    try{await env.SITE_ADMIN.put(checkpointKey,JSON.stringify(checkpoint),{expirationTtl:86400});}
    catch(e){return jsonResponse({error:`Source-locked claims generated but checkpoint save failed: ${e?.message||"storage error"}`},500);}
    return jsonResponse({ok:true,done:false,progress:{phase:"final_claims",completed:2,total:2,message:"Source-lock checkpoint saved; next request assembles without AI"}});
  }
  const out={...(checkpoint.final.narrative||{}),...(checkpoint.final.claims||{})};

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
  const citation_validation={removed_section_sentences:[],removed_claim_citations:[],removed_uncited_claims:[]};
  const validateSection=(value,section)=>{const before=String(value||"");const after=sanitizeSection(before,section);if(after!==before)citation_validation.removed_section_sentences.push(section);return after;};
  const mapClaims=(items,label)=> (Array.isArray(items)?items:[]).slice(0,label==="finding"?8:6).map(x=>{
    const txt=String(x?.[label]||"").trim();
    const original=Array.isArray(x?.pmids)?x.pmids.map(String):[];
    const pmids=cleanPmids(original,txt);
    if(pmids.length!==original.filter(p=>allowed.has(p)).length)citation_validation.removed_claim_citations.push({type:label,text:txt.slice(0,140)});
    if(txt && pmids.length===0){citation_validation.removed_uncited_claims.push({type:label,text:txt.slice(0,180)});return null;}
    return txt?{[label]:txt,pmids}:null;
  }).filter(Boolean);
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
  const synthesis={schema_version:19,area_slug:slug,area_label:area.label,generated_at:new Date().toISOString(),library_total:area.count,cards_processed:raw.length,cards_analyzed:usable.length,cards_excluded:excluded.length,cards_sent_to_model:nano.length,cards_synthesized:nano.length,synthesis_chunks:chunks.length,excluded_cards:excluded,evidence_profile,relevance_profile,relevance_cards:relevanceAudit,counts,citation_validation,evidence_consistency:String(out?.evidence_consistency||"insufficient"),overall_interpretation:stripModelCitations(out?.overall_interpretation),human_clinical:lockedSection(out?.human_clinical,"human",humanPrefix),reviews_meta_analyses:lockedSection(out?.reviews_meta_analyses,"reviews",reviewPrefix),preclinical_mechanistic:lockedSection(out?.preclinical_mechanistic,"preclinical",preclinicalPrefix),main_findings:mapClaims(out?.main_findings,"finding").map(x=>({finding:stripModelCitations(x.finding),pmids:x.pmids})),conflicting_evidence:mapClaims(out?.conflicting_evidence,"issue").map(x=>({issue:stripModelCitations(x.issue),pmids:x.pmids})),limitations:(Array.isArray(out?.limitations)?out.limitations:[]).map(stripModelCitations).slice(0,8),research_gaps:(Array.isArray(out?.research_gaps)?out.research_gaps:[]).map(stripModelCitations).slice(0,8),bottom_line:stripModelCitations(out?.bottom_line)};
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
  const compactNew=[]; for(const src of todo){const pmid=String(src.pmid);if(extracted.has(pmid)){const saved=extracted.get(pmid);saved.pmid=pmid;saved.title=src.title;saved.doi=src.doi;saved.year=src.year;compactNew.push(saved);}}
  if(compactNew.length)await evidenceCompactPutMany(env,slug,compactNew);
  const next={processed:[...done],failed,updated_at:now};
  await env.SITE_ADMIN.put(EVIDENCE_LAB_STATE_PREFIX+slug,JSON.stringify(next));
  return jsonResponse({ok:true,processed_now:processedNow,attempted:todo.length,processed:done.size,remaining:Math.max(0,area.count-done.size),large_corpus:area.count>EVIDENCE_LAB_LARGE_CORPUS_THRESHOLD,warnings});
}


const EVIDENCE_AUTO_LEDGER_PREFIX="evidence-lab:v2:auto:ledger:";
const EVIDENCE_AUTO_CURSOR_KEY="evidence-lab:v2:auto:cursor";
function evidenceAutoInt(v,def,min,max){const n=Number(v);return Number.isFinite(n)?Math.max(min,Math.min(max,Math.floor(n))):def;}
function evidenceAutoConfig(env){return {daily_card_budget:evidenceAutoInt(env.EVIDENCE_AUTO_DAILY_CARD_BUDGET,120,1,10000),per_area_daily_cap:evidenceAutoInt(env.EVIDENCE_AUTO_AREA_DAILY_CAP,48,1,5000),batch_size:evidenceAutoInt(env.EVIDENCE_AUTO_BATCH_SIZE,6,1,10)};}
function evidenceAutoDay(d=new Date()){return d.toISOString().slice(0,10);}
async function evidenceAutoLedger(env,day=evidenceAutoDay()){
  const v=await env.SITE_ADMIN.get(EVIDENCE_AUTO_LEDGER_PREFIX+day,"json").catch(()=>null);
  return v&&typeof v==="object"?v:{date:day,attempted_total:0,processed_total:0,areas:{},last_run_at:null,last_area:null,last_error:null};
}
async function evidenceAutoSnapshot(request,env){
  if(!env.SITE_ADMIN)throw new Error("Evidence Lab storage (SITE_ADMIN) is not configured.");
  const cfg=evidenceAutoConfig(env), day=evidenceAutoDay(), ledger=await evidenceAutoLedger(env,day), idx=await evidenceLabIndex(request,env), cursor=(await env.SITE_ADMIN.get(EVIDENCE_AUTO_CURSOR_KEY,"json").catch(()=>null))||{};
  const rows=[];
  for(const a of idx.areas){
    const st=await evidenceLabState(env,a.slug), processed=(st.processed||[]).length, remaining=Math.max(0,Number(a.count||0)-processed), today=ledger.areas?.[a.slug]||{attempted:0,processed:0,runs:0};
    const weight=a.count>EVIDENCE_LAB_LARGE_CORPUS_THRESHOLD?6:(a.count>50?3:1);
    rows.push({slug:a.slug,label:a.label,total:Number(a.count||0),processed,remaining,today_attempted:Number(today.attempted||0),today_processed:Number(today.processed||0),today_runs:Number(today.runs||0),weight});
  }
  const incomplete=rows.filter(x=>x.remaining>0);
  const eligible=incomplete.filter(x=>x.today_attempted<cfg.per_area_daily_cap);
  const last=String(cursor.last_slug||""); const order=new Map(rows.map((x,i)=>[x.slug,i])); const lastIndex=order.has(last)?order.get(last):-1;
  eligible.sort((a,b)=>{
    const sa=a.today_attempted/a.weight, sb=b.today_attempted/b.weight;
    if(sa!==sb)return sa-sb;
    const da=(order.get(a.slug)-lastIndex+rows.length)%rows.length, db=(order.get(b.slug)-lastIndex+rows.length)%rows.length;
    return da-db;
  });
  return {cfg,day,ledger,idx,rows,incomplete,eligible,next:eligible[0]||null};
}
async function evidenceAutoRunOne(request,env){
  const snap=await evidenceAutoSnapshot(request,env), {cfg,ledger,day}=snap;
  if(Number(ledger.attempted_total||0)>=cfg.daily_card_budget)return {ok:true,reason:"daily_budget_reached",message:`Daily Evidence Lab budget reached (${ledger.attempted_total}/${cfg.daily_card_budget} cards attempted).`,config:cfg,today:ledger};
  const area=snap.next;
  if(!area)return {ok:true,reason:snap.incomplete.length?"per_area_caps_reached":"all_complete",message:snap.incomplete.length?"All incomplete areas reached their per-area daily cap.":"All Evidence Lab areas are complete.",config:cfg,today:ledger};
  const remainingBudget=Math.max(0,cfg.daily_card_budget-Number(ledger.attempted_total||0));
  const remainingAreaCap=Math.max(0,cfg.per_area_daily_cap-area.today_attempted);
  const batch=Math.max(1,Math.min(cfg.batch_size,remainingBudget,remainingAreaCap,area.remaining));
  const internal=new Request(new URL("/api/review/evidence/process",request.url).toString(),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({area:area.slug,batch})});
  let parsed={}; let status=500;
  try{const response=await handleEvidenceProcess(internal,env);status=response.status;parsed=await response.json();}
  catch(e){parsed={error:e?.message||String(e)};}
  const attempted=Math.max(0,Number(parsed.attempted??batch)||0), processedNow=Math.max(0,Number(parsed.processed_now||0));
  const entry=ledger.areas?.[area.slug]||{attempted:0,processed:0,runs:0};
  ledger.areas={...(ledger.areas||{}),[area.slug]:{attempted:Number(entry.attempted||0)+attempted,processed:Number(entry.processed||0)+processedNow,runs:Number(entry.runs||0)+1,last_run_at:new Date().toISOString()}};
  ledger.attempted_total=Number(ledger.attempted_total||0)+attempted;ledger.processed_total=Number(ledger.processed_total||0)+processedNow;ledger.last_run_at=new Date().toISOString();ledger.last_area=area.slug;ledger.last_error=status>=400?(parsed.error||`HTTP ${status}`):((parsed.warnings||[]).length&&!processedNow?String(parsed.warnings[0]):null);
  await env.SITE_ADMIN.put(EVIDENCE_AUTO_LEDGER_PREFIX+day,JSON.stringify(ledger));
  await env.SITE_ADMIN.put(EVIDENCE_AUTO_CURSOR_KEY,JSON.stringify({last_slug:area.slug,updated_at:ledger.last_run_at}));
  if(status>=400)return {ok:false,error:parsed.error||`Evidence batch failed (${status})`,config:cfg,today:ledger,run:{area:area.slug,area_label:area.label,attempted,processed_now:processedNow,remaining:area.remaining,warnings:parsed.warnings||[]}};
  return {ok:true,config:cfg,today:ledger,run:{area:area.slug,area_label:area.label,attempted,processed_now:processedNow,remaining:parsed.remaining,warnings:parsed.warnings||[]}};
}
async function handleEvidenceAutomation(request,env){
  if(request.method==="GET"){
    const snap=await evidenceAutoSnapshot(request,env);
    return jsonResponse({enabled:!!env.EVIDENCE_AUTOMATION_SECRET,config:snap.cfg,today:snap.ledger,incomplete_areas:snap.incomplete.length,next_area:snap.next?.slug||null,next_area_label:snap.next?.label||null,areas:snap.rows.map(x=>({slug:x.slug,label:x.label,total:x.total,processed:x.processed,remaining:x.remaining,today_attempted:x.today_attempted,today_processed:x.today_processed,weight:x.weight}))});
  }
  const body=await request.json().catch(()=>({})); if(body.action!=="run")return jsonResponse({error:"Unsupported automation action."},400);
  const out=await evidenceAutoRunOne(request,env); return jsonResponse(out,out.ok?200:503);
}
async function handleEvidenceAutomationCron(request,env){
  const secret=String(env.EVIDENCE_AUTOMATION_SECRET||""); if(!secret)return jsonResponse({error:"EVIDENCE_AUTOMATION_SECRET is not configured."},503);
  const auth=String(request.headers.get("Authorization")||""); if(auth!==`Bearer ${secret}`)return jsonResponse({error:"Unauthorized."},401);
  const out=await evidenceAutoRunOne(request,env); return jsonResponse(out,out.ok?200:503);
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

    const publicEvidenceMatch=url.pathname.match(/^\/evidence\/([a-z0-9-]+)\/?$/);
    if(publicEvidenceMatch&&request.method==="GET"){
      if(!env.SITE_ADMIN)return new Response("Not found",{status:404});
      const brief=await env.SITE_ADMIN.get(PUBLIC_EVIDENCE_PREFIX+evidenceLabSlug(publicEvidenceMatch[1]),"json");
      if(!brief)return new Response("Not found",{status:404,headers:{"X-Robots-Tag":"noindex"}});
      return new Response(publicEvidencePageHtml(brief),{headers:{"Content-Type":"text/html; charset=utf-8","Cache-Control":"public, max-age=60, stale-while-revalidate=300","X-Content-Type-Options":"nosniff"}});
    }

    if ((url.pathname === "/review-studio" || url.pathname === "/review-studio/" || url.pathname === "/review-studio.html") && request.method === "GET") {
      const auth=await requireReviewAdmin(request,env); if(!auth.ok)return auth.response;
      return serveRawHtmlAsset(request,env,"/_raw-review-studio.txt",{"Cache-Control":"private, no-store","X-Robots-Tag":"noindex,nofollow"});
    }
    if(url.pathname==="/api/evidence-automation/daily"&&request.method==="POST")return handleEvidenceAutomationCron(request,env);

    if (url.pathname.startsWith("/api/review/")) {
      const auth=await requireReviewAdmin(request,env); if(!auth.ok)return auth.response;
      try { if(url.pathname==="/api/review/evidence/automation"&&(request.method==="GET"||request.method==="POST"))return handleEvidenceAutomation(request,env); if(url.pathname==="/api/review/evidence/areas")return handleEvidenceAreas(request,env); if(url.pathname==="/api/review/evidence/status")return handleEvidenceStatus(request,env); if(url.pathname==="/api/review/evidence/map"&&request.method==="GET")return handleEvidenceMap(request,env); if(url.pathname==="/api/review/evidence/contradictions"&&request.method==="GET")return handleEvidenceContradictions(request,env); if(url.pathname==="/api/review/evidence/conclusion"&&request.method==="GET")return handleEvidenceConclusion(request,env); if(url.pathname==="/api/review/evidence/publication"&&(request.method==="GET"||request.method==="POST"))return handleEvidencePublication(request,env,auth.session); if(url.pathname==="/api/review/evidence/ask"&&request.method==="POST")return handleEvidenceAsk(request,env); if(url.pathname==="/api/review/evidence/process"&&request.method==="POST")return handleEvidenceProcess(request,env); if(url.pathname==="/api/review/evidence/synthesis"&&request.method==="GET")return handleEvidenceSynthesisGet(request,env); if(url.pathname==="/api/review/evidence/review"&&(request.method==="GET"||request.method==="POST"))return handleEvidenceReview(request,env,auth.session); if(url.pathname==="/api/review/evidence/synthesize"&&request.method==="POST")return handleEvidenceSynthesize(request,env); if(url.pathname==="/api/review/protocol")return handleProtocolApi(request,env); if(url.pathname==="/api/review/pubmed")return handlePubmedApi(request,env); if(url.pathname==="/api/review/draft")return handleDraftApi(request,env); return jsonResponse({error:"Not found"},404); } catch(e){ return jsonResponse({error:e?.message||"Review Studio error"},500); }
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
