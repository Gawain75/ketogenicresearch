#!/usr/bin/env python3
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LATEST = ROOT / "latest-publications.json"

def load(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

def comparable(data):
    # Only visible Latest Evidence content determines "content update".
    return {
        "window_days": data.get("window_days"),
        "max_records": data.get("max_records"),
        "count": data.get("count"),
        "publications": data.get("publications") or [],
    }

def main():
    before_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    before = load(before_path) if before_path else {}
    current = load(LATEST)
    if not current:
        raise SystemExit("latest-publications.json is missing or invalid")

    now = (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
    )

    changed = comparable(before) != comparable(current)

    if changed:
        content_updated_at = now
    else:
        content_updated_at = (
            before.get("content_updated_at")
            or before.get("generated_at")
            or current.get("content_updated_at")
            or current.get("generated_at")
            or now
        )

    # generated_at remains for backwards compatibility.
    current["generated_at"] = now
    current["verified_at"] = now
    current["content_updated_at"] = content_updated_at

    LATEST.write_text(
        json.dumps(current, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("Evidence verification:", now)
    print("Visible content changed:", changed)
    print("Content updated:", content_updated_at)

if __name__ == "__main__":
    main()
