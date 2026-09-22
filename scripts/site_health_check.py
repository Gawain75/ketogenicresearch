#!/usr/bin/env python3
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SUPABASE_URL = "https://kfctugbpwmjdupmtfjen.supabase.co"
SUPABASE_KEY = "sb_publishable_fz-WHqnfABeqFiTjBz8Utg_psM2G6sY"

CHECKS = []

def request(url, *, headers=None, follow_redirects=True, timeout=20):
    headers = headers or {}
    req = urllib.request.Request(url, headers=headers, method="GET")

    if follow_redirects:
        opener = urllib.request.build_opener()
    else:
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, hdrs, newurl):
                return None
        opener = urllib.request.build_opener(NoRedirect)

    try:
        with opener.open(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read(512)
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read(512)

def add(name, ok, detail):
    CHECKS.append((name, ok, detail))

status, headers, body = request("https://ketogenicresearch.org/")
add("Public website", status == 200, f"HTTP {status}")

status, headers, body = request("https://library.ketogenicresearch.org/library-access")
add("Library login page", status == 200, f"HTTP {status}")

status, headers, body = request(
    "https://library.ketogenicresearch.org/library",
    follow_redirects=False
)
location = headers.get("Location", "")
library_ok = (
    status in (301, 302, 303, 307, 308)
    and "library-access" in location
) or status == 200
add(
    "Protected Library route",
    library_ok,
    f"HTTP {status}" + (f" -> {location}" if location else "")
)

status, headers, body = request(
    f"{SUPABASE_URL}/auth/v1/health",
    headers={"apikey": SUPABASE_KEY}
)
add("Supabase Auth", status == 200, f"HTTP {status}")

status, headers, body = request("https://status.resend.com/")
add("Resend status page", status == 200, f"HTTP {status}")

now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
lines = [f"Ketogenic Research health check — {now}", ""]
for name, ok, detail in CHECKS:
    lines.append(f"{'OK' if ok else 'FAIL'} | {name} | {detail}")

failed = [x for x in CHECKS if not x[1]]

if failed:
    lines += [
        "",
        "Possible areas to inspect:",
        "- Public website: GitHub Pages / DNS",
        "- Library: Cloudflare Pages / Worker / DNS",
        "- Authentication: Supabase",
        "- Email: Resend / Supabase SMTP",
    ]

report = "\n".join(lines) + "\n"
Path("health-report.txt").write_text(report, encoding="utf-8")
print(report)

def send_alert(text):
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    alert_email = os.getenv("ALERT_EMAIL", "").strip()
    if not api_key or not alert_email:
        print("Alert email skipped: RESEND_API_KEY or ALERT_EMAIL not configured.")
        return

    payload = json.dumps({
        "from": "Ketogenic Research <noreply@ketogenicresearch.org>",
        "to": [alert_email],
        "subject": "ALERT: Ketogenic Research health check",
        "text": text
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            print(f"Alert email sent: HTTP {r.status}")
    except Exception as e:
        print(f"Could not send alert email: {e}")

if failed:
    send_alert(report)
    sys.exit(1)

sys.exit(0)
