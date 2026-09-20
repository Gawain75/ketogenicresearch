#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "library.html"
STATE = ROOT / "library-title-translation-state.json"

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip()
MAX_TITLES = max(1, int(os.getenv("TRANSLATION_BATCH_MAX", "120")))


def strip_number(value: str) -> tuple[str, str]:
    m = re.match(r"^(\s*\d+\.\s*)(.*)$", value or "")
    if m:
        return m.group(1), m.group(2).strip()
    return "", (value or "").strip()


def needs_translation(h4) -> bool:
    en = (h4.get("data-en") or h4.get_text(" ", strip=True)).strip()
    it = (h4.get("data-it") or "").strip()
    if not en:
        return False

    _, en_title = strip_number(en)
    _, it_title = strip_number(it)

    # Missing Italian or Italian identical to the English bibliographic title.
    return not it_title or it_title.casefold() == en_title.casefold()


def groq_translate(titles: list[str]) -> list[str]:
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not configured.")

    prompt = """Translate the following scientific publication titles from English into Italian.

Rules:
- Preserve scientific meaning exactly.
- Use natural professional Italian, not literal machine-like phrasing.
- Preserve gene symbols, protein names, abbreviations, drug names, chemical names, study acronyms, and proper nouns when appropriate.
- Do not add explanations, commentary, quotation marks, numbering, or citations.
- Keep each output aligned with the corresponding input.
- Return JSON only in this exact form:
{"translations":["...", "..."]}

Titles:
""" + json.dumps(titles, ensure_ascii=False)

    payload = json.dumps(
        {
            "model": GROQ_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a scientific English-to-Italian translator "
                        "specialized in clinical nutrition, metabolism, neurology "
                        "and biomedical research. Return JSON only."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "max_tokens": 7000,
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    last_error = None
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                data = json.loads(response.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            translations = parsed.get("translations") or []
            if len(translations) != len(titles):
                raise RuntimeError(
                    f"Translation count mismatch: expected {len(titles)}, got {len(translations)}"
                )
            return [str(x).strip() for x in translations]

        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code == 429 or 500 <= exc.code < 600:
                wait = min(90, max(8, 10 * (attempt + 1)))
                print(f"Groq HTTP {exc.code}; waiting {wait}s before retry.")
                time.sleep(wait)
                continue
            raise
        except (urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as exc:
            last_error = exc
            wait = min(60, 8 * (attempt + 1))
            print(f"Translation request failed; waiting {wait}s: {exc}")
            time.sleep(wait)

    raise RuntimeError(f"Translation failed after retries: {last_error}")


def main():
    soup = BeautifulSoup(LIBRARY.read_text(encoding="utf-8"), "html.parser")
    candidates = [h4 for h4 in soup.select("article.folder-paper h4") if needs_translation(h4)]
    batch = candidates[:MAX_TITLES]

    if not batch:
        STATE.write_text(
            json.dumps(
                {
                    "translated_this_run": 0,
                    "remaining_untranslated": 0,
                    "completed": True,
                },
                ensure_ascii=False,
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )
        print("All Library titles already have an Italian display title.")
        return

    source_titles = []
    prefixes = []
    for h4 in batch:
        en = (h4.get("data-en") or h4.get_text(" ", strip=True)).strip()
        prefix, title = strip_number(en)
        prefixes.append(prefix)
        source_titles.append(title)

    translated = groq_translate(source_titles)

    changed = 0
    for h4, prefix, original, italian in zip(batch, prefixes, source_titles, translated):
        italian = re.sub(r"^\s*\d+\.\s*", "", italian).strip()
        if not italian:
            continue

        # data-en remains the official bibliographic title.
        en_value = h4.get("data-en") or ((prefix + original).strip())
        h4["data-en"] = en_value
        h4["data-it"] = (prefix + italian).strip()
        changed += 1

    LIBRARY.write_text(str(soup), encoding="utf-8")

    remaining = sum(
        1
        for h4 in soup.select("article.folder-paper h4")
        if needs_translation(h4)
    )

    state = {
        "translated_this_run": changed,
        "remaining_untranslated": remaining,
        "completed": remaining == 0,
        "batch_max": MAX_TITLES,
    }
    STATE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(state, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
