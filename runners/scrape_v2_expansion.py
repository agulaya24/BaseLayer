#!/usr/bin/env python3
"""
V2 Expansion Scraper — fetch MORE posts for 10 Wave 1 subjects.
Skips files that already exist. Only adds NEW content.

Usage:
    python scrape_v2_expansion.py                  # all subjects
    python scrape_v2_expansion.py --only scott      # one subject
    python scrape_v2_expansion.py --only scott,matt  # multiple
"""

import requests
import re
import time
import os
import sys
import argparse
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

DATA_DIR = Path(__file__).parent / "data"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; BaselayerBot/1.0)"}


# ── HTML-to-text ─────────────────────────────────────────────────────────────

class HTMLToText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.result = []
        self.skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "nav", "footer", "header"):
            self.skip = True
        elif tag in ("p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6",
                      "li", "blockquote", "tr"):
            self.result.append("\n")
        elif tag == "hr":
            self.result.append("\n---\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "nav", "footer", "header"):
            self.skip = False
        elif tag in ("p", "div", "h1", "h2", "h3", "h4", "h5", "h6",
                      "blockquote", "tr"):
            self.result.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.result.append(data)

    def get_text(self):
        text = "".join(self.result)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def html_to_text(html):
    parser = HTMLToText()
    parser.feed(html)
    return parser.get_text()


def sanitize_filename(s):
    return re.sub(r"[^\w\-]", "_", s)[:120]


def save_post(output_dir, slug, title, text, url=""):
    filename = sanitize_filename(slug) + ".txt"
    filepath = output_dir / filename
    if filepath.exists():
        return False  # already have it
    if len(text) < 200:
        return False  # too short
    header = f"{title}\nSource: {url}\n\n" if url else f"{title}\n\n"
    filepath.write_text(header + text + "\n", encoding="utf-8")
    return True


# ── Substack scraper ─────────────────────────────────────────────────────────

def scrape_substack(subdomain, output_dir, target=500, skip_patterns=None):
    """Scrape ALL free posts from a Substack. Uses their API."""
    base_url = f"https://{subdomain}"
    api_url = f"{base_url}/api/v1/archive"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    existing = len(list(output_dir.glob("*.txt")))
    print(f"  Existing files: {existing}")

    collected = []
    offset = 0
    batch_size = 50

    while len(collected) < target:
        try:
            resp = requests.get(api_url, params={
                "sort": "new", "search": "", "offset": offset, "limit": batch_size
            }, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            posts = resp.json()
        except Exception as e:
            print(f"  API error at offset {offset}: {e}")
            break

        if not posts:
            break

        for post in posts:
            audience = post.get("audience", "everyone")
            if audience != "everyone":
                continue
            slug = post.get("slug", "")
            title = post.get("title", "Untitled")
            if skip_patterns and any(p in slug for p in skip_patterns):
                continue
            collected.append({"slug": slug, "title": title})
            if len(collected) >= target:
                break

        offset += batch_size
        time.sleep(0.5)

    print(f"  Found {len(collected)} free posts. Fetching new ones...")

    saved = 0
    skipped = 0
    for i, post in enumerate(collected):
        slug = post["slug"]
        title = post["title"]
        filepath = output_dir / (sanitize_filename(slug) + ".txt")
        if filepath.exists():
            skipped += 1
            continue

        try:
            url = f"{base_url}/api/v1/posts/{slug}"
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            body_html = resp.json().get("body_html", "")
            if not body_html:
                continue

            text = html_to_text(body_html)
            post_url = f"{base_url}/p/{slug}"
            if save_post(output_dir, slug, title, text, post_url):
                words = len(text.split())
                print(f"  [{saved+1}] SAVED: {slug} ({words:,} words)")
                saved += 1
            time.sleep(2.0)
        except requests.exceptions.HTTPError as e:
            if e.response and e.response.status_code == 429:
                print(f"  Rate limited on {slug}, waiting 15s...")
                time.sleep(15)
            else:
                print(f"  Error on {slug}: {e}")
            time.sleep(3.0)
        except Exception as e:
            print(f"  Error on {slug}: {e}")
            time.sleep(2.0)

    print(f"  Done: {saved} new, {skipped} existing")
    return saved


# ── WordPress/blog sitemap scraper ───────────────────────────────────────────

def scrape_sitemap_blog(base_url, output_dir, target=500, content_selector=None,
                         url_filter=None, skip_patterns=None):
    """Scrape blog posts via sitemap.xml. Works for WordPress, custom blogs."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    existing = len(list(output_dir.glob("*.txt")))
    print(f"  Existing files: {existing}")

    # Try common sitemap locations
    urls = []
    sitemap_urls = [
        f"{base_url}/sitemap.xml",
        f"{base_url}/sitemap_index.xml",
        f"{base_url}/post-sitemap.xml",
        f"{base_url}/sitemap-posts.xml",
    ]

    for sitemap_url in sitemap_urls:
        try:
            resp = requests.get(sitemap_url, headers=HEADERS, timeout=15)
            if resp.status_code == 200:
                root = ElementTree.fromstring(resp.content)
                ns = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}

                # Check if it's a sitemap index
                sitemaps = root.findall(".//ns:sitemap/ns:loc", ns)
                if sitemaps:
                    for sm in sitemaps:
                        sm_url = sm.text
                        if "post" in sm_url.lower() or not any(x in sm_url.lower() for x in ["page", "category", "tag", "author"]):
                            try:
                                resp2 = requests.get(sm_url, headers=HEADERS, timeout=15)
                                root2 = ElementTree.fromstring(resp2.content)
                                for loc in root2.findall(".//ns:url/ns:loc", ns):
                                    urls.append(loc.text)
                                time.sleep(0.5)
                            except Exception:
                                pass
                else:
                    for loc in root.findall(".//ns:url/ns:loc", ns):
                        urls.append(loc.text)

                if urls:
                    print(f"  Found {len(urls)} URLs from {sitemap_url}")
                    break
        except Exception:
            continue

    if not urls:
        print(f"  No sitemap found at {base_url}. Trying RSS...")
        urls = scrape_rss_urls(base_url)

    if not urls:
        print(f"  ERROR: No URLs found for {base_url}")
        return 0

    # Filter URLs
    if url_filter:
        urls = [u for u in urls if url_filter(u)]
    if skip_patterns:
        urls = [u for u in urls if not any(p in u for p in skip_patterns)]

    # Remove non-post URLs (common patterns)
    urls = [u for u in urls if not any(x in u for x in [
        "/tag/", "/category/", "/author/", "/page/", "/wp-content/",
        "/feed/", "/comments/", "/attachment/", "#", "?",
    ])]

    print(f"  {len(urls)} post URLs after filtering. Fetching new ones...")

    saved = 0
    for url in urls[:target]:
        parsed = urlparse(url)
        slug = parsed.path.strip("/").replace("/", "_")
        if not slug:
            continue

        filepath = output_dir / (sanitize_filename(slug) + ".txt")
        if filepath.exists():
            continue

        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            html = resp.text

            # Try to extract title
            title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
            title = html_to_text(title_match.group(1)).strip() if title_match else slug

            # Try specific content selectors, fall back to full page
            text = ""
            if content_selector:
                # Simple CSS selector extraction
                pattern = f'<{content_selector}[^>]*>(.*?)</{content_selector}>'
                match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
                if match:
                    text = html_to_text(match.group(1))

            if not text or len(text) < 200:
                # Try common content containers
                for sel in ["article", "main", "div class=\"post-content\"",
                            "div class=\"entry-content\"", "div class=\"prose\""]:
                    tag = sel.split()[0]
                    if " " in sel:
                        attr = sel.split(" ", 1)[1]
                        pattern = f"<{tag} {attr}[^>]*>(.*?)</{tag}>"
                    else:
                        pattern = f"<{tag}[^>]*>(.*?)</{tag}>"
                    match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
                    if match:
                        candidate = html_to_text(match.group(1))
                        if len(candidate) > len(text):
                            text = candidate

            if not text or len(text) < 200:
                text = html_to_text(html)

            if save_post(output_dir, slug, title, text, url):
                words = len(text.split())
                print(f"  [{saved+1}] SAVED: {slug[:60]} ({words:,} words)")
                saved += 1

            time.sleep(1.5)
        except Exception as e:
            print(f"  Error on {url[:60]}: {e}")
            time.sleep(2.0)

    print(f"  Done: {saved} new posts")
    return saved


def scrape_rss_urls(base_url):
    """Fall back to RSS feed for URL discovery."""
    urls = []
    rss_paths = ["/feed", "/rss", "/feed.xml", "/rss.xml", "/atom.xml", "/index.xml"]
    for path in rss_paths:
        try:
            resp = requests.get(f"{base_url}{path}", headers=HEADERS, timeout=15)
            if resp.status_code == 200:
                # Extract URLs from RSS
                for match in re.finditer(r"<link>([^<]+)</link>", resp.text):
                    url = match.group(1).strip()
                    if url.startswith("http") and url != base_url and url != f"{base_url}/":
                        urls.append(url)
                # Also try Atom format
                for match in re.finditer(r'href="([^"]+)"', resp.text):
                    url = match.group(1).strip()
                    if url.startswith("http") and "/post" in url or "/p/" in url or "/20" in url:
                        urls.append(url)
                if urls:
                    print(f"  Found {len(urls)} URLs from RSS at {base_url}{path}")
                    break
        except Exception:
            continue
    return list(dict.fromkeys(urls))  # dedupe preserving order


# ── Simon Willison special scraper ───────────────────────────────────────────

def scrape_simon_willison(output_dir, target=500):
    """Simon's blog at simonwillison.net has a structured archive."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    existing = len(list(output_dir.glob("*.txt")))
    print(f"  Existing files: {existing}")

    # His blog has /archive/ page and posts at /YYYY/Mon/DD/slug/
    urls = []

    # Try sitemap first
    try:
        resp = requests.get("https://simonwillison.net/sitemap.xml", headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            root = ElementTree.fromstring(resp.content)
            ns = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            for loc in root.findall(".//ns:url/ns:loc", ns):
                url = loc.text
                if re.match(r"https://simonwillison\.net/\d{4}/\w+/\d+/", url):
                    urls.append(url)
            print(f"  Found {len(urls)} blog post URLs from sitemap")
    except Exception:
        pass

    if not urls:
        # Try RSS
        urls = scrape_rss_urls("https://simonwillison.net")

    saved = 0
    for url in urls[:target]:
        parsed = urlparse(url)
        slug = parsed.path.strip("/").replace("/", "_")
        filepath = output_dir / (sanitize_filename(slug) + ".txt")
        if filepath.exists():
            continue

        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()

            title_match = re.search(r"<title[^>]*>(.*?)</title>", resp.text, re.DOTALL)
            title = html_to_text(title_match.group(1)).strip() if title_match else slug

            # Simon's blog uses .entry-content
            for sel in ["entry-content", "article"]:
                pattern = f'class="{sel}"[^>]*>(.*?)</div>'
                match = re.search(pattern, resp.text, re.DOTALL)
                if match:
                    text = html_to_text(match.group(1))
                    if len(text) > 200:
                        break
            else:
                text = html_to_text(resp.text)

            if save_post(output_dir, slug, title, text, url):
                words = len(text.split())
                print(f"  [{saved+1}] SAVED: {slug[:50]} ({words:,} words)")
                saved += 1
            time.sleep(1.5)
        except Exception as e:
            print(f"  Error: {e}")
            time.sleep(2.0)

    print(f"  Done: {saved} new posts")
    return saved


# ── swyx special scraper ─────────────────────────────────────────────────────

def scrape_swyx(output_dir, target=300):
    """swyx.io - try sitemap and RSS."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    existing = len(list(output_dir.glob("*.txt")))
    print(f"  Existing files: {existing}")

    # swyx.io might use a static site generator
    return scrape_sitemap_blog(
        "https://www.swyx.io", output_dir, target=target,
        url_filter=lambda u: "/ideas/" in u or "/writing/" in u or "/blog/" in u or re.search(r"/\d{4}", u),
    )


# ── David Perell special scraper ─────────────────────────────────────────────

def scrape_david_perell(output_dir, target=300):
    """Perell.com — WordPress with paginated essays at /essays/page/N/."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    existing = len(list(output_dir.glob("*.txt")))
    print(f"  Existing files: {existing}")

    # Collect essay URLs by crawling paginated essay index
    essay_urls = []
    page = 1
    while len(essay_urls) < target:
        if page == 1:
            index_url = "https://perell.com/essays/"
        else:
            index_url = f"https://perell.com/essays/page/{page}/"

        try:
            resp = requests.get(index_url, headers=HEADERS, timeout=30)
            if resp.status_code == 404:
                print(f"  Page {page} returned 404, done collecting URLs.")
                break
            resp.raise_for_status()

            # Extract essay URLs from page
            found = re.findall(r'href="(https://perell\.com/essay/[^"]+)"', resp.text)
            found = list(dict.fromkeys(found))  # dedupe preserving order
            # Filter out the 3 always-present featured essays
            if page > 1:
                found = [u for u in found if u not in essay_urls[:3]]

            if not found:
                print(f"  Page {page} had no new essay links, done.")
                break

            new_on_page = [u for u in found if u not in essay_urls]
            essay_urls.extend(new_on_page)
            print(f"  Page {page}: found {len(new_on_page)} new essay URLs (total: {len(essay_urls)})")

            page += 1
            time.sleep(1.0)
        except Exception as e:
            print(f"  Error fetching page {page}: {e}")
            break

    # Also collect newsletter archive URLs from ckarchive.com
    print(f"  Collecting newsletter archive URLs...")
    try:
        resp = requests.get("https://perell.com/newsletter-archive/", headers=HEADERS, timeout=30)
        resp.raise_for_status()
        ck_urls = re.findall(r'href="(https://ckarchive\.com/b/[^"]+)"', resp.text)
        ck_urls = list(dict.fromkeys(ck_urls))
        print(f"  Found {len(ck_urls)} newsletter archive URLs")
    except Exception as e:
        print(f"  Error fetching newsletter archive: {e}")
        ck_urls = []

    # Combine: essays first, then newsletters
    all_urls = [(u, "essay") for u in essay_urls] + [(u, "newsletter") for u in ck_urls]
    print(f"  Total URLs: {len(all_urls)} ({len(essay_urls)} essays + {len(ck_urls)} newsletters)")
    print(f"  Fetching new ones...")

    saved = 0
    for url, content_type in all_urls[:target]:
        parsed = urlparse(url)
        if content_type == "newsletter":
            # Use ckarchive ID as slug
            slug = "newsletter_" + parsed.path.strip("/").split("/")[-1]
        else:
            slug = parsed.path.strip("/").split("/")[-1]
        if not slug:
            continue

        filepath = output_dir / (sanitize_filename(slug) + ".txt")
        if filepath.exists():
            continue

        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()

            title_match = re.search(r"<title[^>]*>(.*?)</title>", resp.text, re.DOTALL | re.IGNORECASE)
            title = html_to_text(title_match.group(1)).strip() if title_match else slug

            # Try content selectors
            text = ""
            for sel in ["article", "div class=\"entry-content\"", "div class=\"post-content\"",
                        "div class=\"prose\"", "main"]:
                tag = sel.split()[0]
                if " " in sel:
                    attr = sel.split(" ", 1)[1]
                    pattern = f"<{tag} {attr}[^>]*>(.*?)</{tag}>"
                else:
                    pattern = f"<{tag}[^>]*>(.*?)</{tag}>"
                match = re.search(pattern, resp.text, re.DOTALL | re.IGNORECASE)
                if match:
                    candidate = html_to_text(match.group(1))
                    if len(candidate) > len(text):
                        text = candidate

            if not text or len(text) < 200:
                text = html_to_text(resp.text)

            if save_post(output_dir, slug, title, text, url):
                words = len(text.split())
                print(f"  [{saved+1}] SAVED: {slug[:60]} ({words:,} words) [{content_type}]")
                saved += 1

            time.sleep(2.0)
        except Exception as e:
            print(f"  Error on {slug}: {e}")
            time.sleep(2.0)

    print(f"  Done: {saved} new posts")
    return saved


# ── Maggie Appleton special scraper ──────────────────────────────────────────

def scrape_maggie_appleton(output_dir, target=300):
    """maggieappleton.com — digital garden with essays, notes, patterns, talks."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    existing = len(list(output_dir.glob("*.txt")))
    print(f"  Existing files: {existing}")

    # Collect URLs from each content type index page
    content_pages = []
    index_pages = [
        ("https://maggieappleton.com/essays", "essay"),
        ("https://maggieappleton.com/notes", "note"),
        ("https://maggieappleton.com/patterns", "pattern"),
        ("https://maggieappleton.com/talks", "talk"),
        ("https://maggieappleton.com/smidgeons", "smidgeon"),
    ]

    for index_url, content_type in index_pages:
        try:
            resp = requests.get(index_url, headers=HEADERS, timeout=30)
            resp.raise_for_status()

            # Extract internal links — maggieappleton.com uses relative paths like /slug
            hrefs = re.findall(r'href="(/[a-z][a-z0-9_-]+)"', resp.text)
            hrefs = list(dict.fromkeys(hrefs))  # dedupe

            # Filter out navigation/structural links
            skip = ["/essays", "/notes", "/patterns", "/talks", "/smidgeons",
                    "/library", "/now", "/about", "/podcasts", "/antilibrary",
                    "/resources", "/colophon", "/start-here", "/uses"]
            hrefs = [h for h in hrefs if h not in skip]

            for href in hrefs:
                full_url = f"https://maggieappleton.com{href}"
                if full_url not in [p[0] for p in content_pages]:
                    content_pages.append((full_url, content_type))

            print(f"  {content_type}: found {len(hrefs)} links")
            time.sleep(1.0)
        except Exception as e:
            print(f"  Error fetching {index_url}: {e}")

    print(f"  Collected {len(content_pages)} content URLs. Fetching new ones...")

    saved = 0
    for url, content_type in content_pages[:target]:
        parsed = urlparse(url)
        slug = parsed.path.strip("/").replace("/", "_")
        if not slug:
            continue

        filepath = output_dir / (sanitize_filename(slug) + ".txt")
        if filepath.exists():
            continue

        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()

            title_match = re.search(r"<title[^>]*>(.*?)</title>", resp.text, re.DOTALL | re.IGNORECASE)
            title = html_to_text(title_match.group(1)).strip() if title_match else slug

            # Try content selectors for her garden
            text = ""
            for sel in ["article", "main", "div class=\"prose\"",
                        "div class=\"content\"", "div class=\"post\""]:
                tag = sel.split()[0]
                if " " in sel:
                    attr = sel.split(" ", 1)[1]
                    pattern = f"<{tag} {attr}[^>]*>(.*?)</{tag}>"
                else:
                    pattern = f"<{tag}[^>]*>(.*?)</{tag}>"
                match = re.search(pattern, resp.text, re.DOTALL | re.IGNORECASE)
                if match:
                    candidate = html_to_text(match.group(1))
                    if len(candidate) > len(text):
                        text = candidate

            if not text or len(text) < 200:
                text = html_to_text(resp.text)

            if save_post(output_dir, slug, title, text, url):
                words = len(text.split())
                print(f"  [{saved+1}] SAVED: {slug[:60]} ({words:,} words) [{content_type}]")
                saved += 1

            time.sleep(2.0)
        except Exception as e:
            print(f"  Error on {slug}: {e}")
            time.sleep(2.0)

    print(f"  Done: {saved} new posts")
    return saved


# ── Subject definitions ──────────────────────────────────────────────────────

SUBJECTS = {
    "scott": {
        "name": "Scott Alexander",
        "type": "substack",
        "subdomain": "www.astralcodexten.com",
        "output": "scott_alexander_source",
        "target": 500,
        "skip_patterns": ["open-thread", "links-for", "mantic-monday",
                          "meetups-everywhere", "highlights-from-the-comments",
                          "classifieds-thread"],
    },
    "matt": {
        "name": "Matt Yglesias",
        "type": "substack",
        "subdomain": "www.slowboring.com",
        "output": "matt_yglesias_source",
        "target": 500,
        "skip_patterns": ["mailbag", "friday-thread", "open-thread"],
    },
    "ethan": {
        "name": "Ethan Mollick",
        "type": "substack",
        "subdomain": "www.oneusefulthing.org",
        "output": "ethan_mollick_source",
        "target": 300,
        "skip_patterns": [],
    },
    "cedric": {
        "name": "Cedric Chin",
        "type": "blog",
        "base_url": "https://commoncog.com",
        "output": "cedric_chin_source",
        "target": 500,
        "url_filter": lambda u: "/blog/" in u or "/case-library/" in u,
    },
    "cory": {
        "name": "Cory Doctorow",
        "type": "blog",
        "base_url": "https://pluralistic.net",
        "output": "cory_doctorow_source",
        "target": 500,
    },
    "fred": {
        "name": "Fred Wilson",
        "type": "blog",
        "base_url": "https://avc.com",
        "output": "fred_wilson_source",
        "target": 500,
    },
    "dan": {
        "name": "Dan Shipper",
        "type": "substack",
        "subdomain": "every.to",
        "output": "dan_shipper_source",
        "target": 300,
        "skip_patterns": ["napkin-math", "divinations", "superorganizers"],
    },
    "simon": {
        "name": "Simon Willison",
        "type": "simon",
        "output": "simon_willison_source",
        "target": 500,
    },
    "swyx": {
        "name": "swyx",
        "type": "swyx",
        "output": "swyx_source",
        "target": 300,
    },
    "anne": {
        "name": "Anne-Laure Le Cunff",
        "type": "blog",
        "base_url": "https://nesslabs.com",
        "output": "anne_source",
        "target": 500,
        "url_filter": lambda u: any(x in u for x in ["/blog/", "/articles/", "/20"]),
        "skip_patterns": ["/tag/", "/category/", "/page/"],
    },
    "david": {
        "name": "David Perell",
        "type": "david_perell",
        "output": "david_source",
        "target": 300,
    },
    "henrik": {
        "name": "Henrik Karlsson",
        "type": "substack",
        "subdomain": "www.henrikkarlsson.xyz",
        "output": "henrik_source",
        "target": 300,
        "skip_patterns": ["a-summary-of-what-i-wrote"],
    },
    "casey": {
        "name": "Casey Newton",
        "type": "blog",
        "base_url": "https://www.platformer.news",
        "output": "casey_newton_source",
        "target": 500,
        "skip_patterns": ["/tag/", "/author/", "/page/"],
    },
    "maggie": {
        "name": "Maggie Appleton",
        "type": "maggie",
        "output": "maggie_appleton_source",
        "target": 300,
    },
}


def scrape_subject(key, config):
    print(f"\n{'='*60}")
    print(f"  {config['name']} — V2 Expansion Scrape")
    output_dir = DATA_DIR / config["output"]
    print(f"  Output: {output_dir}")
    print(f"  Target: {config.get('target', 500)} posts")
    print(f"{'='*60}")

    stype = config["type"]
    if stype == "substack":
        return scrape_substack(
            config["subdomain"], output_dir,
            target=config.get("target", 500),
            skip_patterns=config.get("skip_patterns"),
        )
    elif stype == "simon":
        return scrape_simon_willison(output_dir, target=config.get("target", 500))
    elif stype == "swyx":
        return scrape_swyx(output_dir, target=config.get("target", 300))
    elif stype == "david_perell":
        return scrape_david_perell(output_dir, target=config.get("target", 300))
    elif stype == "maggie":
        return scrape_maggie_appleton(output_dir, target=config.get("target", 300))
    elif stype == "blog":
        return scrape_sitemap_blog(
            config["base_url"], output_dir,
            target=config.get("target", 500),
            url_filter=config.get("url_filter"),
            skip_patterns=config.get("skip_patterns"),
        )
    else:
        print(f"  Unknown type: {stype}")
        return 0


def main():
    parser = argparse.ArgumentParser(description="V2 Expansion Scraper")
    parser.add_argument("--only", help="Comma-separated subject keys (e.g. scott,matt)")
    parser.add_argument("--list", action="store_true", help="List available subjects")
    args = parser.parse_args()

    if args.list:
        for key, config in SUBJECTS.items():
            output_dir = DATA_DIR / config["output"]
            existing = len(list(output_dir.glob("*.txt"))) if output_dir.exists() else 0
            print(f"  {key:10s}  {config['name']:25s}  {existing:4d} files  target={config.get('target', 500)}")
        return

    if args.only:
        keys = [k.strip() for k in args.only.split(",")]
        invalid = [k for k in keys if k not in SUBJECTS]
        if invalid:
            print(f"Unknown subjects: {invalid}. Available: {list(SUBJECTS.keys())}")
            sys.exit(1)
    else:
        keys = list(SUBJECTS.keys())

    print(f"V2 Expansion Scraper — {len(keys)} subjects")
    print(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    results = {}
    for key in keys:
        try:
            new = scrape_subject(key, SUBJECTS[key])
            output_dir = DATA_DIR / SUBJECTS[key]["output"]
            total = len(list(output_dir.glob("*.txt")))
            results[key] = f"+{new} new ({total} total)"
        except Exception as e:
            results[key] = f"ERROR: {e}"

    print(f"\n{'='*60}")
    print("RESULTS:")
    for key, status in results.items():
        print(f"  {SUBJECTS[key]['name']:25s}  {status}")
    print(f"Completed: {time.strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
