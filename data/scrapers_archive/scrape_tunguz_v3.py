"""
Scraper v3: Lower threshold to 300w, aim for 70-80 posts with year diversity.
Re-uses the already-fetched data approach but adjusts selection.
"""

import requests
from bs4 import BeautifulSoup
import re
import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.parse import urlparse

OUTPUT_DIR = r"C:\Users\Aarik\Anthropic\memory_system\data\tomasz_tunguz_source"
os.makedirs(OUTPUT_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

session = requests.Session()
session.headers.update(HEADERS)


def get_all_post_urls():
    r = session.get("https://tomtunguz.com/sitemap.xml", timeout=15)
    root = ET.fromstring(r.text)
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    skip_slugs = {
        "categories", "guides", "about", "tags", "page", "author",
        "feed", "post", "search", "series", "contact", "archive"
    }
    post_urls = []
    seen = set()
    for url_elem in root.findall(".//s:url/s:loc", ns):
        url = url_elem.text
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        parts = path.split("/")
        if len(parts) != 1 or not parts[0] or len(parts[0]) < 4:
            continue
        if parts[0] in skip_slugs:
            continue
        if url not in seen:
            seen.add(url)
            post_urls.append(url)
    return post_urls


def extract_post(url):
    try:
        r = session.get(url, timeout=15, allow_redirects=True)
        if r.status_code != 200:
            return None
        if "404 Page not found" in r.text[:1000]:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        title_elem = soup.find("h1", class_="post-title") or soup.find("h1")
        if not title_elem:
            return None
        title = title_elem.get_text(strip=True)
        if title in ("Posts", "Categories", "Guides", "Search"):
            return None

        date_str = ""
        date_elem = soup.find(class_="post-date")
        if date_elem:
            date_str = date_elem.get_text(strip=True)

        categories = [ct.get_text(strip=True) for ct in soup.find_all(class_="category-tag")]

        content_elem = soup.find(class_="post-content")
        if not content_elem:
            content_elem = soup.find("article") or soup.find("main")
        if not content_elem:
            return None

        for tag in content_elem.find_all(["script", "style", "nav", "footer", "iframe", "form", "noscript", "svg"]):
            tag.decompose()
        for cls in ["share", "social", "newsletter", "subscribe", "related", "comments", "sidebar", "footnotes", "post-nav"]:
            for elem in content_elem.find_all(class_=re.compile(cls, re.I)):
                elem.decompose()

        paragraphs = []
        for elem in content_elem.find_all(["p", "h2", "h3", "h4", "li", "blockquote"]):
            text = elem.get_text(strip=True)
            if not text or len(text) < 10:
                continue
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
            "title": title, "date": date_str, "url": url,
            "content": content, "word_count": word_count, "categories": categories,
        }
    except:
        return None


def parse_date(date_str):
    if not date_str:
        return None
    for fmt in ["%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"]:
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
    slug = title.lower()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s]+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    return slug.strip('-')[:70]


def main():
    print("=" * 60)
    print("Scraping Tomasz Tunguz's blog (v3 - broader)")
    print("=" * 60)

    # Clear old files
    for f in os.listdir(OUTPUT_DIR):
        if f.endswith('.txt'):
            os.remove(os.path.join(OUTPUT_DIR, f))

    # Get URLs
    post_urls = get_all_post_urls()
    print(f"Sitemap: {len(post_urls)} post URLs")

    # Sample 300 evenly for broader coverage
    target_fetch = 300
    step = len(post_urls) / target_fetch
    sampled = [post_urls[int(i * step)] for i in range(target_fetch)]
    print(f"Sampling {len(sampled)} URLs")

    # Fetch
    posts = []
    for i, url in enumerate(sampled):
        slug = url.rstrip("/").split("/")[-1]
        if (i + 1) % 20 == 0:
            print(f"  [{i+1}/{len(sampled)}] fetched {len(posts)} good so far...")
        post = extract_post(url)
        if post and post["word_count"] >= 300:
            posts.append(post)
        time.sleep(0.25)

    print(f"\nExtracted {len(posts)} posts (300+ words)")

    # Group by year
    by_year = {}
    for p in posts:
        dt = parse_date(p["date"])
        yr = dt.year if dt else 0
        by_year.setdefault(yr, []).append(p)

    print("\nPosts by year (before selection):")
    for yr in sorted(by_year.keys()):
        print(f"  {yr}: {len(by_year[yr])}")

    # Select: aim for 70-80 total, distribute across years
    # Give each year a minimum of 3, then fill with longest posts
    target = 75
    years = sorted([y for y in by_year.keys() if y > 0])
    per_year_min = max(2, target // len(years)) if years else 5

    selected = []
    for yr in years:
        yr_posts = sorted(by_year[yr], key=lambda x: x["word_count"], reverse=True)
        selected.extend(yr_posts[:per_year_min])

    # If under target, add more from longest remaining
    if len(selected) < target:
        remaining = [p for p in posts if p not in selected and parse_date(p["date"])]
        remaining.sort(key=lambda x: x["word_count"], reverse=True)
        selected.extend(remaining[:target - len(selected)])

    # If over target, trim years with too many
    if len(selected) > 80:
        selected.sort(key=lambda x: x["word_count"], reverse=True)
        selected = selected[:80]

    print(f"\nSelected: {len(selected)} posts")

    # Save
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

    # Final summary
    print(f"\n{'=' * 60}")
    print("FINAL SUMMARY")
    print(f"{'=' * 60}")
    years_final = {}
    for p in selected:
        dt = parse_date(p["date"])
        yr = dt.year if dt else "unknown"
        years_final[yr] = years_final.get(yr, 0) + 1
    for yr in sorted(years_final.keys(), key=lambda x: str(x)):
        print(f"  {yr}: {years_final[yr]}")
    total_words = sum(p["word_count"] for p in selected)
    avg = total_words // len(selected) if selected else 0
    print(f"\nSaved: {saved} posts")
    print(f"Total words: {total_words:,}")
    print(f"Average: {avg} words/post")
    print(f"Output: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
