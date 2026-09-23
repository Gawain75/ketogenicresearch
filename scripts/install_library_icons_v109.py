#!/usr/bin/env python3
from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "library.html"

html = LIBRARY.read_text(encoding="utf-8")
soup = BeautifulSoup(html, "html.parser")

head = soup.head
if head is None:
    raise SystemExit("library.html has no <head>.")

existing = head.find("link", href=lambda v: v and "library-icons.css" in v)
if existing:
    existing["href"] = "library-icons.css?v=109"
else:
    link = soup.new_tag("link", rel="stylesheet", href="library-icons.css?v=109")
    # Keep the icon layer after the main stylesheet so it can override legacy SVGs.
    main = head.find("link", rel=lambda v: v and "stylesheet" in v)
    if main:
        main.insert_after(link)
    else:
        head.append(link)

LIBRARY.write_text(str(soup), encoding="utf-8")
print("Library premium icon stylesheet linked.")
