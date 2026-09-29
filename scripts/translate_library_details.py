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
STATE = ROOT / "library-details-translation-state.json"

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip()
MAX_UNIQUE = max(1, int(os.getenv("DETAIL_TRANSLATION_BATCH_MAX", "60")))
MAX_CHARS_PER_REQUEST = max(
    6000, int(os.getenv("DETAIL_TRANSLATION_MAX_CHARS", "22000"))
)


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def needs_translation(p) -> bool:
    en = clean(p.get("data-en") or p.get_text(" ", strip=True))
    it = clean(p.get("data-it") or "")
    if not en:
        return False
    # Old backfill wrote the English text into both attributes.
    return not it or it.casefold() == en.casefold()


def groq_translate(texts: list[str]) -> list[str]:
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not configured.")

    prompt = """Translate the following biomedical research-detail texts from English into Italian.

Rules:
- Translate faithfully; do not summarize, expand, interpret, or omit information.
- Preserve numbers, units, p values, confidence intervals, gene/protein symbols, drug names, study acronyms, trial identifiers, and scientific abbreviations.
- Use precise professional Italian suitable for a scientific library.
- Preserve uncertainty and limitations exactly.
- Do not add headings, bullets, citations, comments, quotation marks, or numbering.
- Return JSON only, exactly as:
{"translations":["...", "..."]}

Texts:
""" + json.dumps(texts, ensure_ascii=False)

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a scientific English-to-Italian translator "
                    "specialized in biomedical research, clinical nutrition, "
                    "metabolism and ketogenic therapies. Return JSON only."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.0,
        "max_completion_tokens": 12000,
        "reasoning_effort": "low",
        "reasoning_format": "hidden",
        "response_format": {"type": "json_object"},
    }

    encoded = json.dumps(payload).encode("utf-8")
    last_error = None

    for attempt in range(1, 6):
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=encoded,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
                "User-Agent": "KetogenicResearch/Library-Details-Translation-V1",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as response:
                data = json.loads(response.read().decode("utf-8"))

            content = data["choices"][0]["message"]["content"].strip()
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                begin = content.find("{")
                end = content.rfind("}")
                if begin < 0 or end <= begin:
                    raise RuntimeError("Translation response was not valid JSON.")
                parsed = json.loads(content[begin:end + 1])

            translations = parsed.get("translations") or []
            if len(translations) != len(texts):
                raise RuntimeError(
                    f"Translation count mismatch: expected {len(texts)}, "
                    f"got {len(translations)}"
                )

            result = [clean(str(x)) for x in translations]
            if any(not x for x in result):
                raise RuntimeError("One or more translations were empty.")
            return result

        except urllib.error.HTTPError as exc:
            last_error = exc
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                pass

            if exc.code == 429 and attempt < 5:
                retry_after = exc.headers.get("Retry-After")
                try:
                    wait = max(30, int(float(retry_after)))
                except Exception:
                    wait = 45 * attempt
                print(f"Groq 429; waiting {wait}s.")
                time.sleep(wait)
                continue

            if 500 <= exc.code < 600 and attempt < 5:
                wait = 20 * attempt
                print(f"Groq HTTP {exc.code}; waiting {wait}s.")
                time.sleep(wait)
                continue

            raise RuntimeError(
                f"Groq HTTP {exc.code}: {body[:1000]}"
            ) from exc

        except (urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt >= 5:
                raise
            wait = 20 * attempt
            print(f"Translation request failed; waiting {wait}s: {exc}")
            time.sleep(wait)

    raise RuntimeError(f"Translation failed after retries: {last_error}")


def split_batches(texts: list[str]) -> list[list[str]]:
    batches = []
    current = []
    chars = 0

    for text in texts:
        size = len(text)
        if current and chars + size > MAX_CHARS_PER_REQUEST:
            batches.append(current)
            current = []
            chars = 0
        current.append(text)
        chars += size

    if current:
        batches.append(current)

    return batches


def main() -> None:
    soup = BeautifulSoup(LIBRARY.read_text(encoding="utf-8"), "html.parser")
    nodes = [
        p for p in soup.select("details.paper-study-details p.paper-source-abstract")
        if needs_translation(p)
    ]

    if not nodes:
        state = {
            "translated_unique_this_run": 0,
            "translated_cards_this_run": 0,
            "remaining_cards": 0,
            "remaining_unique": 0,
            "completed": True,
        }
        STATE.write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return

    by_text = {}
    for p in nodes:
        en = clean(p.get("data-en") or p.get_text(" ", strip=True))
        by_text.setdefault(en, []).append(p)

    selected_texts = list(by_text.keys())[:MAX_UNIQUE]
    translated_map = {}

    for batch_no, batch in enumerate(split_batches(selected_texts), start=1):
        print(
            f"Translating request {batch_no}: "
            f"{len(batch)} unique texts / {sum(map(len, batch))} chars"
        )
        translations = groq_translate(batch)
        translated_map.update(zip(batch, translations))

    changed_cards = 0
    for en, it in translated_map.items():
        for p in by_text[en]:
            p["data-en"] = en
            p["data-it"] = it
            # English is the repository default display text.
            p.string = en
            changed_cards += 1

    LIBRARY.write_text(str(soup), encoding="utf-8")

    # Recalculate after writing this batch.
    remaining_nodes = [
        p for p in soup.select("details.paper-study-details p.paper-source-abstract")
        if needs_translation(p)
    ]
    remaining_unique = len({
        clean(p.get("data-en") or p.get_text(" ", strip=True))
        for p in remaining_nodes
    })

    state = {
        "translated_unique_this_run": len(translated_map),
        "translated_cards_this_run": changed_cards,
        "remaining_cards": len(remaining_nodes),
        "remaining_unique": remaining_unique,
        "completed": len(remaining_nodes) == 0,
        "batch_max_unique": MAX_UNIQUE,
    }
    STATE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(state, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
