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
  return `${name}=${encodeURIComponent(value)}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${maxAge}`;
}

function redirectToLogin(request, reason) {
  const u = new URL("/library-access.html", request.url);
  u.searchParams.set("reason", reason);
  return Response.redirect(u.toString(), 302);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // Always use the definitive custom domain.
    // This also fixes old bookmarks and stale links to the pages.dev hostname.
    if (url.hostname === "ketogenicresearch-library.pages.dev") {
      const canonical = new URL(request.url);
      canonical.hostname = "library.ketogenicresearch.org";
      canonical.protocol = "https:";
      return Response.redirect(canonical.toString(), 301);
    }

    // Normalize legacy .html links to the canonical protected route.
    if (url.pathname === "/library.html") {
      return Response.redirect("https://library.ketogenicresearch.org/library", 302);
    }

    // Browser authentication is converted into first-party HttpOnly cookies here.
    // This avoids relying on JavaScript-created cookies and prevents login loops
    // on the custom domain.
    if (url.pathname === "/auth/session" && request.method === "POST") {
      let payload;
      try {
        payload = await request.json();
      } catch {
        return Response.json({ error: "Invalid request body" }, { status: 400 });
      }

      const accessToken = payload?.access_token || "";
      const refreshToken = payload?.refresh_token || "";
      const user = await validateUser(accessToken);

      if (!user || !refreshToken) {
        return Response.json({ error: "Invalid Supabase session" }, { status: 401 });
      }

      const headers = new Headers({
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store"
      });
      headers.append("Set-Cookie", cookie("kr_access_token", accessToken, 60 * 60 * 24 * 30));
      headers.append("Set-Cookie", cookie("kr_refresh_token", refreshToken, 60 * 60 * 24 * 30));

      return new Response(JSON.stringify({ ok: true }), { status: 200, headers });
    }

    if (url.pathname === "/auth/logout" && request.method === "POST") {
      const headers = new Headers({
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store"
      });
      headers.append("Set-Cookie", "kr_access_token=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0");
      headers.append("Set-Cookie", "kr_refresh_token=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0");
      return new Response(JSON.stringify({ ok: true }), { status: 200, headers });
    }

    const protectedPath = url.pathname === "/library.html" || url.pathname === "/library" || url.pathname === "/library/";

    if (!protectedPath) {
      return env.ASSETS.fetch(request);
    }

    const cookies = parseCookies(request);
    let access = cookies.kr_access_token || "";
    let user = await validateUser(access);
    let refreshed = null;

    if (!user) {
      refreshed = await refreshSession(cookies.kr_refresh_token || "");
      if (!refreshed?.access_token) return redirectToLogin(request, "login");
      access = refreshed.access_token;
      user = await validateUser(access);
      if (!user) return redirectToLogin(request, "login");
    }

    if (!user.email_confirmed_at) return redirectToLogin(request, "email");

    const profileResponse = await fetch(
      `https://kfctugbpwmjdupmtfjen.supabase.co/rest/v1/library_profiles?user_id=eq.${encodeURIComponent(user.id)}&select=user_id&limit=1`,
      {
        headers: {
          "apikey": "sb_publishable_fz-WHqnfABeqFiTjBz8Utg_psM2G6sY",
          "Authorization": `Bearer ${access}`,
          "Accept": "application/json"
        }
      }
    );

    if (!profileResponse.ok) return redirectToLogin(request, "profile");
    const profiles = await profileResponse.json();
    if (!Array.isArray(profiles) || profiles.length === 0) return redirectToLogin(request, "profile");

    // Important: fetch the ORIGINAL request path.
    // Cloudflare Pages canonicalizes .html URLs to extensionless routes.
    // Rewriting /library back to /library.html here can create an endless
    // /library.html <-> /library redirect loop.
    const assetResponse = await env.ASSETS.fetch(request);
    const headers = new Headers(assetResponse.headers);
    headers.set("Cache-Control", "private, no-store");
    headers.set("X-Robots-Tag", "noindex, noarchive, nofollow");

    const response = new Response(assetResponse.body, {
      status: assetResponse.status,
      statusText: assetResponse.statusText,
      headers
    });

    if (refreshed?.access_token && refreshed?.refresh_token) {
      response.headers.append("Set-Cookie", cookie("kr_access_token", refreshed.access_token, 60 * 60 * 24 * 30));
      response.headers.append("Set-Cookie", cookie("kr_refresh_token", refreshed.refresh_token, 60 * 60 * 24 * 30));
    }

    return response;
  }
};
