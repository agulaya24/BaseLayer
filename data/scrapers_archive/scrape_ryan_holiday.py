"""Scrape Ryan Holiday's blog posts from ryanholiday.net using the sitemap."""

import requests
import re
import os
import time
import unicodedata
from bs4 import BeautifulSoup

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "ryan_holiday_source")
os.makedirs(OUTPUT_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

MIN_WORD_COUNT = 200  # Skip short posts (quotes, promos)


def slugify(title):
    """Convert title to a clean filename slug."""
    title = unicodedata.normalize("NFKD", title)
    title = title.encode("ascii", "ignore").decode("ascii")
    title = title.lower().strip()
    title = re.sub(r"[^\w\s-]", "", title)
    title = re.sub(r"[-\s]+", "-", title)
    return title[:80].strip("-")


def get_post_urls():
    """Get all post URLs from the sitemap."""
    r = requests.get("https://ryanholiday.net/post-sitemap.xml", headers=HEADERS, timeout=30)
    r.raise_for_status()
    urls = re.findall(r"<loc>(https://ryanholiday\.net/[^<]+)</loc>", r.text)
    print(f"Found {len(urls)} URLs in sitemap")
    return urls


def extract_post(url):
    """Extract title and body text from a blog post URL."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
    except Exception as e:
        print(f"  FAILED to fetch {url}: {e}")
        return None, None

    soup = BeautifulSoup(r.text, "html.parser")

    # Try to get the title
    title_tag = soup.find("h1", class_="entry-title") or soup.find("h1")
    if title_tag:
        title = title_tag.get_text(strip=True)
    else:
        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True).split("|")[0].strip() if title_tag else ""

    if not title:
        return None, None

    # Try to get the article body
    content_div = (
        soup.find("div", class_="entry-content")
        or soup.find("article")
        or soup.find("div", class_="post-content")
        or soup.find("div", class_="content")
    )

    if not content_div:
        return title, None

    # Remove scripts, styles, social sharing, etc.
    for tag in content_div.find_all(["script", "style", "iframe", "noscript", "nav"]):
        tag.decompose()

    # Remove common non-content elements
    for cls in ["sharedaddy", "jp-relatedposts", "social-share", "newsletter-signup",
                "email-signup", "post-tags", "author-bio", "related-posts"]:
        for el in content_div.find_all(class_=re.compile(cls, re.I)):
            el.decompose()

    # Extract text paragraph by paragraph
    paragraphs = []
    for p in content_div.find_all(["p", "h2", "h3", "h4", "blockquote", "li"]):
        text = p.get_text(strip=True)
        if text and len(text) > 5:
            paragraphs.append(text)

    body = "\n\n".join(paragraphs)
    return title, body


def main():
    urls = get_post_urls()

    # Filter out obvious non-essay URLs
    skip_patterns = [
        "/cart", "/checkout", "/my-account", "/shop", "/product",
        "/tag/", "/category/", "/author/", "/page/",
        "/reading-list-", "/reading-newsletter",
    ]

    filtered_urls = []
    for url in urls:
        path = url.replace("https://ryanholiday.net", "").lower()
        if not any(pat in path for pat in skip_patterns):
            filtered_urls.append(url)

    print(f"After filtering: {len(filtered_urls)} candidate URLs")

    saved = 0
    skipped_short = 0
    skipped_error = 0
    already_exists = 0

    for i, url in enumerate(filtered_urls):
        # Progress
        if i % 25 == 0:
            print(f"Processing {i}/{len(filtered_urls)}... (saved: {saved})")

        title, body = extract_post(url)

        if not title or not body:
            skipped_error += 1
            time.sleep(0.5)
            continue

        # Check word count
        word_count = len(body.split())
        if word_count < MIN_WORD_COUNT:
            skipped_short += 1
            time.sleep(0.5)
            continue

        slug = slugify(title)
        if not slug:
            slug = f"post-{i}"

        filepath = os.path.join(OUTPUT_DIR, f"{slug}.txt")

        # Skip if already scraped
        if os.path.exists(filepath):
            already_exists += 1
            time.sleep(0.3)
            continue

        content = f"{title}\n\n{body}"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        saved += 1
        time.sleep(1)  # Polite delay

    print(f"\n=== DONE ===")
    print(f"Total URLs in sitemap: {len(urls)}")
    print(f"After filtering: {len(filtered_urls)}")
    print(f"Saved: {saved}")
    print(f"Already existed: {already_exists}")
    print(f"Skipped (too short <{MIN_WORD_COUNT} words): {skipped_short}")
    print(f"Skipped (error/no content): {skipped_error}")
    print(f"Output dir: {OUTPUT_DIR}")

    # List files
    files = os.listdir(OUTPUT_DIR)
    txt_files = [f for f in files if f.endswith(".txt")]
    print(f"Total .txt files in output dir: {len(txt_files)}")


if __name__ == "__main__":
    main()
