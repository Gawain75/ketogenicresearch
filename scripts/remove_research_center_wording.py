#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "index.html"

html = TARGET.read_text(encoding="utf-8")

# Remove explicit "research center / centro di ricerca" wording from the homepage.
replacements = {
    "KETOGENIC RESEARCH CENTER": "KETOGENIC RESEARCH",
    "CENTRO DI RICERCA CHETOGENICA": "KETOGENIC RESEARCH",
    "scientific research center": "scientific research initiative",
    "Scientific research center": "Scientific research initiative",
    "research center": "research initiative",
    "Research center": "Research initiative",
    "centro di ricerca scientifica": "iniziativa di ricerca scientifica",
    "Centro di ricerca scientifica": "Iniziativa di ricerca scientifica",
    "centro di ricerca": "iniziativa di ricerca",
    "Centro di ricerca": "Iniziativa di ricerca",
}

for old, new in replacements.items():
    html = html.replace(old, new)

# Replace any surviving hero/lead formulation that explicitly declares a center.
html = re.sub(
    r'data-en="[^"]*(?:research center)[^"]*"',
    'data-en="Clinical and translational work focused on ketogenic metabolism, metabolic health and clinical nutrition."',
    html,
    flags=re.I,
)
html = re.sub(
    r'data-it="[^"]*(?:centro di ricerca)[^"]*"',
    'data-it="Attività clinica e traslazionale focalizzata su metabolismo chetogenico, salute metabolica e nutrizione clinica."',
    html,
    flags=re.I,
)

# Also remove explicit center wording from visible text nodes if any survived.
html = re.sub(r'(?i)\bscientific research center\b', 'scientific research initiative', html)
html = re.sub(r'(?i)\bresearch center\b', 'research initiative', html)
html = re.sub(r'(?i)\bcentro di ricerca scientifica\b', 'iniziativa di ricerca scientifica', html)
html = re.sub(r'(?i)\bcentro di ricerca\b', 'iniziativa di ricerca', html)

TARGET.write_text(html, encoding="utf-8")
print("Explicit research-center wording removed from homepage.")
