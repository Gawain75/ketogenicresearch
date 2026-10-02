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
  const u = new URL("/library-access.html", request.url);
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
  return (await env.SITE_ADMIN.get(SITE_ADMIN_CONFIG_KEY,"json")) || {menu:[]};
}
async function handleSiteAdminApi(request,env,url){
  const auth=await requireSiteAdmin(request,env); if(!auth.ok) return auth.response;
  if(!env.SITE_ADMIN) return siteAdminJson({error:"SITE_ADMIN binding non configurato."},500);
  try {
    if(url.pathname==="/api/site-admin/config") {
      if(request.method==="GET") return siteAdminJson(await getSiteAdminConfig(env));
      if(request.method==="PUT") { const b=await request.json().catch(()=>({})); const cfg={menu:Array.isArray(b.menu)?b.menu:[]}; await env.SITE_ADMIN.put(SITE_ADMIN_CONFIG_KEY,JSON.stringify(cfg)); return siteAdminJson({ok:true,config:cfg}); }
    }
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

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname.startsWith("/api/site-admin/")) return handleSiteAdminApi(request, env, url);

    if ((url.pathname === "/admin" || url.pathname === "/admin/") && request.method === "GET") {
      const auth = await requireSiteAdmin(request, env); if (!auth.ok) return auth.response;
      const assetUrl = new URL("/admin.html", request.url);
      const r = await env.ASSETS.fetch(new Request(assetUrl, request));
      const h = new Headers(r.headers); h.set("Cache-Control","private, no-store"); h.set("X-Robots-Tag","noindex, noarchive,nofollow");
      return new Response(r.body,{status:r.status,statusText:r.statusText,headers:h});
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
      url.pathname === "/library/";

    if (!protectedPath) {
      return env.ASSETS.fetch(request);
    }

    const cookies = parseCookies(request);
    const session = await verifySession(cookies.kr_session || "", env.SESSION_SECRET);

    if (!session) {
      return redirectToLogin(request, "login");
    }

    const assetResponse = await env.ASSETS.fetch(request);
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
