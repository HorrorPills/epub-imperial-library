#!/usr/bin/env python3
"""
Elder Scrolls Imperial Library — Book Scraper
==============================================
Scrapes all books (excluding Journals, Notes, and Letters) from:
  https://www.imperial-library.info/game-books

Produces 4 Kindle-ready EPUB files:
  • Daggerfall_Tomes.epub
  • Morrowind_Tomes.epub
  • Oblivion_Tomes.epub
  • Skyrim_Tomes.epub

Required packages are installed automatically.
"""

import sys
import subprocess

# ── Auto-install dependencies ─────────────────────────────────────────────────
REQUIRED = [
    ("requests",  "requests"),
    ("bs4",       "beautifulsoup4"),
    ("lxml",      "lxml"),
    ("ebooklib",  "ebooklib"),
]

print("Checking / installing required packages …")
for import_name, pip_name in REQUIRED:
    try:
        __import__(import_name)
    except ImportError:
        print(f"  Installing {pip_name} …")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", pip_name, "-q"]
        )
print("All packages ready.\n")

# ── Stdlib + third-party imports ──────────────────────────────────────────────
import time
import re
from html import escape
from typing import Optional, List, Dict

import requests
from bs4 import BeautifulSoup
from ebooklib import epub

# ── Configuration ─────────────────────────────────────────────────────────────

BASE_URL = "https://www.imperial-library.info"

GAMES: List[Dict] = [
    {
        "name":        "Daggerfall",
        "url":         f"{BASE_URL}/game-books/tes2-daggerfall-books",
        "filename":    "Daggerfall_Tomes.epub",
        "title":       "Daggerfall Tomes",
        "subtitle":    "The Elder Scrolls II: Daggerfall",
        "description": (
            "A collection of in-game books from "
            "The Elder Scrolls II: Daggerfall (1996)."
        ),
    },
    {
        "name":        "Morrowind",
        "url":         f"{BASE_URL}/game-books/tes3-morrowind-books",
        "filename":    "Morrowind_Tomes.epub",
        "title":       "Morrowind Tomes",
        "subtitle":    "The Elder Scrolls III: Morrowind",
        "description": (
            "A collection of in-game books from "
            "The Elder Scrolls III: Morrowind (2002), "
            "including the Tribunal and Bloodmoon expansions."
        ),
    },
    {
        "name":        "Oblivion",
        "url":         f"{BASE_URL}/game-books/tes4-oblivion-books",
        "filename":    "Oblivion_Tomes.epub",
        "title":       "Oblivion Tomes",
        "subtitle":    "The Elder Scrolls IV: Oblivion",
        "description": (
            "A collection of in-game books from "
            "The Elder Scrolls IV: Oblivion (2006), "
            "including Knights of the Nine and Shivering Isles."
        ),
    },
    {
        "name":        "Skyrim",
        "url":         f"{BASE_URL}/game-books/tes5-skyrim-books",
        "filename":    "Skyrim_Tomes.epub",
        "title":       "Skyrim Tomes",
        "subtitle":    "The Elder Scrolls V: Skyrim",
        "description": (
            "A collection of in-game books from "
            "The Elder Scrolls V: Skyrim (2011), "
            "including the Dawnguard and Dragonborn expansions."
        ),
    },
]

# Section IDs on the listing pages that should be EXCLUDED
# (Journals, Notes, Letters — as requested)
EXCLUDED_SECTION_IDS = {"journals", "letters-notes"}

# Any section whose ID contains one of these keywords is also skipped
EXCLUDED_KEYWORDS = ["journal", "letter", "note"]

# Delay between HTTP requests — be polite to the server
REQUEST_DELAY = 0.8  # seconds


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.5",
    })
    return session


def fetch(session: requests.Session, url: str, retries: int = 3) -> Optional[str]:
    """Fetch a URL with retry/backoff; returns HTML text or None on failure."""
    for attempt in range(retries):
        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as exc:
            wait = 2 ** attempt
            if attempt < retries - 1:
                print(f"      [retry {attempt + 1}] {exc} — waiting {wait}s …")
                time.sleep(wait)
            else:
                print(f"      [FAILED] {url}: {exc}")
    return None


# ── Section-exclusion logic ───────────────────────────────────────────────────

def is_excluded(section_id: str) -> bool:
    """Return True if this section (by its HTML id) should be skipped."""
    sid = section_id.lower()
    if sid in EXCLUDED_SECTION_IDS:
        return True
    return any(kw in sid for kw in EXCLUDED_KEYWORDS)


# ── Scraping ──────────────────────────────────────────────────────────────────

def scrape_book_list(
    session: requests.Session, game_url: str
) -> List[Dict[str, str]]:
    """
    Parse a game-listing page and return a list of
    {"title": str, "url": str} dicts, skipping excluded sections.
    """
    html = fetch(session, game_url)
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    content = soup.find("div", class_="entry-content")
    if not content:
        return []

    books: List[Dict[str, str]] = []
    skip_current = False

    for el in content.find_all(["h2", "h3", "h4", "div"]):
        # ── Section heading ──────────────────────────────────────────
        if el.name in ("h2", "h3", "h4"):
            sid = el.get("id", "")
            skip_current = is_excluded(sid)
            if skip_current:
                print(f"    ⊘  Skipping section: {el.get_text(strip=True)}")
            continue

        if skip_current:
            continue

        # ── Book-listing block ────────────────────────────────────────
        if "book-listing" in (el.get("class") or []):
            for item in el.find_all("div", class_="listing-item"):
                link = item.find("a", class_="title")
                if link and link.get("href"):
                    books.append(
                        {"title": link.get_text(strip=True), "url": link["href"]}
                    )

    return books


def scrape_book(
    session: requests.Session, url: str
) -> Optional[Dict[str, str]]:
    """
    Fetch one book page.
    Returns {"title", "info_html", "content_html", "url"} or None.
    """
    html = fetch(session, url)
    if not html:
        return None

    soup = BeautifulSoup(html, "lxml")

    # Title
    title_el = soup.find("h1", class_="entry-title")
    title = title_el.get_text(strip=True) if title_el else "Unknown Title"

    # Book-info strip (game, category, author)
    info_el = soup.find("p", class_="book-info")
    if info_el:
        # Convert anchor tags to plain text (removes dead href links in EPUB)
        for a in info_el.find_all("a"):
            a.replace_with(a.get_text())
        info_html = str(info_el)
    else:
        info_html = ""

    # Main content
    content_el = soup.find("div", class_="entry-content")
    if not content_el:
        return None

    # Strip scripts / styles / iframes
    for bad in content_el.find_all(["script", "style", "iframe"]):
        bad.decompose()
    # Ensure all images have an alt attribute (required for valid EPUB)
    for img in content_el.find_all("img"):
        if not img.get("alt"):
            img["alt"] = ""

    content_html = content_el.decode_contents()

    return {
        "title":        title,
        "info_html":    info_html,
        "content_html": content_html,
        "url":          url,
    }


# ── EPUB construction ─────────────────────────────────────────────────────────

STYLESHEET = """\
@charset "UTF-8";
body {
    font-family: Georgia, "Times New Roman", serif;
    line-height: 1.65;
    margin: 0.5em 1.5em 1.5em 1.5em;
    color: #1a1a1a;
}
h1.book-title {
    font-size: 1.35em;
    color: #3d2000;
    border-bottom: 1px solid #c8a45a;
    padding-bottom: 0.25em;
    margin-top: 0.4em;
    margin-bottom: 0.4em;
}
.book-info {
    font-size: 0.82em;
    color: #555;
    font-style: italic;
    border-left: 3px solid #c8a45a;
    padding: 0.4em 0.8em;
    background: #fdf8f0;
    margin-bottom: 1.4em;
}
.book-content p {
    margin: 0.45em 0;
    text-indent: 1.5em;
}
.book-content p:first-of-type {
    text-indent: 0;
}
.book-content h1,
.book-content h2,
.book-content h3 {
    text-indent: 0;
    color: #3d2000;
}
.cover-wrap {
    text-align: center;
    margin-top: 3em;
}
.cover-title {
    font-size: 2.2em;
    color: #3d2000;
    margin-bottom: 0.3em;
}
.cover-subtitle {
    font-size: 1.1em;
    color: #555;
    font-style: italic;
    margin-bottom: 0.5em;
}
.cover-description {
    font-size: 0.9em;
    color: #666;
    margin: 1em auto;
    max-width: 30em;
}
.cover-source {
    font-size: 0.8em;
    color: #999;
    margin-top: 3em;
}
"""


def _chapter_xhtml(title: str, info_html: str, content_html: str) -> str:
    safe = escape(title)
    return (
        "<!DOCTYPE html>\n"
        '<html xmlns="http://www.w3.org/1999/xhtml"'
        ' xmlns:epub="http://www.idpf.org/2007/ops">\n'
        "<head>\n"
        '  <meta charset="utf-8"/>\n'
        f"  <title>{safe}</title>\n"
        '  <link rel="stylesheet" type="text/css" href="../Styles/main.css"/>\n'
        "</head>\n"
        "<body>\n"
        f'  <h1 class="book-title">{safe}</h1>\n'
        f'  <div class="book-info">{info_html}</div>\n'
        f'  <div class="book-content">{content_html}</div>\n'
        "</body>\n</html>"
    )


def _cover_xhtml(
    title: str, subtitle: str, description: str, count: int
) -> str:
    return (
        "<!DOCTYPE html>\n"
        '<html xmlns="http://www.w3.org/1999/xhtml"'
        ' xmlns:epub="http://www.idpf.org/2007/ops">\n'
        "<head>\n"
        '  <meta charset="utf-8"/>\n'
        f"  <title>{escape(title)}</title>\n"
        '  <link rel="stylesheet" type="text/css" href="../Styles/main.css"/>\n'
        "</head>\n"
        "<body>\n"
        '  <div class="cover-wrap">\n'
        f'    <p class="cover-title">{escape(title)}</p>\n'
        f'    <p class="cover-subtitle">{escape(subtitle)}</p>\n'
        f'    <p class="cover-description">{escape(description)}</p>\n'
        f'    <p class="cover-description">{count} books</p>\n'
        '    <p class="cover-source">'
        "Compiled from The Imperial Library<br/>"
        "imperial-library.info"
        "</p>\n"
        "  </div>\n"
        "</body>\n</html>"
    )


def create_epub_file(game: Dict, books: List[Dict]) -> str:
    ebook = epub.EpubBook()
    ebook.set_identifier(f"imperial-library-{game['name'].lower()}-tomes")
    ebook.set_title(game["title"])
    ebook.set_language("en")
    ebook.add_author("The Imperial Library")
    ebook.add_metadata("DC", "description", game["description"])
    ebook.add_metadata("DC", "publisher", "The Imperial Library")
    ebook.add_metadata(
        "DC", "rights", "The Elder Scrolls \u00a9 ZeniMax Media Inc."
    )

    # Stylesheet
    css = epub.EpubItem(
        uid="main-css",
        file_name="Styles/main.css",
        media_type="text/css",
        content=STYLESHEET,
    )
    ebook.add_item(css)

    # Cover / title page
    cover_ch = epub.EpubHtml(
        title=game["title"], file_name="Text/cover.xhtml", lang="en"
    )
    cover_ch.content = _cover_xhtml(
        game["title"], game["subtitle"], game["description"], len(books)
    )
    cover_ch.add_item(css)
    ebook.add_item(cover_ch)

    chapters = []
    toc_links = [epub.Link("Text/cover.xhtml", "Title Page", "cover")]

    for idx, bk in enumerate(books):
        safe_name = re.sub(r"[^\w]", "_", bk["title"])[:40]
        fname = f"Text/book_{idx:04d}_{safe_name}.xhtml"
        ch = epub.EpubHtml(title=bk["title"], file_name=fname, lang="en")
        ch.content = _chapter_xhtml(
            bk["title"], bk["info_html"], bk["content_html"]
        )
        ch.add_item(css)
        ebook.add_item(ch)
        chapters.append(ch)
        toc_links.append(epub.Link(fname, bk["title"], f"book_{idx:04d}"))

    ebook.toc = toc_links
    ebook.spine = ["nav", cover_ch] + chapters
    ebook.add_item(epub.EpubNcx())
    ebook.add_item(epub.EpubNav())

    out_path = game["filename"]
    epub.write_epub(out_path, ebook, {})
    return out_path


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 56)
    print("  Elder Scrolls Imperial Library — Book Scraper")
    print("=" * 56)

    session = make_session()
    created: List[str] = []

    for game in GAMES:
        print(f"\n{'─' * 56}")
        print(f"  {game['title']}")
        print(f"  {game['url']}")
        print(f"{'─' * 56}")

        # 1. Collect book URLs from the listing page
        print("  Fetching book list …")
        raw_refs = scrape_book_list(session, game["url"])
        time.sleep(REQUEST_DELAY)

        # Deduplicate — same URL may appear multiple times on a page
        seen_urls: set = set()
        unique_refs: List[Dict[str, str]] = []
        for ref in raw_refs:
            if ref["url"] not in seen_urls:
                seen_urls.add(ref["url"])
                unique_refs.append(ref)

        print(f"  {len(unique_refs)} unique books found (after deduplication)")

        # 2. Fetch content of each individual book
        books_data: List[Dict] = []
        failed = 0
        for i, ref in enumerate(unique_refs, 1):
            short = ref["title"]
            if len(short) > 55:
                short = short[:52] + "..."
            print(f"  [{i:3d}/{len(unique_refs)}] {short}")
            data = scrape_book(session, ref["url"])
            if data:
                books_data.append(data)
            else:
                failed += 1
            time.sleep(REQUEST_DELAY)

        print(
            f"\n  Scraped: {len(books_data)} books"
            + (f"  |  Failed: {failed}" if failed else "")
        )

        # 3. Build EPUB
        print("  Building EPUB …")
        out = create_epub_file(game, books_data)
        created.append(out)
        print(f"  Saved -> {out}")

    print(f"\n{'=' * 56}")
    print("All done!  Created files:")
    for f in created:
        print(f"    {f}")
    print()


if __name__ == "__main__":
    main()
