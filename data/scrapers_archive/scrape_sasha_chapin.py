"""
Scrape Sasha Chapin's writing from Substack (sitemap-based).
The archive API only returns ~23 recent posts, but the sitemap has 270.
Saves each post as .txt with title as first line.
"""

import os
import re
import time
import requests
from html.parser import HTMLParser

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "sasha_chapin_source")
os.makedirs(OUTPUT_DIR, exist_ok=True)

DELAY = 1.0
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


class HTMLToText(HTMLParser):
    """Strip HTML tags, keep text with paragraph breaks."""
    def __init__(self):
        super().__init__()
        self.text = []
        self.skip = False
        self.block_tags = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6",
                           "li", "blockquote", "br", "tr", "figcaption"}

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.skip = True
        if tag in self.block_tags:
            self.text.append("\n")
        if tag == "br":
            self.text.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.skip = False
        if tag in self.block_tags:
            self.text.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.text.append(data)

    def get_text(self):
        raw = "".join(self.text)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()


def html_to_text(html):
    parser = HTMLToText()
    parser.feed(html)
    return parser.get_text()


def slugify(title):
    s = title.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")[:80]


def get_slugs_from_sitemap():
    """Extract all post slugs from the Substack sitemap."""
    resp = requests.get("https://sashachapin.substack.com/sitemap.xml",
                        headers=HEADERS, timeout=30)
    resp.raise_for_status()
    slugs = re.findall(
        r'<loc>https://sashachapin\.substack\.com/p/([^<]+)</loc>',
        resp.text
    )
    return slugs


def fetch_post(slug):
    """Fetch post title and body HTML from Substack API."""
    url = f"https://sashachapin.substack.com/api/v1/posts/{slug}"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    title = data.get("title", "Untitled")
    body_html = data.get("body_html", "")
    return title, body_html


def main():
    print("=" * 60)
    print("Sasha Chapin Scraper (sitemap-based)")
    print("=" * 60)

    # 1. Get all slugs from sitemap
    print("\n[1] Fetching sitemap...")
    slugs = get_slugs_from_sitemap()
    print(f"  Found {len(slugs)} posts in sitemap")

    # 2. Check which we already have
    existing = set(os.listdir(OUTPUT_DIR))
    print(f"  {len(existing)} files already in output dir")

    # 3. Download each post
    saved = 0
    skipped_exists = 0
    skipped_no_body = 0
    skipped_short = 0
    errors = 0
    rate_limit_waits = 0

    print(f"\n[2] Downloading posts...")
    for i, slug in enumerate(slugs):
        # We can't know the file slug until we fetch the title,
        # but we can check if the API slug matches an existing file
        # Quick check: if any file starts similarly, skip
        # Better: just try to fetch and check after getting title

        try:
            # First fetch the post
            title, body_html = fetch_post(slug)
            file_slug = slugify(title) if title != "Untitled" else slug
            filepath = os.path.join(OUTPUT_DIR, f"{file_slug}.txt")

            # Skip if already downloaded
            if os.path.exists(filepath):
                print(f"  [{i+1}/{len(slugs)}] SKIP (exists): {title}")
                skipped_exists += 1
                time.sleep(0.3)  # lighter delay for skips
                continue

            if not body_html:
                print(f"  [{i+1}/{len(slugs)}] No body: {title}")
                skipped_no_body += 1
                time.sleep(0.3)
                continue

            text = html_to_text(body_html)
            if len(text) < 200:
                print(f"  [{i+1}/{len(slugs)}] Too short ({len(text)} chars): {title}")
                skipped_short += 1
                time.sleep(0.3)
                continue

            content = f"{title}\n\n{text}\n"
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            saved += 1
            print(f"  [{i+1}/{len(slugs)}] Saved ({len(text):,} chars): {title}")
            time.sleep(DELAY)

        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 429:
                rate_limit_waits += 1
                print(f"  [{i+1}/{len(slugs)}] Rate limited, waiting 10s...")
                time.sleep(10)
                # Retry once
                try:
                    title, body_html = fetch_post(slug)
                    file_slug = slugify(title) if title != "Untitled" else slug
                    filepath = os.path.join(OUTPUT_DIR, f"{file_slug}.txt")
                    if body_html:
                        text = html_to_text(body_html)
                        if len(text) >= 200:
                            content = f"{title}\n\n{text}\n"
                            with open(filepath, "w", encoding="utf-8") as f:
                                f.write(content)
                            saved += 1
                            print(f"    -> Retry OK ({len(text):,} chars): {title}")
                        else:
                            skipped_short += 1
                    else:
                        skipped_no_body += 1
                    time.sleep(DELAY)
                except Exception as e2:
                    print(f"    -> Retry failed: {e2}")
                    errors += 1
                    time.sleep(DELAY)
            else:
                print(f"  [{i+1}/{len(slugs)}] ERROR ({slug}): {e}")
                errors += 1
                time.sleep(DELAY)
        except Exception as e:
            print(f"  [{i+1}/{len(slugs)}] ERROR ({slug}): {e}")
            errors += 1
            time.sleep(DELAY)

    # Summary
    files = sorted(os.listdir(OUTPUT_DIR))
    print(f"\n{'=' * 60}")
    print(f"RESULTS:")
    print(f"  Sitemap posts:     {len(slugs)}")
    print(f"  New saved:         {saved}")
    print(f"  Skipped (exists):  {skipped_exists}")
    print(f"  Skipped (no body): {skipped_no_body}")
    print(f"  Skipped (short):   {skipped_short}")
    print(f"  Errors:            {errors}")
    print(f"  Rate limit waits:  {rate_limit_waits}")
    print(f"  Total files:       {len(files)}")
    print(f"  Output dir:        {OUTPUT_DIR}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
