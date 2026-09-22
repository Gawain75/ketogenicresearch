#!/usr/bin/env python3
import os
import smtplib
import ssl
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

SUPABASE_URL = "https://kfctugbpwmjdupmtfjen.supabase.co"
SUPABASE_KEY = "sb_publishable_fz-WHqnfABeqFiTjBz8Utg_psM2G6sY"

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,it;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

CHECKS = []

def request(url, *, headers=None, follow_redirects=True, timeout=20):
    merged = dict(BROWSER_HEADERS)
    if headers:
        merged.update(headers)

    req = urllib.request.Request(url, headers=merged, method="GET")

    if follow_redirects:
        opener = urllib.request.build_opener()
    else:
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, hdrs, newurl):
                return None
        opener = urllib.request.build_opener(NoRedirect)

    try:
        with opener.open(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read(1024)
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read(1024)
    except Exception as e:
        return 0, {}, str(e).encode("utf-8", errors="replace")

def add(name, ok, detail):
    CHECKS.append((name, ok, detail))

def cloudflare_reachable(status, headers):
    server = (headers.get("Server") or headers.get("server") or "").lower()
    # GitHub-hosted checks can occasionally be challenged by Cloudflare.
    # A Cloudflare-generated 403 proves the hostname/edge is reachable, so
    # don't classify it as an outage by itself.
    return status == 403 and "cloudflare" in server

# 1. Public homepage
status, headers, body = request("https://ketogenicresearch.org/")
add("Public website", status == 200, f"HTTP {status}")

# 2. Library login page
status, headers, body = request("https://library.ketogenicresearch.org/library-access")
login_ok = status == 200 or cloudflare_reachable(status, headers)
detail = f"HTTP {status}"
if cloudflare_reachable(status, headers):
    detail += " (Cloudflare edge reachable; automated request challenged)"
add("Library login page", login_ok, detail)

# 3. Protected route: anonymous request should normally redirect to login.
status, headers, body = request(
    "https://library.ketogenicresearch.org/library",
    follow_redirects=False
)
location = headers.get("Location") or headers.get("location") or ""
protected_ok = (
    status in (301, 302, 303, 307, 308)
    and "library-access" in location
) or cloudflare_reachable(status, headers)

detail = f"HTTP {status}"
if location:
    detail += f" -> {location}"
elif cloudflare_reachable(status, headers):
    detail += " (Cloudflare edge reachable; automated request challenged)"

add("Protected Library route", protected_ok, detail)

# 4. Supabase Auth health
status, headers, body = request(
    f"{SUPABASE_URL}/auth/v1/health",
    headers={
        "apikey": SUPABASE_KEY,
        "Accept": "application/json",
    }
)
add("Supabase Auth", status == 200, f"HTTP {status}")

# 5. Resend status page
status, headers, body = request("https://status.resend.com/")
add("Resend status page", status == 200, f"HTTP {status}")

now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
lines = [f"Ketogenic Research health check — {now}", ""]

for name, ok, detail in CHECKS:
    lines.append(f"{'OK' if ok else 'FAIL'} | {name} | {detail}")

failed = [item for item in CHECKS if not item[1]]

if failed:
    lines += [
        "",
        "Possible areas to inspect:",
        "- Public website: GitHub Pages / Aruba DNS",
        "- Library: Cloudflare Pages / Worker / Aruba DNS",
        "- Authentication: Supabase",
        "- Email: Resend / Supabase SMTP",
    ]

report = "\n".join(lines) + "\n"
Path("health-report.txt").write_text(report, encoding="utf-8")
print(report)

def send_alert_via_smtp(text):
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    alert_email = os.getenv("ALERT_EMAIL", "").strip()

    if not api_key or not alert_email:
        print("Alert email skipped: RESEND_API_KEY or ALERT_EMAIL not configured.")
        return False

    msg = EmailMessage()
    msg["From"] = "Ketogenic Research <noreply@ketogenicresearch.org>"
    msg["To"] = alert_email
    msg["Subject"] = "ALERT: Ketogenic Research health check"
    msg.set_content(text)

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(
            "smtp.resend.com",
            465,
            context=context,
            timeout=30,
        ) as smtp:
            smtp.login("resend", api_key)
            smtp.send_message(msg)

        print("Alert email sent successfully via Resend SMTP.")
        return True

    except Exception as exc:
        print(f"Could not send alert email via Resend SMTP: {type(exc).__name__}: {exc}")
        return False

if failed:
    send_alert_via_smtp(report)
    sys.exit(1)

sys.exit(0)
