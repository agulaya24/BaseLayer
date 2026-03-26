"""
Scraper for visakanv.com - blog posts + 1000 word vomits
Saves each post as .txt in visakan_veerasamy_source/
Resumable: skips already-downloaded files.
"""

import requests
import time
import re
import os
import sys
import json
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

sys.stdout.reconfigure(encoding='utf-8')

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "visakan_veerasamy_source")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Track URL -> filename mapping for resume
STATE_FILE = os.path.join(OUTPUT_DIR, "_scraper_state.json")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Referer': 'https://visakanv.com/',
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

MIN_WORDS = 200
BASE_DELAY = 1.5  # seconds between requests
BLOCK_BACKOFF = 30  # seconds to wait when blocked
MAX_CONSECUTIVE_ERRORS = 10


def log(msg):
    print(msg, flush=True)


def slugify(title):
    s = title.lower().strip()
    s = re.sub(r'[^\w\s-]', '', s)
    s = re.sub(r'[\s_]+', '-', s)
    s = re.sub(r'-+', '-', s)
    s = s.strip('-')
    return s[:120] if s else 'untitled'


def fetch(url, retries=3):
    for attempt in range(retries + 1):
        try:
            r = SESSION.get(url, timeout=15)
            if r.status_code == 200:
                return r
            elif r.status_code in (406, 429, 503):
                wait = BLOCK_BACKOFF * (attempt + 1)
                log(f"  HTTP {r.status_code} - backing off {wait}s...")
                time.sleep(wait)
                continue
            elif r.status_code == 404:
                return None
            else:
                log(f"  HTTP {r.status_code} for {url}")
                if attempt < retries:
                    time.sleep(5)
                    continue
                return None
        except requests.exceptions.Timeout:
            if attempt < retries:
                log(f"  Timeout, retry {attempt+1}...")
                time.sleep(5)
            else:
                log(f"  Timeout after {retries+1} attempts: {url}")
                return None
        except Exception as e:
            if attempt < retries:
                time.sleep(3)
            else:
                log(f"  Error: {e}")
                return None
    return None


def extract_post_content(soup):
    content_el = (
        soup.find('div', class_='entry-content') or
        soup.find('div', class_='post-content') or
        soup.find('article') or
        soup.find('div', class_='content') or
        soup.find('div', id='content')
    )
    if not content_el:
        return ""

    for tag in content_el.find_all(['script', 'style', 'nav', 'aside', 'footer']):
        tag.decompose()

    paragraphs = []
    for p in content_el.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'blockquote']):
        text = p.get_text(strip=True)
        if text:
            paragraphs.append(text)

    if not paragraphs:
        return content_el.get_text(separator='\n\n', strip=True)

    return '\n\n'.join(paragraphs)


def extract_title(soup, url=""):
    title_el = soup.find(class_='entry-title') or soup.find('h1', class_='post-title')
    if title_el:
        return title_el.get_text(strip=True)

    h1 = soup.find('h1')
    if h1:
        return h1.get_text(strip=True)

    if soup.title:
        t = soup.title.string or ""
        t = re.sub(r'\s*[\|:\u2013\u2014-]\s*(@?visakanv|visa|1000 word vomits).*$', '', t, flags=re.IGNORECASE)
        return t.strip()

    path = urlparse(url).path.rstrip('/')
    return path.split('/')[-1].replace('-', ' ').title() if path else "Untitled"


def save_post(title, content, url):
    word_count = len(content.split())
    if word_count < MIN_WORDS:
        return False

    slug = slugify(title)
    if not slug:
        slug = 'untitled'

    filepath = os.path.join(OUTPUT_DIR, f"{slug}.txt")

    counter = 1
    while os.path.exists(filepath):
        filepath = os.path.join(OUTPUT_DIR, f"{slug}-{counter}.txt")
        counter += 1

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(f"{title}\n\n{content}\n")

    return True


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {"done_urls": []}


def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)


def get_all_urls_from_sitemaps():
    """Get all post URLs from sitemaps."""
    log("Fetching URLs from sitemaps...")
    all_urls = set()

    sitemap_urls = [
        'https://visakanv.com/sitemap.xml',
        'https://visakanv.com/wp-sitemap.xml',
        'https://visakanv.com/blog/sitemap.xml',
        'https://visakanv.com/1000/sitemap.xml',
    ]

    for sitemap_url in sitemap_urls:
        r = fetch(sitemap_url)
        if not r or '<?xml' not in r.text[:200]:
            continue

        log(f"  Found: {sitemap_url}")
        soup = BeautifulSoup(r.text, 'xml')

        # Sub-sitemaps
        for sitemap in soup.find_all('sitemap'):
            loc = sitemap.find('loc')
            if not loc:
                continue
            sub_url = loc.text.strip()
            # Only fetch post sitemaps, skip categories/tags/authors/attachments
            if any(skip in sub_url for skip in ['category', 'tag', 'author', 'attachment', 'taxonom', 'user']):
                continue
            log(f"    Sub: {sub_url}")
            sr = fetch(sub_url)
            if sr and '<?xml' in sr.text[:200]:
                sub_soup = BeautifulSoup(sr.text, 'xml')
                for url_el in sub_soup.find_all('url'):
                    loc2 = url_el.find('loc')
                    if loc2:
                        u = loc2.text.strip()
                        if '/blog/' in u or '/1000/' in u:
                            all_urls.add(u)
            time.sleep(0.5)

        # Direct entries
        for url_el in soup.find_all('url'):
            loc = url_el.find('loc')
            if loc:
                u = loc.text.strip()
                if '/blog/' in u or '/1000/' in u:
                    all_urls.add(u)

        time.sleep(0.5)

    # Also check the word vomit index page for links not in sitemap
    log("  Checking word vomit index page...")
    r = fetch('https://visakanv.com/1000/')
    if r:
        soup = BeautifulSoup(r.text, 'html.parser')
        for a in soup.find_all('a', href=True):
            href = a['href']
            full_url = urljoin('https://visakanv.com/1000/', href)
            if re.search(r'/1000/\d{4}', full_url):
                all_urls.add(full_url)

    # Filter out index pages and normalize
    filtered = set()
    for u in all_urls:
        # Skip bare index pages
        path = urlparse(u).path.rstrip('/')
        if path in ('', '/blog', '/1000'):
            continue
        # Skip if it's a page (not a post) - WordPress pages like /blog/bookmarks
        # Keep everything and let word count filter handle it
        filtered.add(u)

    log(f"Total unique URLs found: {len(filtered)}")
    return filtered


def main():
    log("=== Visakan Veerasamy Blog Scraper ===\n")

    state = load_state()
    done_set = set(state["done_urls"])
    log(f"Previously completed: {len(done_set)} URLs\n")

    all_urls = get_all_urls_from_sitemaps()

    # Separate and sort
    vomit_urls = sorted([u for u in all_urls if '/1000/' in u])
    blog_urls = sorted([u for u in all_urls if '/blog/' in u])

    # Combine: vomits first (more valuable), then blog
    ordered = vomit_urls + blog_urls

    # Filter already done
    todo = [u for u in ordered if u not in done_set]
    log(f"URLs to process: {len(todo)} (skipping {len(ordered) - len(todo)} already done)")
    log(f"  Word vomits: {len(vomit_urls)}, Blog posts: {len(blog_urls)}")
    log("")

    saved = 0
    skipped_short = 0
    errors = 0
    consecutive_errors = 0

    for i, url in enumerate(todo):
        label = "Vomit" if "/1000/" in url else "Blog"
        log(f"[{i+1}/{len(todo)}] {label}: {url}")

        r = fetch(url)
        if not r:
            errors += 1
            consecutive_errors += 1
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                log(f"\n!!! {MAX_CONSECUTIVE_ERRORS} consecutive errors - site may be blocking. Pausing 60s...")
                time.sleep(60)
                consecutive_errors = 0
            time.sleep(BASE_DELAY)
            continue

        consecutive_errors = 0

        soup = BeautifulSoup(r.text, 'html.parser')
        title = extract_title(soup, url)
        content = extract_post_content(soup)

        if save_post(title, content, url):
            saved += 1
            log(f"  -> Saved: {title[:60]} ({len(content.split())} words)")
        else:
            skipped_short += 1
            wc = len(content.split()) if content else 0
            log(f"  -> Skipped ({wc} words): {title[:60]}")

        # Mark as done regardless of save/skip
        done_set.add(url)
        state["done_urls"] = list(done_set)

        # Save state every 50 URLs
        if (i + 1) % 50 == 0:
            save_state(state)
            log(f"  [checkpoint: {len(done_set)} done, {saved} saved]")

        time.sleep(BASE_DELAY)

    # Final state save
    save_state(state)

    # Count total files
    total_files = len([f for f in os.listdir(OUTPUT_DIR) if f.endswith('.txt') and not f.startswith('_')])

    log(f"\n=== DONE ===")
    log(f"This run - Saved: {saved}, Skipped short: {skipped_short}, Errors: {errors}")
    log(f"Total files in output: {total_files}")
    log(f"Output: {OUTPUT_DIR}")


if __name__ == '__main__':
    main()
