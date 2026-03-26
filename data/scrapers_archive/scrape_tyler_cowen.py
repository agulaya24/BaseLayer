"""
Scrape Tyler Cowen substantive essays from Marginal Revolution via RSS feed.
The site has Cloudflare protection, but RSS feed bypasses it.
Filters for Tyler Cowen as author, 400+ words, saves as .txt files.
Target: 100-150 substantive posts.
"""
import requests
import xml.etree.ElementTree as ET
import re
import os
import time
import unicodedata
from html.parser import HTMLParser

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tyler_cowen_source")
os.makedirs(OUTPUT_DIR, exist_ok=True)

FEED_URL = "https://marginalrevolution.com/feed"
TARGET_COUNT = 150  # Stop after this many saved
WORD_MIN = 400

# Short link-post indicators (titles that suggest link roundups, not essays)
LINK_POST_PATTERNS = [
    r"^links for",
    r"^assorted links",
    r"^morning links",
    r"^evening links",
    r"^weekend links",
    r"^friday links",
    r"^saturday links",
    r"^sunday links",
    r"^monday links",
    r"^tuesday links",
    r"^wednesday links",
    r"^thursday links",
    r"^markets in everything",  # typically short
    r"^fact of the day",
    r"^sentence of the day",
    r"^sentences to ponder",
    r"^the culture that is",
    r"^what i.ve been reading",
    r"^my conversation with",  # podcast transcripts
    r"^bonus.*conversation",
]

class HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.result = []
        self.skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip = True
        if tag in ("p", "br", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "li"):
            self.result.append("\n\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = False

    def handle_data(self, data):
        if not self.skip:
            self.result.append(data)

def strip_html(html_text):
    stripper = HTMLStripper()
    try:
        stripper.feed(html_text)
    except:
        return re.sub(r'<[^>]+>', ' ', html_text)
    text = "".join(stripper.result)
    # Clean up whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()

def slugify(title):
    title = unicodedata.normalize("NFKD", title)
    title = title.encode("ascii", "ignore").decode("ascii")
    title = re.sub(r"[^\w\s-]", "", title.lower())
    title = re.sub(r"[-\s]+", "-", title).strip("-")
    return title[:80]

def is_link_post(title):
    """Check if title matches known link-roundup patterns."""
    title_lower = title.lower().strip()
    for pattern in LINK_POST_PATTERNS:
        if re.match(pattern, title_lower):
            return True
    return False

def is_substantive(text, title):
    """Check if post is substantive (not just links/quotes)."""
    words = text.split()
    word_count = len(words)

    if word_count < WORD_MIN:
        return False, word_count

    # Check for excessive links (link roundups)
    link_count = text.lower().count("http://") + text.lower().count("https://")
    if link_count > 10 and word_count < 600:
        return False, word_count

    return True, word_count

def parse_feed_page(page_num):
    """Fetch and parse one page of the RSS feed."""
    url = FEED_URL if page_num == 1 else f"{FEED_URL}?paged={page_num}"
    try:
        r = requests.get(url, timeout=30, headers={
            "User-Agent": "Mozilla/5.0 (compatible; BaseLayer/1.0)",
            "Accept": "application/rss+xml, application/xml, text/xml",
        })
        if r.status_code != 200:
            return []

        # Parse XML
        # Handle CDATA sections properly
        root = ET.fromstring(r.content)
        items = []

        ns = {
            "content": "http://purl.org/rss/1.0/modules/content/",
            "dc": "http://purl.org/dc/elements/1.1/",
        }

        for item in root.findall(".//item"):
            title_el = item.find("title")
            creator_el = item.find("dc:creator", ns)
            content_el = item.find("content:encoded", ns)
            link_el = item.find("link")
            pubdate_el = item.find("pubDate")

            title = title_el.text if title_el is not None and title_el.text else ""
            creator = creator_el.text if creator_el is not None and creator_el.text else ""
            content = content_el.text if content_el is not None and content_el.text else ""
            link = link_el.text if link_el is not None and link_el.text else ""
            pubdate = pubdate_el.text if pubdate_el is not None and pubdate_el.text else ""

            items.append({
                "title": title,
                "creator": creator,
                "content": content,
                "link": link,
                "pubdate": pubdate,
            })

        return items
    except Exception as e:
        print(f"  Error fetching page {page_num}: {e}")
        return []

def main():
    print("=" * 60)
    print("Tyler Cowen Scraper - Marginal Revolution (RSS)")
    print(f"Target: {TARGET_COUNT} substantive posts ({WORD_MIN}+ words)")
    print("=" * 60)

    saved = 0
    skipped_author = 0
    skipped_short = 0
    skipped_links = 0
    skipped_dupe = 0
    total_scanned = 0
    saved_slugs = set()

    # Scan pages. MR has 15 posts per page.
    # With ~22 years of daily posts, we need to go deep.
    # Strategy: scan sequentially until we hit target.
    # Tyler posts substantive essays maybe 1 in 5-10 posts.
    page = 1
    max_pages = 2000  # Safety limit (~30,000 posts)
    empty_streak = 0

    while saved < TARGET_COUNT and page <= max_pages and empty_streak < 5:
        items = parse_feed_page(page)
        if not items:
            empty_streak += 1
            print(f"Page {page}: empty or error (streak: {empty_streak})")
            page += 1
            time.sleep(1)
            continue

        empty_streak = 0
        page_saved = 0

        for item in items:
            total_scanned += 1

            # Filter: Tyler Cowen only
            if "Tyler Cowen" not in item["creator"]:
                skipped_author += 1
                continue

            title = item["title"]

            # Filter: skip known link-post patterns
            if is_link_post(title):
                skipped_links += 1
                continue

            # Strip HTML from content
            text = strip_html(item["content"])

            # Filter: substantive (400+ words)
            is_sub, word_count = is_substantive(text, title)
            if not is_sub:
                skipped_short += 1
                continue

            # Generate slug and check for dupes
            slug = slugify(title) if title else f"post-{total_scanned}"
            if slug in saved_slugs:
                skipped_dupe += 1
                continue
            saved_slugs.add(slug)

            # Save
            filename = f"{slug}.txt"
            filepath = os.path.join(OUTPUT_DIR, filename)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"{title}\n\n{text}")

            saved += 1
            page_saved += 1

            if saved >= TARGET_COUNT:
                break

        print(f"Page {page}: scanned {len(items)}, saved {page_saved} (total: {saved}/{TARGET_COUNT})")
        page += 1
        time.sleep(1)  # Respect crawl delay

    print("\n" + "=" * 60)
    print(f"DONE: {saved} substantive posts saved")
    print(f"  Total scanned: {total_scanned}")
    print(f"  Skipped (not Tyler): {skipped_author}")
    print(f"  Skipped (link posts): {skipped_links}")
    print(f"  Skipped (<{WORD_MIN} words): {skipped_short}")
    print(f"  Skipped (duplicate): {skipped_dupe}")
    print(f"  Pages crawled: {page - 1}")
    print(f"  Output: {OUTPUT_DIR}")
    print("=" * 60)

if __name__ == "__main__":
    main()
