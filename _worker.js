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


// --- Site Admin CMS -------------------------------------------------------
const SITE_ADMIN_CONFIG_KEY = "site-admin:config:v1";
const SITE_ADMIN_PAGE_PREFIX = "site-admin:page:";

const DEFAULT_SITE_ADMIN_CONFIG = {
  menu: [
    { id: "home", label_en: "Home", label_it: "Home", href: "index.html", visible: true, group: "main", order: 10 },
    { id: "research", label_en: "Research", label_it: "Ricerca", href: "research.html", visible: true, group: "main", order: 20 },
    { id: "library", label_en: "Scientific Library", label_it: "Biblioteca Scientifica", href: "https://library.ketogenicresearch.org/library", visible: true, group: "main", order: 30 },
    { id: "latest", label_en: "Latest Evidence", label_it: "Ultime evidenze", href: "latest.html", visible: true, group: "main", order: 40 },
    { id: "trends", label_en: "Evidence Trends", label_it: "Andamento evidenze", href: "evidence-trends.html", visible: true, group: "main", order: 50 },
    { id: "articles", label_en: "Articles", label_it: "Articoli", href: "articles.html", visible: true, group: "main", order: 60 },
    { id: "director", label_en: "Scientific Direction", label_it: "Direzione scientifica", href: "director.html", visible: true, group: "main", order: 70 },
    { id: "methodology", label_en: "Methodology", label_it: "Metodologia", href: "methodology.html", visible: true, group: "more", order: 80 },
    { id: "contact", label_en: "Contact", label_it: "Contatti", href: "contact.html", visible: true, group: "more", order: 90 }
  ]
};

function escHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}
function safeSlug(value) {
  return String(value || "").toLowerCase().trim().replace(/[^a-z0-9-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 80);
}
function safeHref(value) {
  const v = String(value || "").trim();
  if (!v) return "#";
  if (/^(https?:\/\/|\/|[a-z0-9._-]+(?:\.html)?(?:[?#].*)?$)/i.test(v)) return v;
  return "#";
}
async function getSiteAdminConfig(env) {
  if (!env.SITE_ADMIN) return structuredClone(DEFAULT_SITE_ADMIN_CONFIG);
  const stored = await env.SITE_ADMIN.get(SITE_ADMIN_CONFIG_KEY, "json");
  return stored && Array.isArray(stored.menu) ? stored : structuredClone(DEFAULT_SITE_ADMIN_CONFIG);
}
function renderMenu(config) {
  const rows = (config?.menu || []).filter(x => x && x.visible !== false).sort((a,b) => Number(a.order||0)-Number(b.order||0));
  const link = x => `<a data-en="${escHtml(x.label_en || x.label_it || "Page")}" data-it="${escHtml(x.label_it || x.label_en || "Pagina")}" href="${escHtml(safeHref(x.href))}">${escHtml(x.label_en || x.label_it || "Page")}</a>`;
  const main = rows.filter(x => x.group !== "more").map(link).join("\n");
  const moreRows = rows.filter(x => x.group === "more");
  const more = moreRows.length ? `<details class="nav-more"><summary><span data-en="More" data-it="Altro">More</span><span aria-hidden="true" class="nav-caret">▾</span></summary><div class="nav-submenu">${moreRows.map(link).join("\n")}</div></details>` : "";
  return main + "\n" + more;
}
async function applyManagedMenu(response, env) {
  const type = response.headers.get("Content-Type") || "";
  if (!type.includes("text/html") || !env.SITE_ADMIN) return response;
  const config = await getSiteAdminConfig(env);
  return new HTMLRewriter().on("nav.site-nav", { element(el) { el.setInnerContent(renderMenu(config), { html: true }); } }).transform(response);
}
function cmsPageHtml(page, config) {
  const title = escHtml(page.title || "");
  const body = String(page.body_html || "");
  const description = escHtml(page.description || "");
  const nav = renderMenu(config);
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${title} | Ketogenic Research Hub</title><meta name="description" content="${description}"><link rel="stylesheet" href="style.css"></head><body><header class="header"><div class="wrap nav"><a aria-label="Ketogenic Research Hub" class="brand" href="/index.html"><img alt="Ketogenic Research Hub" class="site-logo" src="/logo-ketogenic-research.png"></a><nav aria-label="Primary navigation" class="site-nav">${nav}</nav><div class="actions"><div class="lang"><button class="active" data-lang="en">EN</button><button data-lang="it">IT</button></div><button aria-label="Menu" class="menu">☰</button></div></div></header><main><section class="section"><div class="wrap"><article class="cms-page"><h1>${title}</h1>${body}</article></div></section></main><script src="/script.js"></script></body></html>`;
}
async function handleSiteAdminApi(request, env, url) {
  if (!env.SITE_ADMIN) return jsonResponse({ error: "SITE_ADMIN KV binding is not configured." }, 503);
  const admin = await requireReviewAdmin(request, env);
  if (!admin.ok) return admin.response;
  try {
    if (url.pathname === "/api/site-admin/config") {
      if (request.method === "GET") return withRefreshedCookies(jsonResponse(await getSiteAdminConfig(env)), admin.refreshed);
      if (request.method === "PUT") {
        const body = await request.json().catch(() => null);
        if (!body || !Array.isArray(body.menu)) return jsonResponse({ error: "Invalid menu configuration." }, 400);
        const menu = body.menu.slice(0,100).map((x,i) => ({
          id: String(x.id || `item-${i}`).slice(0,80), label_en: String(x.label_en || "").slice(0,100), label_it: String(x.label_it || "").slice(0,100),
          href: safeHref(x.href), visible: x.visible !== false, group: x.group === "more" ? "more" : "main", order: Number.isFinite(Number(x.order)) ? Number(x.order) : (i+1)*10
        }));
        const current = await getSiteAdminConfig(env); current.menu = menu;
        await env.SITE_ADMIN.put(SITE_ADMIN_CONFIG_KEY, JSON.stringify(current));
        return withRefreshedCookies(jsonResponse({ ok: true, config: current }), admin.refreshed);
      }
      return jsonResponse({ error: "Method not allowed." }, 405);
    }
    if (url.pathname === "/api/site-admin/pages") {
      if (request.method === "GET") {
        const list = await env.SITE_ADMIN.list({ prefix: SITE_ADMIN_PAGE_PREFIX });
        const pages = [];
        for (const key of list.keys) { const p = await env.SITE_ADMIN.get(key.name, "json"); if (p) pages.push(p); }
        pages.sort((a,b) => String(a.title||"").localeCompare(String(b.title||"")));
        return withRefreshedCookies(jsonResponse({ pages }), admin.refreshed);
      }
      if (request.method === "POST") {
        const b = await request.json().catch(() => ({})); const slug = safeSlug(b.slug || b.title);
        if (!slug) return jsonResponse({ error: "A valid slug is required." }, 400);
        const page = { slug, title: String(b.title||slug).slice(0,160), description: String(b.description||"").slice(0,300), body_html: String(b.body_html||""), status: b.status === "published" ? "published" : "draft", updated_at: new Date().toISOString() };
        await env.SITE_ADMIN.put(SITE_ADMIN_PAGE_PREFIX + slug, JSON.stringify(page));
        return withRefreshedCookies(jsonResponse({ ok:true, page }), admin.refreshed);
      }
      return jsonResponse({ error: "Method not allowed." }, 405);
    }
    const m = url.pathname.match(/^\/api\/site-admin\/pages\/([a-z0-9-]+)$/);
    if (m) {
      const slug = safeSlug(m[1]); const key = SITE_ADMIN_PAGE_PREFIX + slug;
      if (request.method === "GET") { const page = await env.SITE_ADMIN.get(key,"json"); return withRefreshedCookies(page ? jsonResponse({page}) : jsonResponse({error:"Page not found."},404), admin.refreshed); }
      if (request.method === "PUT") { const old = await env.SITE_ADMIN.get(key,"json"); if (!old) return jsonResponse({error:"Page not found."},404); const b=await request.json().catch(()=>({})); const page={...old,title:String(b.title??old.title).slice(0,160),description:String(b.description??old.description).slice(0,300),body_html:String(b.body_html??old.body_html),status:b.status==="published"?"published":"draft",updated_at:new Date().toISOString()}; await env.SITE_ADMIN.put(key,JSON.stringify(page)); return withRefreshedCookies(jsonResponse({ok:true,page}),admin.refreshed); }
      if (request.method === "DELETE") { await env.SITE_ADMIN.delete(key); return withRefreshedCookies(jsonResponse({ok:true}),admin.refreshed); }
      return jsonResponse({ error: "Method not allowed." }, 405);
    }
    return jsonResponse({ error: "Unknown Site Admin endpoint." }, 404);
  } catch (err) { return withRefreshedCookies(jsonResponse({ error: err?.message || "Site Admin error." }, 500), admin.refreshed); }
}
// --- /Site Admin CMS ------------------------------------------------------


export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const siteAdminPath = url.pathname === "/admin" || url.pathname === "/admin/" || url.pathname === "/admin.html";
    const siteAdminApi = url.pathname.startsWith("/api/site-admin/");
    if (siteAdminApi) return handleSiteAdminApi(request, env, url);
    if (siteAdminPath) {
      const admin = await requireReviewAdmin(request, env);
      if (!admin.ok) return admin.response;
      const assetUrl = new URL("/admin.html", request.url);
      const assetResponse = await env.ASSETS.fetch(new Request(assetUrl, request));
      const headers = new Headers(assetResponse.headers); headers.set("Cache-Control","private, no-store"); headers.set("X-Robots-Tag","noindex, noarchive,nofollow");
      return withRefreshedCookies(new Response(assetResponse.body,{status:assetResponse.status,statusText:assetResponse.statusText,headers}),admin.refreshed);
    }
    const cmsMatch = url.pathname.match(/^\/p\/([a-z0-9-]+)\/?$/);
    if (cmsMatch && env.SITE_ADMIN) {
      const page = await env.SITE_ADMIN.get(SITE_ADMIN_PAGE_PREFIX + safeSlug(cmsMatch[1]), "json");
      if (!page || page.status !== "published") return new Response("Not found", {status:404});
      const config = await getSiteAdminConfig(env);
      return new Response(cmsPageHtml(page, config), {headers:{"Content-Type":"text/html; charset=utf-8","Cache-Control":"public, max-age=60"}});
    }
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

    if (!protectedLibraryPath) return applyManagedMenu(await env.ASSETS.fetch(request), env);

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
    const protectedResponse = new Response(assetResponse.body, {
      status: assetResponse.status,
      statusText: assetResponse.statusText,
      headers
    });
    return withRefreshedCookies(await applyManagedMenu(protectedResponse, env), auth.refreshed);
  }};
