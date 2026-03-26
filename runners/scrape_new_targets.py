#!/usr/bin/env python3
"""
Scrape blog content for new outreach targets.
Targets: Ava Huang (bookbear express), Nabeel Qureshi, Julia Galef, Tim Urban (waitbutwhy)

Usage:
    python scrape_new_targets.py                  # all targets
    python scrape_new_targets.py --only ava       # one target
    python scrape_new_targets.py --only ava,nabeel # multiple
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

DATA_DIR = Path(r"C:\Users\Aarik\Anthropic\memory_system\data")
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; BaselayerBot/1.0)"}


# ── HTML-to-text (same as scrape_v2_expansion.py) ────────────────────────────

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
        return False
    if len(text) < 200:
        return False
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


# ── Blog sitemap/RSS scraper ─────────────────────────────────────────────────

def scrape_rss_urls(base_url):
    """Fall back to RSS feed for URL discovery."""
    urls = []
    rss_paths = ["/feed", "/rss", "/feed.xml", "/rss.xml", "/atom.xml", "/index.xml"]
    for path in rss_paths:
        try:
            resp = requests.get(f"{base_url}{path}", headers=HEADERS, timeout=15)
            if resp.status_code == 200:
                for match in re.finditer(r"<link>([^<]+)</link>", resp.text):
                    url = match.group(1).strip()
                    if url.startswith("http") and url != base_url and url != f"{base_url}/":
                        urls.append(url)
                for match in re.finditer(r'href="([^"]+)"', resp.text):
                    url = match.group(1).strip()
                    if url.startswith("http") and ("/post" in url or "/p/" in url or "/20" in url):
                        urls.append(url)
                if urls:
                    print(f"  Found {len(urls)} URLs from RSS at {base_url}{path}")
                    break
        except Exception:
            continue
    return list(dict.fromkeys(urls))


def scrape_sitemap_blog(base_url, output_dir, target=500, url_filter=None, skip_patterns=None):
    """Scrape blog posts via sitemap.xml."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    existing = len(list(output_dir.glob("*.txt")))
    print(f"  Existing files: {existing}")

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

    if url_filter:
        urls = [u for u in urls if url_filter(u)]
    if skip_patterns:
        urls = [u for u in urls if not any(p in u for p in skip_patterns)]

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

            title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
            title = html_to_text(title_match.group(1)).strip() if title_match else slug

            text = ""
            for sel in ["article", "main", "div class=\"post-content\"",
                        "div class=\"entry-content\"", "div class=\"prose\"",
                        "div class=\"content\""]:
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


# ── Nabeel Qureshi special scraper ────────────────────────────────────────────

def scrape_nabeel(output_dir, target=200):
    """nabeelqu.co — static site + Substack at nabeelqu.substack.com."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    existing = len(list(output_dir.glob("*.txt")))
    print(f"  Existing files: {existing}")

    saved = 0

    # Part 1: nabeelqu.co blog via sitemap
    base_url = "https://nabeelqu.co"
    urls = []

    for sitemap_path in ["/sitemap.xml", "/sitemap_index.xml"]:
        try:
            resp = requests.get(f"{base_url}{sitemap_path}", headers=HEADERS, timeout=15)
            if resp.status_code == 200:
                root = ElementTree.fromstring(resp.content)
                ns = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}
                for loc in root.findall(".//ns:url/ns:loc", ns):
                    urls.append(loc.text)
                if urls:
                    print(f"  Found {len(urls)} URLs from sitemap")
                    break
        except Exception:
            continue

    if not urls:
        urls = scrape_rss_urls(base_url)

    # Filter
    urls = [u for u in urls if not any(x in u for x in [
        "/tag/", "/category/", "/author/", "/page/", "/wp-content/",
        "/feed/", "#", "?",
    ])]

    print(f"  {len(urls)} blog URLs after filtering. Fetching new ones...")

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

            title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
            title = html_to_text(title_match.group(1)).strip() if title_match else slug

            text = ""
            for sel in ["article", "main", "div class=\"post-content\"",
                        "div class=\"entry-content\"", "div class=\"prose\"",
                        "div class=\"content\"", "div class=\"post\""]:
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
                print(f"  [{saved+1}] SAVED: {slug[:60]} ({words:,} words) [blog]")
                saved += 1

            time.sleep(1.5)
        except Exception as e:
            print(f"  Error on {url[:60]}: {e}")
            time.sleep(2.0)

    blog_saved = saved

    # Part 2: nabeelqu.substack.com
    print(f"\n  Fetching Substack posts from nabeelqu.substack.com...")
    substack_saved = scrape_substack_to_dir(
        "nabeelqu.substack.com", output_dir, target=target, prefix="substack_"
    )
    saved += substack_saved

    print(f"  Done: {blog_saved} blog + {substack_saved} Substack = {saved} total new")
    return saved


def scrape_substack_to_dir(subdomain, output_dir, target=500, prefix="", skip_patterns=None):
    """Scrape Substack posts into an existing directory with optional filename prefix."""
    base_url = f"https://{subdomain}"
    api_url = f"{base_url}/api/v1/archive"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

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
            print(f"  Substack API error at offset {offset}: {e}")
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

    print(f"  Found {len(collected)} free Substack posts. Fetching new ones...")

    saved = 0
    for post in collected:
        slug = post["slug"]
        title = post["title"]
        filepath = output_dir / (sanitize_filename(f"{prefix}{slug}") + ".txt")
        if filepath.exists():
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
            if save_post(output_dir, f"{prefix}{slug}", title, text, post_url):
                words = len(text.split())
                print(f"  [{saved+1}] SAVED: {prefix}{slug} ({words:,} words) [substack]")
                saved += 1
            time.sleep(2.0)
        except requests.exceptions.HTTPError as e:
            if e.response and e.response.status_code == 429:
                print(f"  Rate limited, waiting 15s...")
                time.sleep(15)
            else:
                print(f"  Error on {slug}: {e}")
            time.sleep(3.0)
        except Exception as e:
            print(f"  Error on {slug}: {e}")
            time.sleep(2.0)

    return saved


# ── Julia Galef scraper ───────────────────────────────────────────────────────

def scrape_julia_galef(output_dir, target=200):
    """juliagalef.com blog + possible Substack."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    existing = len(list(output_dir.glob("*.txt")))
    print(f"  Existing files: {existing}")

    saved = 0

    # Try juliagalef.com first (WordPress blog)
    print(f"  Trying juliagalef.com...")
    saved += scrape_sitemap_blog(
        "https://juliagalef.com", output_dir, target=target,
        skip_patterns=["/tag/", "/category/", "/page/"],
    )

    # Also try her Substack if it exists
    print(f"  Trying Julia Galef Substack...")
    try:
        resp = requests.get("https://juliagalef.substack.com/api/v1/archive",
                          params={"sort": "new", "offset": 0, "limit": 10},
                          headers=HEADERS, timeout=15)
        if resp.status_code == 200 and resp.json():
            print(f"  Substack found! Scraping...")
            saved += scrape_substack("juliagalef.substack.com", output_dir,
                                     target=target)
    except Exception:
        print(f"  No Substack found.")

    return saved


# ── Tim Urban / Wait But Why scraper ──────────────────────────────────────────

def scrape_waitbutwhy(output_dir, target=200):
    """waitbutwhy.com — WordPress, long-form essays."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    existing = len(list(output_dir.glob("*.txt")))
    print(f"  Existing files: {existing}")

    base_url = "https://waitbutwhy.com"

    # Try sitemap
    saved = scrape_sitemap_blog(
        base_url, output_dir, target=target,
        skip_patterns=["/tag/", "/category/", "/page/", "/author/"],
    )

    return saved


# ── Subject definitions ──────────────────────────────────────────────────────

SUBJECTS = {
    "ava": {
        "name": "Ava Huang",
        "type": "substack",
        "subdomain": "www.avabear.xyz",
        "output": "ava_huang_source",
        "target": 300,
        "skip_patterns": [],
    },
    "nabeel": {
        "name": "Nabeel Qureshi",
        "type": "nabeel",
        "output": "nabeel_qureshi_source",
        "target": 200,
    },
    "julia": {
        "name": "Julia Galef",
        "type": "julia",
        "output": "julia_galef_source",
        "target": 200,
    },
    "tim": {
        "name": "Tim Urban",
        "type": "waitbutwhy",
        "output": "tim_urban_source",
        "target": 200,
    },
}


def scrape_subject(key, config):
    print(f"\n{'='*60}")
    print(f"  {config['name']} — New Target Scrape")
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
    elif stype == "nabeel":
        return scrape_nabeel(output_dir, target=config.get("target", 200))
    elif stype == "julia":
        return scrape_julia_galef(output_dir, target=config.get("target", 200))
    elif stype == "waitbutwhy":
        return scrape_waitbutwhy(output_dir, target=config.get("target", 200))
    else:
        print(f"  Unknown type: {stype}")
        return 0


def count_words(output_dir):
    """Count total words across all .txt files in a directory."""
    total = 0
    output_dir = Path(output_dir)
    if output_dir.exists():
        for f in output_dir.glob("*.txt"):
            try:
                total += len(f.read_text(encoding="utf-8").split())
            except Exception:
                pass
    return total


def main():
    parser = argparse.ArgumentParser(description="New Targets Scraper")
    parser.add_argument("--only", help="Comma-separated subject keys (e.g. ava,nabeel)")
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

    print(f"New Targets Scraper — {len(keys)} subjects")
    print(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    results = {}
    for key in keys:
        try:
            new = scrape_subject(key, SUBJECTS[key])
            output_dir = DATA_DIR / SUBJECTS[key]["output"]
            total = len(list(output_dir.glob("*.txt")))
            words = count_words(output_dir)
            results[key] = {"new": new, "total": total, "words": words}
        except Exception as e:
            results[key] = {"error": str(e)}

    print(f"\n{'='*60}")
    print("RESULTS:")
    print(f"{'='*60}")
    for key, status in results.items():
        name = SUBJECTS[key]["name"]
        if "error" in status:
            print(f"  {name:25s}  ERROR: {status['error']}")
        else:
            print(f"  {name:25s}  {status['total']:4d} files  ~{status['words']:,} words  (+{status['new']} new)")
    print(f"\nCompleted: {time.strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
