"""
Scrape Seth Godin's blog (seths.blog) for substantive posts via WordPress REST API.
Strategy:
1. Use WP REST API to paginate through all posts (per_page=100 -> ~97 requests)
2. Extract title + rendered content, compute word count
3. Filter for posts >= 200 words
4. Save top 200 longest posts as .txt files
"""

import requests
from bs4 import BeautifulSoup
import os
import re
import sys
import time
import unicodedata

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seth_godin_source")
os.makedirs(OUTPUT_DIR, exist_ok=True)

PROGRESS_FILE = os.path.join(OUTPUT_DIR, "_progress.txt")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

API_URL = "https://seths.blog/wp-json/wp/v2/posts"


def log(msg):
    print(msg, flush=True)
    with open(PROGRESS_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def slugify(text):
    """Convert title to a clean filename slug."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    text = text.strip("-")
    return text[:80] if text else "untitled"


def html_to_text(html):
    """Convert HTML content to clean plain text."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["script", "style"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def fetch_all_posts():
    """Fetch all posts via WP REST API, return list of (title, text, word_count)."""
    posts = []
    page = 1
    total_pages = None

    while True:
        params = {
            "per_page": 100,
            "page": page,
            "_fields": "id,title,content",
        }
        try:
            r = requests.get(API_URL, params=params, headers=HEADERS, timeout=30)
        except Exception as e:
            log(f"  ERROR on page {page}: {e}")
            time.sleep(5)
            continue

        if r.status_code == 400:
            log(f"  Page {page}: no more results (HTTP 400)")
            break

        if r.status_code != 200:
            log(f"  Page {page}: HTTP {r.status_code}, retrying...")
            time.sleep(5)
            continue

        if total_pages is None:
            total_pages = int(r.headers.get("X-WP-TotalPages", 0))
            total_posts = int(r.headers.get("X-WP-Total", 0))
            log(f"Total posts: {total_posts}, Total pages: {total_pages}")

        data = r.json()
        if not data:
            break

        for p in data:
            title = BeautifulSoup(p["title"]["rendered"], "html.parser").get_text()
            text = html_to_text(p["content"]["rendered"])
            wc = len(text.split())
            posts.append((title, text, wc))

        log(f"  Page {page}/{total_pages} - {len(posts)} posts fetched, {sum(1 for _,_,w in posts if w >= 200)} substantial")

        page += 1
        time.sleep(1)

        if total_pages and page > total_pages:
            break

    return posts


def main():
    # Clear progress file
    with open(PROGRESS_FILE, "w") as f:
        f.write("")

    log("Fetching all posts via WordPress REST API...")
    posts = fetch_all_posts()
    log(f"\nTotal posts fetched: {len(posts)}")

    # Filter for >= 200 words
    substantial = [(t, txt, wc) for t, txt, wc in posts if wc >= 200]
    log(f"Posts with >= 200 words: {len(substantial)}")

    # Sort by word count (longest first), take top 200
    substantial.sort(key=lambda x: x[2], reverse=True)
    selected = substantial[:200]

    if selected:
        log(f"\nSelected {len(selected)} posts:")
        log(f"  Longest:  {selected[0][2]} words - {selected[0][0][:60]}")
        log(f"  Shortest: {selected[-1][2]} words - {selected[-1][0][:60]}")

    # Save to files
    used_slugs = set()
    saved = 0
    for title, text, wc in selected:
        slug = slugify(title)
        if not slug or slug in used_slugs:
            slug = slug + "-" + str(saved)
        used_slugs.add(slug)

        filename = f"{slug}.txt"
        filepath = os.path.join(OUTPUT_DIR, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"{title}\n\n{text}\n")

        saved += 1

    log(f"\nDone! Saved {saved} posts to {OUTPUT_DIR}")

    # Print word count distribution
    if substantial:
        wcs = [wc for _, _, wc in substantial]
        log(f"\nWord count distribution (all {len(substantial)} substantial posts):")
        log(f"  Min: {min(wcs)}, Max: {max(wcs)}, Median: {sorted(wcs)[len(wcs)//2]}")
        brackets = [200, 300, 500, 750, 1000, 1500, 2000, 5000]
        for i, b in enumerate(brackets):
            upper = brackets[i+1] if i+1 < len(brackets) else 999999
            count = sum(1 for w in wcs if b <= w < upper)
            log(f"  {b}-{upper if upper < 999999 else '+'}: {count}")


if __name__ == "__main__":
    main()
