#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
WF_DIR = ROOT / ".github" / "workflows"

def patch_workflow(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")

    if "Commit literature updates" not in text:
        return False

    original = text

    # Replace any explicit git-add block inside the commit step with git add -A.
    # This handles multiline "git add \\" blocks and single-line git add commands.
    text = re.sub(
        r'(?m)^(?P<indent>\s*)git add(?:\s+\\\\\n(?:\s+.+\n)+|\s+.+)$',
        lambda m: f'{m.group("indent")}git add -A',
        text,
        count=1,
    )

    # If the first replacement did not catch a multiline block, apply a more
    # conservative replacement between "git add" and the following blank/if line.
    if text == original:
        text = re.sub(
            r'(?ms)^(?P<indent>\s*)git add\b.*?(?=^\s*(?:if git diff --cached --quiet|if \[|git diff --cached --quiet))',
            lambda m: f'{m.group("indent")}git add -A\n\n',
            text,
            count=1,
        )

    # Add a diagnostic status line before staging, if absent.
    marker = 'echo "Generated changes before commit:"'
    if marker not in text:
        text = text.replace(
            '          git config user.email "github-actions[bot]@users.noreply.github.com"\n',
            '          git config user.email "github-actions[bot]@users.noreply.github.com"\n'
            '          echo "Generated changes before commit:"\n'
            '          git status --short\n',
            1,
        )

    # Ensure the tree is clean before pull --rebase. git add -A + commit should do it;
    # this guard captures any side-effect files created between commit and rebase.
    if 'Unexpected working-tree changes after commit' not in text:
        text = text.replace(
            '          git pull --rebase origin main\n',
            '          if [ -n "$(git status --porcelain)" ]; then\n'
            '            echo "Unexpected working-tree changes after commit:"\n'
            '            git status --short\n'
            '            git add -A\n'
            '            git commit -m "Capture literature update side effects" || true\n'
            '          fi\n\n'
            '          git pull --rebase origin main\n',
            1,
        )

    if text == original:
        return False

    path.write_text(text, encoding="utf-8")
    print(f"Patched: {path}")
    return True

def main():
    matches = []
    for path in sorted(WF_DIR.glob("*.y*ml")):
        if patch_workflow(path):
            matches.append(path)

    if not matches:
        raise SystemExit('No workflow containing "Commit literature updates" was found.')

    print(f"Patched {len(matches)} workflow(s).")

if __name__ == "__main__":
    main()
