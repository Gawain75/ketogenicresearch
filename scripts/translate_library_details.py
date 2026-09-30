#!/usr/bin/env python3
from __future__ import annotations

import json, os, re, time, urllib.error, urllib.request
from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "library.html"
STATE = ROOT / "library-details-translation-state.json"

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip()
MAX_UNIQUE = max(1, int(os.getenv("DETAIL_TRANSLATION_BATCH_MAX", "10")))
MAX_CHARS_PER_REQUEST = max(2500, int(os.getenv("DETAIL_TRANSLATION_MAX_CHARS", "6500")))

def clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()

def needs_translation(p) -> bool:
    en = clean(p.get("data-en") or p.get_text(" ", strip=True))
    it = clean(p.get("data-it") or "")
    return bool(en and (not it or it.casefold() == en.casefold()))

def split_batches(texts):
    batches, cur, chars = [], [], 0
    for text in texts:
        if cur and chars + len(text) > MAX_CHARS_PER_REQUEST:
            batches.append(cur); cur=[]; chars=0
        cur.append(text); chars += len(text)
    if cur:
        batches.append(cur)
    return batches

def groq_translate(batch):
    prompt = """Translate these biomedical research-detail texts from English into Italian.
Translate faithfully. Do not summarize, expand, interpret or omit information.
Preserve numbers, units, p values, confidence intervals, gene/protein symbols,
drug names, study acronyms, trial identifiers and scientific abbreviations.
Use professional scientific Italian.
Return JSON only exactly as: {"translations":["...", "..."]}

Texts:
""" + json.dumps(batch, ensure_ascii=False)

    # Keep reserved output tokens small enough not to consume the TPM budget.
    approx_input_tokens = max(1, len(prompt) // 4)
    max_output = min(3200, max(900, int(approx_input_tokens * 1.35)))

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role":"system","content":"You are a biomedical English-to-Italian translator. Return JSON only."},
            {"role":"user","content":prompt},
        ],
        "temperature":0.0,
        "max_completion_tokens":max_output,
        "reasoning_effort":"low",
        "reasoning_format":"hidden",
        "response_format":{"type":"json_object"},
    }

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent":"KetogenicResearch/DetailsTranslationCheckpointed",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        if exc.code == 429:
            retry = exc.headers.get("Retry-After")
            try:
                retry_s = int(float(retry))
            except Exception:
                retry_s = 0
            raise RuntimeError(f"RATE_LIMIT:{retry_s}:{body[:500]}") from exc
        if exc.code == 413 and len(batch) > 1:
            mid = len(batch)//2
            return groq_translate(batch[:mid]) + groq_translate(batch[mid:])
        raise RuntimeError(f"Groq HTTP {exc.code}: {body[:800]}") from exc

    content = data["choices"][0]["message"]["content"].strip()
    parsed = json.loads(content)
    out = [clean(str(x)) for x in (parsed.get("translations") or [])]
    if len(out) != len(batch) or any(not x for x in out):
        raise RuntimeError("Invalid translation response.")
    return out

def save(soup, translated_unique, translated_cards):
    LIBRARY.write_text(str(soup), encoding="utf-8")
    remaining_nodes = [
        p for p in soup.select("details.paper-study-details p.paper-source-abstract")
        if needs_translation(p)
    ]
    remaining_unique = len({
        clean(p.get("data-en") or p.get_text(" ", strip=True))
        for p in remaining_nodes
    })
    state = {
        "translated_unique_this_run": translated_unique,
        "translated_cards_this_run": translated_cards,
        "remaining_cards": len(remaining_nodes),
        "remaining_unique": remaining_unique,
        "completed": len(remaining_nodes) == 0,
    }
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(state, ensure_ascii=False, indent=2))

def main():
    if not GROQ_API_KEY:
        raise SystemExit("GROQ_API_KEY is not configured.")

    soup = BeautifulSoup(LIBRARY.read_text(encoding="utf-8"), "html.parser")
    nodes = [
        p for p in soup.select("details.paper-study-details p.paper-source-abstract")
        if needs_translation(p)
    ]
    if not nodes:
        save(soup, 0, 0)
        return

    by_text = {}
    for p in nodes:
        en = clean(p.get("data-en") or p.get_text(" ", strip=True))
        by_text.setdefault(en, []).append(p)

    selected = list(by_text)[:MAX_UNIQUE]
    done_unique = 0
    done_cards = 0

    # Save after every successful request so even the current checkpoint is durable.
    for n, batch in enumerate(split_batches(selected), 1):
        print(f"Translating request {n}: {len(batch)} texts / {sum(map(len,batch))} chars")
        try:
            translations = groq_translate(batch)
        except RuntimeError as exc:
            save(soup, done_unique, done_cards)
            raise

        for en, it in zip(batch, translations):
            for p in by_text[en]:
                p["data-en"] = en
                p["data-it"] = it
                p.string = en
                done_cards += 1
            done_unique += 1

        save(soup, done_unique, done_cards)
        time.sleep(20)

if __name__ == "__main__":
    main()
