"""
Scrape Morgan Housel essays from Collaborative Fund blog.
Saves substantive posts as .txt files to morgan_housel_source/
"""
import requests
from bs4 import BeautifulSoup
import re
import os
import time
import unicodedata

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "morgan_housel_source")
os.makedirs(OUTPUT_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

BASE_URL = "https://collabfund.com"

def slugify(title):
    title = unicodedata.normalize("NFKD", title)
    title = title.encode("ascii", "ignore").decode("ascii")
    title = re.sub(r"[^\w\s-]", "", title.lower())
    title = re.sub(r"[-\s]+", "-", title).strip("-")
    return title[:80]

def get_all_post_links():
    """Crawl paginated blog listing pages filtered to Morgan Housel posts."""
    all_links = []

    # First try the Morgan author page
    print("Fetching Morgan Housel author page...")
    try:
        r = requests.get(f"{BASE_URL}/blog/authors/morgan/", headers=HEADERS, timeout=30)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            links = soup.find_all("a", href=re.compile(r"^/blog/[a-z0-9]"))
            for link in links:
                href = link.get("href", "")
                if href and "/authors/" not in href and href != "/blog/" and not re.match(r"/blog/\d+/", href):
                    all_links.append(href)
            print(f"  Found {len(all_links)} links on author page")
    except Exception as e:
        print(f"  Author page failed: {e}")

    # Also crawl paginated blog pages to find Morgan's posts
    # The author page may not have all posts
    page = 1
    consecutive_empty = 0
    while consecutive_empty < 3:
        url = f"{BASE_URL}/blog/" if page == 1 else f"{BASE_URL}/blog/{page}/"
        print(f"Fetching blog page {page}...")
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code != 200:
                print(f"  Status {r.status_code}, stopping pagination")
                break

            soup = BeautifulSoup(r.text, "html.parser")
            links = soup.find_all("a", href=re.compile(r"^/blog/[a-z0-9]"))
            page_links = []
            for link in links:
                href = link.get("href", "")
                if href and "/authors/" not in href and href != "/blog/" and not re.match(r"/blog/\d+/", href):
                    page_links.append(href)

            new_count = 0
            for href in page_links:
                if href not in all_links:
                    all_links.append(href)
                    new_count += 1

            print(f"  Found {len(page_links)} links, {new_count} new")
            if new_count == 0:
                consecutive_empty += 1
            else:
                consecutive_empty = 0

        except Exception as e:
            print(f"  Error: {e}")
            consecutive_empty += 1

        page += 1
        time.sleep(1)

    # Deduplicate
    seen = set()
    unique = []
    for link in all_links:
        if link not in seen:
            seen.add(link)
            unique.append(link)

    return unique

def is_morgan_post(soup):
    """Check if a post is by Morgan Housel."""
    text = soup.get_text().lower()
    # Check for author attribution
    author_links = soup.find_all("a", href=re.compile(r"/authors/morgan"))
    if author_links:
        return True
    # Check meta or byline
    for el in soup.find_all(class_=re.compile(r"author|byline|meta", re.I)):
        if "morgan" in el.get_text().lower():
            return True
    return False

def extract_post(url):
    """Fetch a post and extract title + body text."""
    full_url = BASE_URL + url if url.startswith("/") else url
    r = requests.get(full_url, headers=HEADERS, timeout=30)
    if r.status_code != 200:
        return None, None, False

    soup = BeautifulSoup(r.text, "html.parser")

    # Check author
    morgan = is_morgan_post(soup)

    # Extract title
    title_el = soup.find("h1")
    title = title_el.get_text(strip=True) if title_el else ""

    # Extract body - look for article/post content
    body = None
    for selector in ["article", ".post-content", ".post__content", ".entry-content", ".blog-post", "main"]:
        if selector.startswith("."):
            body = soup.find(class_=selector[1:])
        else:
            body = soup.find(selector)
        if body:
            break

    if not body:
        body = soup.find("main") or soup.find("body")

    if not body:
        return title, "", morgan

    # Remove script, style, nav elements
    for tag in body.find_all(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()

    # Get text
    paragraphs = []
    for el in body.find_all(["p", "h2", "h3", "h4", "blockquote", "li"]):
        text = el.get_text(strip=True)
        if text and len(text) > 1:
            if el.name in ["h2", "h3", "h4"]:
                paragraphs.append(f"\n{text}\n")
            elif el.name == "blockquote":
                paragraphs.append(f'"{text}"')
            else:
                paragraphs.append(text)

    full_text = "\n\n".join(paragraphs)
    return title, full_text, morgan

def main():
    print("=" * 60)
    print("Morgan Housel Scraper - Collaborative Fund Blog")
    print("=" * 60)

    # Get all post links
    post_links = get_all_post_links()
    print(f"\nTotal unique post links found: {len(post_links)}")

    # Fetch each post
    saved = 0
    skipped_author = 0
    skipped_short = 0
    skipped_error = 0

    for i, link in enumerate(post_links):
        print(f"\n[{i+1}/{len(post_links)}] {link}")

        try:
            title, text, is_morgan = extract_post(link)

            if not title and not text:
                print("  SKIP: failed to extract")
                skipped_error += 1
                continue

            if not is_morgan:
                print(f"  SKIP: not Morgan Housel")
                skipped_author += 1
                continue

            word_count = len(text.split()) if text else 0
            if word_count < 200:
                print(f"  SKIP: too short ({word_count} words)")
                skipped_short += 1
                continue

            # Save
            slug = slugify(title) if title else link.strip("/").split("/")[-1]
            filename = f"{slug}.txt"
            filepath = os.path.join(OUTPUT_DIR, filename)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"{title}\n\n{text}")

            print(f"  SAVED: {filename} ({word_count} words)")
            saved += 1

        except Exception as e:
            print(f"  ERROR: {e}")
            skipped_error += 1

        time.sleep(1)

    print("\n" + "=" * 60)
    print(f"DONE: {saved} posts saved")
    print(f"  Skipped (not Morgan): {skipped_author}")
    print(f"  Skipped (too short): {skipped_short}")
    print(f"  Skipped (error): {skipped_error}")
    print(f"  Output: {OUTPUT_DIR}")
    print("=" * 60)

if __name__ == "__main__":
    main()
