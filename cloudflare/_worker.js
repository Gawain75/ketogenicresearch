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

const SUPABASE_URL = "https://kfctugbpwmjdupmtfjen.supabase.co";
const SUPABASE_ISSUER = `${SUPABASE_URL}/auth/v1`;
const SUPABASE_JWKS = `${SUPABASE_URL}/auth/v1/.well-known/jwks.json`;
const SUPABASE_PUBLISHABLE_KEY = SUPABASE_PUBLISHABLE_KEY;

let jwksCache = { keys: [], expiresAt: 0 };

function b64urlToBytes(value) {
  const pad = "=".repeat((4 - (value.length % 4)) % 4);
  const base64 = value.replace(/-/g, "+").replace(/_/g, "/") + pad;
  const raw = atob(base64);
  return Uint8Array.from(raw, c => c.charCodeAt(0));
}

function decodeJwtPart(value) {
  return JSON.parse(new TextDecoder().decode(b64urlToBytes(value)));
}

async function getJwks() {
  const now = Date.now();
  if (jwksCache.keys.length && jwksCache.expiresAt > now) return jwksCache.keys;

  const r = await fetch(SUPABASE_JWKS, {
    headers: { "Cache-Control": "no-cache" }
  });
  if (!r.ok) throw new Error("JWKS unavailable");

  const data = await r.json();
  const keys = Array.isArray(data?.keys) ? data.keys : [];
  if (!keys.length) throw new Error("No asymmetric signing keys available");

  // Supabase documents a 10-minute edge cache. Keep our own cache slightly shorter.
  jwksCache = { keys, expiresAt: now + 8 * 60 * 1000 };
  return keys;
}

async function verifyJwtWithJwk(token, header, signingInput, signature) {
  const keys = await getJwks();
  const jwk = keys.find(k => k.kid === header.kid && (!k.alg || k.alg === header.alg));
  if (!jwk) return null;

  let algorithm;
  if (header.alg === "ES256") {
    algorithm = { name: "ECDSA", namedCurve: "P-256", hash: "SHA-256" };
  } else if (header.alg === "RS256") {
    algorithm = { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" };
  } else {
    return null;
  }

  const key = await crypto.subtle.importKey(
    "jwk",
    jwk,
    algorithm,
    false,
    ["verify"]
  );

  const ok = await crypto.subtle.verify(
    algorithm,
    key,
    signature,
    new TextEncoder().encode(signingInput)
  );

  return ok;
}

async function verifyAccessToken(accessToken) {
  if (!accessToken) return null;

  const parts = accessToken.split(".");
  if (parts.length !== 3) return null;

  let header, payload;
  try {
    header = decodeJwtPart(parts[0]);
    payload = decodeJwtPart(parts[1]);
  } catch {
    return null;
  }

  const now = Math.floor(Date.now() / 1000);
  if (!payload.exp || payload.exp <= now) return null;
  if (payload.iss !== SUPABASE_ISSUER) return null;

  const aud = Array.isArray(payload.aud) ? payload.aud : [payload.aud];
  if (!aud.includes("authenticated")) return null;

  // New Supabase projects use asymmetric signing keys. Verify locally at the edge.
  if (header.alg === "ES256" || header.alg === "RS256") {
    try {
      const ok = await verifyJwtWithJwk(
        accessToken,
        header,
        `${parts[0]}.${parts[1]}`,
        b64urlToBytes(parts[2])
      );
      return ok ? payload : null;
    } catch {
      return null;
    }
  }

  // Legacy HS256 fallback: validate with Supabase Auth only when necessary.
  if (header.alg === "HS256") {
    const r = await fetch(`${SUPABASE_URL}/auth/v1/user`, {
      headers: {
        "apikey": SUPABASE_PUBLISHABLE_KEY,
        "Authorization": `Bearer ${accessToken}`
      }
    });
    if (!r.ok) return null;
    const user = await r.json();
    return {
      ...payload,
      sub: user.id || payload.sub,
      email: user.email || payload.email
    };
  }

  return null;
}

async function refreshSession(refreshToken) {
  if (!refreshToken) return null;
  const r = await fetch(`${SUPABASE_URL}/auth/v1/token?grant_type=refresh_token`, {
    method: "POST",
    headers: {
      "apikey": SUPABASE_PUBLISHABLE_KEY,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ refresh_token: refreshToken })
  });
  if (!r.ok) return null;
  return r.json();
}

async function fetchOwnProfile(accessToken, fields = "user_id,first_name,last_name,email") {
  if (!accessToken) return { ok: false, status: 401, rows: [] };

  const r = await fetch(
    `${SUPABASE_URL}/rest/v1/library_profiles?select=${encodeURIComponent(fields)}&limit=1`,
    {
      headers: {
        "apikey": SUPABASE_PUBLISHABLE_KEY,
        "Authorization": `Bearer ${accessToken}`,
        "Accept": "application/json"
      }
    }
  );

  let rows = [];
  if (r.ok) {
    try { rows = await r.json(); } catch {}
  }

  return { ok: r.ok, status: r.status, rows };
}

async function profileExistsCached(accessToken, userId) {
  if (!accessToken || !userId) return { ok: false, status: 401, exists: false };

  const cache = caches.default;
  const cacheKey = new Request(
    `https://library-profile-cache.invalid/${encodeURIComponent(userId)}`,
    { method: "GET" }
  );

  const cached = await cache.match(cacheKey);
  if (cached) {
    return { ok: true, status: 200, exists: true };
  }

  const result = await fetchOwnProfile(accessToken, "user_id");
  if (!result.ok) return { ok: false, status: result.status, exists: false };

  const exists = Array.isArray(result.rows) && result.rows.length > 0;
  if (exists) {
    await cache.put(
      cacheKey,
      new Response("1", {
        headers: { "Cache-Control": "public, max-age=300" }
      })
    );
  }

  return { ok: true, status: 200, exists };
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
      const claims = await verifyAccessToken(accessToken);

      if (!claims?.sub || !refreshToken) {
        return Response.json({ error: "Invalid Supabase session" }, { status: 401 });
      }

      const profileCheck = await profileExistsCached(accessToken, claims.sub);
      if (!profileCheck.ok || !profileCheck.exists) {
        return Response.json({ error: "Library profile not available" }, { status: 403 });
      }

      const headers = new Headers({
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store"
      });
      headers.append("Set-Cookie", cookie("kr_access_token", accessToken, 60 * 60 * 24 * 30));
      headers.append("Set-Cookie", cookie("kr_refresh_token", refreshToken, 60 * 60 * 24 * 30));

      return new Response(JSON.stringify({ ok: true }), { status: 200, headers });
    }

    if (url.pathname === "/auth/me" && request.method === "GET") {
      const cookies = parseCookies(request);
      let access = cookies.kr_access_token || "";
      let refreshed = null;
      let claims = await verifyAccessToken(access);

      if (!claims) {
        refreshed = await refreshSession(cookies.kr_refresh_token || "");
        if (!refreshed?.access_token) {
          return Response.json({ authenticated: false }, {
            status: 401,
            headers: { "Cache-Control": "no-store" }
          });
        }

        access = refreshed.access_token;
        claims = await verifyAccessToken(access);
        if (!claims) {
          return Response.json({ authenticated: false }, {
            status: 401,
            headers: { "Cache-Control": "no-store" }
          });
        }
      }

      const headers = new Headers({
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store"
      });

      if (refreshed?.access_token && refreshed?.refresh_token) {
        headers.append("Set-Cookie", cookie("kr_access_token", refreshed.access_token, 60 * 60 * 24 * 30));
        headers.append("Set-Cookie", cookie("kr_refresh_token", refreshed.refresh_token, 60 * 60 * 24 * 30));
      }

      return new Response(JSON.stringify({
        authenticated: true,
        email: claims.email || "",
        first_name: "",
        last_name: ""
      }), { status: 200, headers });
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
    let refreshed = null;
    let claims = await verifyAccessToken(access);

    if (!claims) {
      refreshed = await refreshSession(cookies.kr_refresh_token || "");
      if (!refreshed?.access_token) return redirectToLogin(request, "login");

      access = refreshed.access_token;
      claims = await verifyAccessToken(access);
      if (!claims) return redirectToLogin(request, "login");
    }

    const profileCheck = await profileExistsCached(access, claims.sub);

    // Temporary backend problems should never destroy a valid login session.
    if (!profileCheck.ok) {
      return new Response(
        "Scientific Library is temporarily unavailable. Please retry in a few seconds.",
        {
          status: 503,
          headers: {
            "Content-Type": "text/plain; charset=utf-8",
            "Cache-Control": "no-store",
            "Retry-After": "5"
          }
        }
      );
    }

    if (!profileCheck.exists) {
      return redirectToLogin(request, "profile");
    }

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
