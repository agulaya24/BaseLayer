"""
Scraper for Spencer Greenberg's essays from spencergreenberg.com
Extracts titles and full text, saves as .txt files.
"""

import requests
import re
import os
import time
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "spencer_greenberg_source")
SITEMAP_URL = "https://www.spencergreenberg.com/sitemap-1.xml"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}
MIN_WORDS = 200
DELAY = 1.0


class HTMLTextExtractor(HTMLParser):
    """Extract text from HTML, keeping paragraph structure."""

    def __init__(self):
        super().__init__()
        self.result = []
        self.current_text = []
        self.skip = False
        self.skip_tags = {'script', 'style', 'nav', 'header', 'footer', 'aside', 'noscript'}
        self.block_tags = {'p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                          'li', 'blockquote', 'br', 'tr', 'pre'}
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.skip_tags:
            self.skip_depth += 1
            self.skip = True
        if tag in self.block_tags and not self.skip:
            text = ''.join(self.current_text).strip()
            if text:
                self.result.append(text)
            self.current_text = []

    def handle_endtag(self, tag):
        if tag in self.skip_tags and self.skip_depth > 0:
            self.skip_depth -= 1
            if self.skip_depth == 0:
                self.skip = False
        if tag in self.block_tags and not self.skip:
            text = ''.join(self.current_text).strip()
            if text:
                self.result.append(text)
            self.current_text = []

    def handle_data(self, data):
        if not self.skip:
            self.current_text.append(data)

    def get_text(self):
        # Flush remaining
        text = ''.join(self.current_text).strip()
        if text:
            self.result.append(text)
        return '\n\n'.join(self.result)


def extract_article_content(html):
    """Extract article content from WordPress post HTML."""
    # Try to find the entry-content div (WordPress standard)
    match = re.search(r'<div[^>]*class="[^"]*entry-content[^"]*"[^>]*>(.*?)</div>\s*(?:<footer|<div[^>]*class="[^"]*(?:post-meta|entry-footer|sharedaddy))', html, re.DOTALL)
    if not match:
        # Broader match
        match = re.search(r'<div[^>]*class="[^"]*entry-content[^"]*"[^>]*>(.*?)</div>\s*<(?:footer|div class="sharedaddy|div class="jp-relatedposts)', html, re.DOTALL)
    if not match:
        # Even broader - just get entry-content
        match = re.search(r'<div[^>]*class="[^"]*entry-content[^"]*"[^>]*>(.*?)</div>\s*</(?:article|main)', html, re.DOTALL)
    if not match:
        # Last resort - get everything between entry-content and the next major section
        match = re.search(r'<div[^>]*class="[^"]*entry-content[^"]*"[^>]*>(.*)', html, re.DOTALL)
        if match:
            content = match.group(1)
            # Cut at sharing buttons or related posts
            for cutoff in ['<div class="sharedaddy', '<div id="jp-relatedposts', '<footer', '<!-- .entry-content']:
                idx = content.find(cutoff)
                if idx > 0:
                    content = content[:idx]
            match = type('Match', (), {'group': lambda self, n: content})()

    if not match:
        return None

    content_html = match.group(1)

    extractor = HTMLTextExtractor()
    extractor.feed(content_html)
    text = extractor.get_text()

    # Clean up
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()

    return text


def extract_title(html):
    """Extract post title from HTML."""
    match = re.search(r'<h1[^>]*class="[^"]*entry-title[^"]*"[^>]*>(.*?)</h1>', html, re.DOTALL)
    if not match:
        match = re.search(r'<title>(.*?)(?:\s*[-|].*)?</title>', html)
    if match:
        title = re.sub(r'<[^>]+>', '', match.group(1)).strip()
        # Decode HTML entities
        title = title.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
        title = title.replace('&#8217;', "'").replace('&#8220;', '"').replace('&#8221;', '"')
        title = title.replace('&#8211;', '-').replace('&#8212;', '--').replace('&nbsp;', ' ')
        title = title.replace('&#038;', '&').replace('&#8216;', "'")
        return title
    return None


def make_slug(url):
    """Create filename slug from URL."""
    # Extract the last path component
    parts = url.rstrip('/').split('/')
    slug = parts[-1]
    # Clean it
    slug = re.sub(r'[^a-z0-9-]', '', slug.lower())
    slug = re.sub(r'-+', '-', slug).strip('-')
    return slug[:80]  # Cap length


def get_post_urls():
    """Get all post URLs from sitemap."""
    print("Fetching sitemap...")
    resp = requests.get(SITEMAP_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    # Parse XML - handle namespace
    content = resp.text
    urls = re.findall(r'<loc>([^<]+)</loc>', content)

    # Filter to only blog post URLs (have /YYYY/MM/ pattern)
    posts = [u for u in urls if re.search(r'/\d{4}/\d{2}/', u)]

    # Exclude known non-essay pages
    skip_slugs = {'hello-world', 'welcome', 'good-reads', 'keyboard-commands',
                  'urltotext', 'subscribe', 'thanks', 'newsletter-thanks',
                  'picture', 'videos', 'work', 'contact-spencer', 'spencer-greenberg'}
    posts = [u for u in posts if u.rstrip('/').split('/')[-1] not in skip_slugs]

    print(f"Found {len(posts)} post URLs in sitemap")
    return posts


def scrape_essay(url):
    """Scrape a single essay. Returns (title, text) or None."""
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    html = resp.text

    title = extract_title(html)
    text = extract_article_content(html)

    if not title or not text:
        return None

    word_count = len(text.split())
    if word_count < MIN_WORDS:
        return None

    return title, text, word_count


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    urls = get_post_urls()

    saved = 0
    skipped_short = 0
    skipped_error = 0

    for i, url in enumerate(urls):
        slug = make_slug(url)
        filepath = os.path.join(OUTPUT_DIR, f"{slug}.txt")

        if os.path.exists(filepath):
            print(f"[{i+1}/{len(urls)}] SKIP (exists): {slug}")
            saved += 1
            continue

        try:
            result = scrape_essay(url)
            if result is None:
                print(f"[{i+1}/{len(urls)}] SKIP (short/no content): {slug}")
                skipped_short += 1
            else:
                title, text, wc = result
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(f"{title}\n\n{text}\n")
                print(f"[{i+1}/{len(urls)}] SAVED: {slug} ({wc} words)")
                saved += 1
        except Exception as e:
            print(f"[{i+1}/{len(urls)}] ERROR: {slug} - {e}")
            skipped_error += 1

        time.sleep(DELAY)

    print(f"\n{'='*60}")
    print(f"COMPLETE: {saved} essays saved, {skipped_short} too short, {skipped_error} errors")
    print(f"Output: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
