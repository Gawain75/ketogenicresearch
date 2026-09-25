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

async function validateUser(accessToken) {
  if (!accessToken) return null;
  const r = await fetch("https://kfctugbpwmjdupmtfjen.supabase.co/auth/v1/user", {
    headers: {
      "apikey": "sb_publishable_fz-WHqnfABeqFiTjBz8Utg_psM2G6sY",
      "Authorization": `Bearer ${accessToken}`
    }
  });
  if (!r.ok) return null;
  return r.json();
}

async function refreshSession(refreshToken) {
  if (!refreshToken) return null;
  const r = await fetch("https://kfctugbpwmjdupmtfjen.supabase.co/auth/v1/token?grant_type=refresh_token", {
    method: "POST",
    headers: {
      "apikey": "sb_publishable_fz-WHqnfABeqFiTjBz8Utg_psM2G6sY",
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ refresh_token: refreshToken })
  });
  if (!r.ok) return null;
  return r.json();
}

function cookie(name, value, maxAge) {
  return `${name}=${encodeURIComponent(value)}; Path=/; Secure; SameSite=Lax; Max-Age=${maxAge}`;
}

function redirectToLogin(request, reason) {
  const u = new URL("/library-access.html", request.url);
  u.searchParams.set("reason", reason);
  return Response.redirect(u.toString(), 302);
}


function isReviewAdmin(user, env) {
  const allowed = String(env.REVIEW_ADMIN_EMAILS || "")
    .split(",")
    .map(x => x.trim().toLowerCase())
    .filter(Boolean);
  return !!user?.email && allowed.includes(String(user.email).toLowerCase());
}

async function authenticatedUser(request) {
  const cookies = parseCookies(request);
  let access = cookies.kr_access_token || "";
  let user = await validateUser(access);
  let refreshed = null;

  if (!user) {
    refreshed = await refreshSession(cookies.kr_refresh_token || "");
    if (!refreshed?.access_token) return { user: null, access: "", refreshed: null };
    access = refreshed.access_token;
    user = await validateUser(access);
  }
  return { user, access, refreshed };
}

function withRefreshedCookies(response, refreshed) {
  if (refreshed?.access_token && refreshed?.refresh_token) {
    response.headers.append("Set-Cookie", cookie("kr_access_token", refreshed.access_token, 60 * 60 * 24 * 30));
    response.headers.append("Set-Cookie", cookie("kr_refresh_token", refreshed.refresh_token, 60 * 60 * 24 * 30));
  }
  return response;
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
  const auth = await authenticatedUser(request);
  if (!auth.user || !auth.user.email_confirmed_at) return { ok: false, response: redirectToLogin(request, "login"), ...auth };
  if (!isReviewAdmin(auth.user, env)) return { ok: false, response: jsonResponse({ error: "Administrator access required." }, 403), ...auth };
  return { ok: true, ...auth };
}

function extractJsonObject(text) {
  const raw = String(text || "").trim();
  try { return JSON.parse(raw); } catch {}
  const first = raw.indexOf("{");
  const last = raw.lastIndexOf("}");
  if (first >= 0 && last > first) return JSON.parse(raw.slice(first, last + 1));
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


export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const protectedLibraryPath = url.pathname === "/library.html" || url.pathname === "/library" || url.pathname === "/library/";
    const protectedReviewPath = url.pathname === "/review-studio.html" || url.pathname === "/review-studio" || url.pathname === "/review-studio/";
    const reviewApi = url.pathname.startsWith("/api/review/");

    if (reviewApi) {
      if (request.method !== "POST") return jsonResponse({ error: "Method not allowed." }, 405);
      const admin = await requireReviewAdmin(request, env);
      if (!admin.ok) return admin.response;
      try {
        let response;
        if (url.pathname === "/api/review/protocol") response = await handleProtocolApi(request, env);
        else if (url.pathname === "/api/review/pubmed") response = await handlePubmedApi(request, env);
        else if (url.pathname === "/api/review/draft") response = await handleDraftApi(request, env);
        else response = jsonResponse({ error: "Unknown Review Studio endpoint." }, 404);
        return withRefreshedCookies(response, admin.refreshed);
      } catch (err) {
        return withRefreshedCookies(jsonResponse({ error: err?.message || "Review Studio API error." }, 500), admin.refreshed);
      }
    }

    if (protectedReviewPath) {
      const admin = await requireReviewAdmin(request, env);
      if (!admin.ok) return admin.response;
      const assetResponse = await env.ASSETS.fetch(request);
      const headers = new Headers(assetResponse.headers);
      headers.set("Cache-Control", "private, no-store");
      headers.set("X-Robots-Tag", "noindex, noarchive, nofollow");
      return withRefreshedCookies(new Response(assetResponse.body, { status: assetResponse.status, statusText: assetResponse.statusText, headers }), admin.refreshed);
    }

    if (!protectedLibraryPath) return env.ASSETS.fetch(request);

    const auth = await authenticatedUser(request);
    if (!auth.user) return redirectToLogin(request, "login");
    if (!auth.user.email_confirmed_at) return redirectToLogin(request, "email");

    const profileResponse = await fetch(
      `https://kfctugbpwmjdupmtfjen.supabase.co/rest/v1/library_profiles?user_id=eq.${encodeURIComponent(auth.user.id)}&select=user_id&limit=1`,
      {
        headers: {
          "apikey": "sb_publishable_fz-WHqnfABeqFiTjBz8Utg_psM2G6sY",
          "Authorization": `Bearer ${auth.access}`,
          "Accept": "application/json"
        }
      }
    );

    if (!profileResponse.ok) return redirectToLogin(request, "profile");
    const profiles = await profileResponse.json();
    if (!Array.isArray(profiles) || profiles.length === 0) return redirectToLogin(request, "profile");

    const assetResponse = await env.ASSETS.fetch(request);
    const headers = new Headers(assetResponse.headers);
    headers.set("Cache-Control", "private, no-store");
    headers.set("X-Robots-Tag", "noindex, noarchive, nofollow");
    return withRefreshedCookies(new Response(assetResponse.body, {
      status: assetResponse.status,
      statusText: assetResponse.statusText,
      headers
    }), auth.refreshed);
  }};
