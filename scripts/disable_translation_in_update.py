#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
WF_DIR = ROOT / ".github" / "workflows"

STEP_NAME = "Translate untranslated Library titles"

def patch(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")

    if STEP_NAME not in text:
        return False

    original = text

    # Add a permanent false condition to the translation step so it no longer
    # blocks or modifies the main literature-update workflow. Translation can
    # still run from its dedicated workflow if desired.
    pattern = re.compile(
        r'(?m)^(?P<indent>\s*)-\s+name:\s*Translate untranslated Library titles\s*$'
    )

    m = pattern.search(text)
    if not m:
        return False

    indent = m.group("indent")
    insertion = (
        f'{indent}- name: Translate untranslated Library titles\n'
        f'{indent}  if: ${{{{ false }}}}\n'
    )

    # Replace only the step's name line; preserve the rest of the step.
    text = text[:m.start()] + insertion + text[m.end():]

    path.write_text(text, encoding="utf-8")
    print(f"Disabled translation step in: {path.name}")
    return text != original

def main():
    changed = []
    for path in sorted(WF_DIR.glob("*.y*ml")):
        if patch(path):
            changed.append(path)

    if not changed:
        raise SystemExit('No workflow containing "Translate untranslated Library titles" was found.')

    print(f"Patched {len(changed)} workflow(s).")

if __name__ == "__main__":
    main()
