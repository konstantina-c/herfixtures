#!/usr/bin/env python3
"""
HerFixtures — sitemap.xml generator
Scans blog/ for article subdirectories and builds a canonical sitemap
with accurate per-article lastmod dates extracted from the article-meta div.
Run after feed scripts so sitemap.xml is committed in the same CI step.
"""

import os
import re
from datetime import date

BASE_URL = "https://herfixtures.com"
OUTPUT_FILE = "sitemap.xml"
BLOG_DIR = "blog"

# Static pages: (path, lastmod)
# Homepage and blog index don't change on every feed refresh; pin to known dates.
STATIC_PAGES = [
    ("/",      "2026-08-14"),
    ("/blog/", "2026-08-14"),
]

DATE_RE = re.compile(
    r'class="article-meta"[^>]*>[^<]*'                   # open tag + text before date
    r'(?:Football|Cricket|Basketball|Tennis|Rugby)'
    r'(?:[^<]*)(?:·|&middot;)\s*'                        # separator (literal or entity)
    r'(\d{1,2}\s+\w+\s+\d{4})',                         # capture: "14 August 2026"
    re.IGNORECASE,
)

MONTHS = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
}


def parse_article_date(html: str) -> str | None:
    m = DATE_RE.search(html)
    if not m:
        return None
    raw = m.group(1).strip()  # e.g. "14 August 2026"
    parts = raw.split()
    if len(parts) != 3:
        return None
    day, month_name, year = parts
    month = MONTHS.get(month_name.lower())
    if not month:
        return None
    return f"{year}-{month}-{day.zfill(2)}"


def collect_articles():
    articles = []
    if not os.path.isdir(BLOG_DIR):
        return articles
    for entry in sorted(os.listdir(BLOG_DIR)):
        entry_path = os.path.join(BLOG_DIR, entry)
        index_path = os.path.join(entry_path, "index.html")
        if not os.path.isdir(entry_path) or not os.path.isfile(index_path):
            continue
        with open(index_path, encoding="utf-8") as f:
            html = f.read()
        pub_date = parse_article_date(html)
        if not pub_date:
            pub_date = date.today().isoformat()
        articles.append((f"/blog/{entry}/", pub_date))
    return articles


def build_sitemap(pages):
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for path, lastmod in pages:
        lines.append("  <url>")
        lines.append(f"    <loc>{BASE_URL}{path}</loc>")
        lines.append(f"    <lastmod>{lastmod}</lastmod>")
        lines.append("  </url>")
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


def main():
    pages = list(STATIC_PAGES) + collect_articles()
    xml = build_sitemap(pages)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(xml)
    print(f"sitemap.xml written — {len(pages)} URLs:")
    for path, lastmod in pages:
        print(f"  {BASE_URL}{path}  [{lastmod}]")


if __name__ == "__main__":
    main()
