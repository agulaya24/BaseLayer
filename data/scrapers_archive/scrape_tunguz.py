"""
Scraper for Tomasz Tunguz's blog at tomtunguz.com (Hugo site)
Strategy:
1. Get all post URLs from sitemap.xml (~1800 post URLs)
2. Sample ~200 evenly across the list for temporal diversity
3. Fetch each, extract date from .post-date div, content from .post-content
4. Skip 404s (old posts that didn't migrate) and short posts
5. Keep 50-80 substantial posts (500+ words)
"""

import requests
from bs4 import BeautifulSoup
import re
import os
import time
import json
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.parse import urlparse

OUTPUT_DIR = r"C:\Users\Aarik\Anthropic\memory_system\data\tomasz_tunguz_source"
os.makedirs(OUTPUT_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# Session for connection reuse
session = requests.Session()
session.headers.update(HEADERS)


def get_all_post_urls():
    """Get all post URLs from sitemap, filtering to actual posts."""
    r = session.get("https://tomtunguz.com/sitemap.xml", timeout=15)
    root = ET.fromstring(r.text)
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}

    all_urls = []
    for url_elem in root.findall(".//s:url/s:loc", ns):
        url = url_elem.text
        all_urls.append(url)

    # Filter to post URLs only (single slug path, not categories/tags/etc.)
    skip_slugs = {
        "categories", "guides", "about", "tags", "page", "author",
        "feed", "post", "search", "series", "contact", "archive"
    }

    post_urls = []
    seen = set()
    for url in all_urls:
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        # Must be a single-level slug
        parts = path.split("/")
        if len(parts) != 1 or not parts[0] or len(parts[0]) < 4:
            continue
        slug = parts[0]
        if slug in skip_slugs or slug.startswith("categories"):
            continue
        if url not in seen:
            seen.add(url)
            post_urls.append(url)

    return post_urls


def extract_post(url):
    """Fetch a single post and extract title, date, and clean text."""
    try:
        r = session.get(url, timeout=15, allow_redirects=True)
        if r.status_code != 200:
            return None

        # Check for 404 page (Hugo returns 200 for soft 404s)
        if "404 Page not found" in r.text[:1000]:
            return None

        soup = BeautifulSoup(r.text, "html.parser")

        # Title from h1.post-title or first h1
        title_elem = soup.find("h1", class_="post-title") or soup.find("h1")
        if not title_elem:
            return None
        title = title_elem.get_text(strip=True)

        # Skip non-article pages
        if title in ("Posts", "Categories", "Guides", "Search"):
            return None

        # Date from .post-date div (format: "March 20, 2026")
        date_str = ""
        date_elem = soup.find(class_="post-date")
        if date_elem:
            date_str = date_elem.get_text(strip=True)

        # Categories
        categories = []
        cat_tags = soup.find_all(class_="category-tag")
        for ct in cat_tags:
            categories.append(ct.get_text(strip=True))

        # Content from .post-content div
        content_elem = soup.find(class_="post-content")
        if not content_elem:
            # Fallback to article or main
            content_elem = soup.find("article") or soup.find("main")
        if not content_elem:
            return None

        # Remove noise
        for tag in content_elem.find_all(["script", "style", "nav", "footer", "iframe", "form", "noscript", "svg"]):
            tag.decompose()
        for cls in ["share", "social", "newsletter", "subscribe", "related", "comments", "sidebar", "footnotes", "post-nav"]:
            for elem in content_elem.find_all(class_=re.compile(cls, re.I)):
                elem.decompose()

        # Extract text preserving structure
        paragraphs = []
        for elem in content_elem.find_all(["p", "h2", "h3", "h4", "li", "blockquote"]):
            text = elem.get_text(strip=True)
            if not text or len(text) < 10:
                continue
            # Skip footnote references
            if text.startswith("[") and text.endswith("]"):
                continue
            if elem.name in ("h2", "h3", "h4"):
                paragraphs.append(f"\n## {text}\n")
            elif elem.name == "blockquote":
                paragraphs.append(f"> {text}")
            elif elem.name == "li":
                paragraphs.append(f"- {text}")
            else:
                paragraphs.append(text)

        content = "\n\n".join(paragraphs)
        word_count = len(content.split())

        if word_count < 50:
            return None

        return {
            "title": title,
            "date": date_str,
            "url": url,
            "content": content,
            "word_count": word_count,
            "categories": categories,
        }
    except Exception as e:
        return None


def parse_date(date_str):
    """Parse date string like 'March 20, 2026' to datetime."""
    if not date_str:
        return None
    for fmt in ["%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%B %Y"]:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except:
            pass
    m = re.search(r"(\d{4})", date_str)
    if m:
        try:
            return datetime(int(m.group(1)), 1, 1)
        except:
            pass
    return None


def slug_from_title(title):
    """Clean filename slug from title."""
    slug = title.lower()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s]+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    slug = slug.strip('-')
    return slug[:70]


def main():
    print("=" * 60)
    print("Scraping Tomasz Tunguz's blog (v2)")
    print("=" * 60)

    # Clear old files
    for f in os.listdir(OUTPUT_DIR):
        if f.endswith('.txt'):
            os.remove(os.path.join(OUTPUT_DIR, f))
    print("Cleared old files")

    # Step 1: Get all post URLs from sitemap
    print("\n--- Step 1: Getting post URLs from sitemap ---")
    post_urls = get_all_post_urls()
    print(f"Found {len(post_urls)} post URLs")

    # Step 2: Sample broadly - take ~200 evenly spaced URLs
    # The sitemap likely has recent posts first, so even spacing gives temporal diversity
    target_fetch = 220
    if len(post_urls) > target_fetch:
        step = len(post_urls) / target_fetch
        sampled = [post_urls[int(i * step)] for i in range(target_fetch)]
    else:
        sampled = post_urls
    print(f"Sampled {len(sampled)} URLs to fetch")

    # Step 3: Fetch and extract
    print(f"\n--- Step 2: Fetching posts ---")
    posts = []
    skipped_404 = 0
    skipped_short = 0

    for i, url in enumerate(sampled):
        slug = url.rstrip("/").split("/")[-1]
        print(f"[{i+1}/{len(sampled)}] {slug}", end=" ")

        post = extract_post(url)
        if post is None:
            print("-> SKIP (404/empty)")
            skipped_404 += 1
        elif post["word_count"] < 300:
            print(f"-> skip ({post['word_count']}w too short)")
            skipped_short += 1
        else:
            dt = parse_date(post["date"])
            year = dt.year if dt else "?"
            print(f"-> {post['word_count']}w [{year}] {post['title'][:50]}")
            posts.append(post)

        # Rate limit: 0.3s between requests
        time.sleep(0.3)

    print(f"\n--- Results ---")
    print(f"Fetched: {len(sampled)}")
    print(f"404/empty: {skipped_404}")
    print(f"Too short: {skipped_short}")
    print(f"Extracted: {len(posts)}")

    # Step 4: Select best 50-80 posts
    # Prioritize: longer posts, temporal diversity
    substantial = [p for p in posts if p["word_count"] >= 500]
    medium = [p for p in posts if 300 <= p["word_count"] < 500]

    print(f"\nSubstantial (500+w): {len(substantial)}")
    print(f"Medium (300-499w): {len(medium)}")

    # Start with all substantial posts
    selected = list(substantial)

    # If under 50, add medium posts (longest first)
    if len(selected) < 50:
        medium.sort(key=lambda x: x["word_count"], reverse=True)
        selected.extend(medium[:50 - len(selected)])

    # If over 80, keep top 80 by word count but ensure year diversity
    if len(selected) > 80:
        # Group by year, take proportionally
        by_year = {}
        for p in selected:
            dt = parse_date(p["date"])
            yr = dt.year if dt else 0
            by_year.setdefault(yr, []).append(p)

        final = []
        per_year = max(3, 80 // max(len(by_year), 1))
        for yr in sorted(by_year.keys()):
            yr_posts = sorted(by_year[yr], key=lambda x: x["word_count"], reverse=True)
            final.extend(yr_posts[:per_year])

        # Fill remaining slots with longest overall
        if len(final) < 80:
            remaining = [p for p in selected if p not in final]
            remaining.sort(key=lambda x: x["word_count"], reverse=True)
            final.extend(remaining[:80 - len(final)])

        selected = final[:80]

    print(f"Selected: {len(selected)} posts")

    # Step 5: Save files
    print(f"\n--- Step 3: Saving to {OUTPUT_DIR} ---")
    saved = 0
    for post in selected:
        dt = parse_date(post["date"])
        date_prefix = dt.strftime("%Y") if dt else "unknown"

        slug = slug_from_title(post["title"])
        if not slug:
            slug = post["url"].rstrip("/").split("/")[-1]

        filename = f"{date_prefix}_{slug}.txt"
        filepath = os.path.join(OUTPUT_DIR, filename)

        counter = 1
        while os.path.exists(filepath):
            filename = f"{date_prefix}_{slug}_{counter}.txt"
            filepath = os.path.join(OUTPUT_DIR, filename)
            counter += 1

        header = f"Title: {post['title']}\n"
        if post["date"]:
            header += f"Date: {post['date']}\n"
        header += f"URL: {post['url']}\n"
        header += f"Word Count: {post['word_count']}\n"
        if post.get("categories"):
            header += f"Categories: {', '.join(post['categories'])}\n"
        header += "-" * 60 + "\n\n"

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(header + post["content"])

        saved += 1

    print(f"Saved {saved} files")

    # Summary
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")

    years = {}
    for post in selected:
        dt = parse_date(post["date"])
        yr = dt.year if dt else "unknown"
        years[yr] = years.get(yr, 0) + 1

    print(f"\nPosts by year:")
    for yr in sorted(years.keys(), key=lambda x: str(x)):
        print(f"  {yr}: {years[yr]}")

    total_words = sum(p["word_count"] for p in selected)
    avg_words = total_words // len(selected) if selected else 0
    print(f"\nTotal posts: {len(selected)}")
    print(f"Total words: {total_words:,}")
    print(f"Average words/post: {avg_words}")
    print(f"Output: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
