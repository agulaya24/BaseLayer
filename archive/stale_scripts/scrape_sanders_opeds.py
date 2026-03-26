"""
Scrape Bernie Sanders op-eds from sanders.senate.gov/op-eds/
Save as individual .txt files to subjects/bernie_sanders_memory/data/sources/op-eds/
"""

import os
import re
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime

BASE_URL = "https://www.sanders.senate.gov/op-eds/"
OUTPUT_DIR = r"C:\Users\Aarik\Anthropic\subjects\bernie_sanders_memory\data\sources\op-eds"
os.makedirs(OUTPUT_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def slugify(text):
    """Convert title to filename-safe slug."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'-+', '-', text)
    text = text.strip('-')
    return text[:80]  # cap length

def parse_date(date_str):
    """Parse date string into YYYY-MM-DD format."""
    date_str = date_str.strip()
    formats = [
        "%B %d, %Y",      # "February 5, 2026"
        "%b %d, %Y",      # "Feb 5, 2026"
        "%m/%d/%Y",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y-%m-%d"), dt.strftime("%Y")
        except ValueError:
            continue
    return date_str, "unknown"

def get_article_links(page_num):
    """Get all op-ed links from a listing page."""
    if page_num == 1:
        url = BASE_URL
    else:
        url = f"{BASE_URL}page/{page_num}/"

    print(f"  Fetching listing page {page_num}: {url}")
    resp = requests.get(url, headers=HEADERS, timeout=30)
    if resp.status_code != 200:
        print(f"  Page {page_num} returned status {resp.status_code}, stopping.")
        return []

    soup = BeautifulSoup(resp.text, 'html.parser')
    links = []

    # Find all article links - they're in the main content area
    # Look for links that point to /op-eds/something/
    for a in soup.find_all('a', href=True):
        href = a['href']
        if '/op-eds/' in href and href != '/op-eds/' and href != BASE_URL:
            # Skip pagination links
            if '/page/' in href:
                continue
            full_url = href if href.startswith('http') else f"https://www.sanders.senate.gov{href}"
            if full_url not in [l[0] for l in links]:
                title_text = a.get_text(strip=True)
                if title_text and len(title_text) > 5:
                    links.append((full_url, title_text))

    return links

def scrape_article(url):
    """Scrape a single op-ed article. Returns (title, date, text) or None."""
    resp = requests.get(url, headers=HEADERS, timeout=30)
    if resp.status_code != 200:
        print(f"    Failed to fetch {url}: {resp.status_code}")
        return None

    soup = BeautifulSoup(resp.text, 'html.parser')

    # Get title - try multiple selectors
    title = None
    for sel in ['h1.entry-title', 'h1.page-title', 'h1']:
        tag = soup.select_one(sel)
        if tag:
            title = tag.get_text(strip=True)
            break
    if not title:
        title = "Untitled"

    # Get date - look for time tags, date classes, or meta
    date_str = ""
    # Try time tag
    time_tag = soup.find('time')
    if time_tag:
        date_str = time_tag.get('datetime', '') or time_tag.get_text(strip=True)

    # Try common date selectors
    if not date_str:
        for sel in ['.entry-date', '.post-date', '.date', '.published', '.meta-date']:
            tag = soup.select_one(sel)
            if tag:
                date_str = tag.get_text(strip=True)
                break

    # Try meta tags
    if not date_str:
        meta = soup.find('meta', {'property': 'article:published_time'})
        if meta:
            date_str = meta.get('content', '')[:10]

    # Get article content
    content = None

    # Try multiple content selectors
    for sel in ['.entry-content', '.post-content', 'article .content',
                '.single-content', '.article-content', 'article', '.post-body',
                'main .content', '#content', '.wp-block-post-content']:
        tag = soup.select_one(sel)
        if tag:
            # Remove scripts, styles, nav elements
            for unwanted in tag.find_all(['script', 'style', 'nav', 'footer', 'header', 'aside', 'form']):
                unwanted.decompose()

            paragraphs = tag.find_all(['p', 'h2', 'h3', 'h4', 'li', 'blockquote'])
            if paragraphs:
                texts = []
                for p in paragraphs:
                    t = p.get_text(strip=True)
                    if t:
                        texts.append(t)
                if len(texts) > 2:  # Reasonable article
                    content = '\n\n'.join(texts)
                    break

    # Fallback: get all paragraphs from main/article
    if not content:
        main = soup.find('main') or soup.find('article') or soup.find('div', class_=re.compile(r'content|post|entry'))
        if main:
            for unwanted in main.find_all(['script', 'style', 'nav', 'footer', 'header', 'aside', 'form']):
                unwanted.decompose()
            paragraphs = main.find_all('p')
            texts = [p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)]
            if len(texts) > 2:
                content = '\n\n'.join(texts)

    if not content:
        print(f"    Could not extract content from {url}")
        return None

    return title, date_str, content

def main():
    print("Starting Bernie Sanders op-ed scraper...")
    print(f"Output: {OUTPUT_DIR}\n")

    all_articles = []  # (url, title)

    # Scrape listing pages
    for page in range(1, 25):  # Go up to 25 to be safe
        links = get_article_links(page)
        if not links:
            print(f"  No more articles found at page {page}. Done with listings.\n")
            break
        all_articles.extend(links)
        print(f"  Found {len(links)} articles on page {page} (total: {len(all_articles)})")
        time.sleep(1)

    print(f"\nTotal articles found: {len(all_articles)}")
    print("Scraping individual articles...\n")

    saved = 0
    failed = 0

    for i, (url, listing_title) in enumerate(all_articles):
        print(f"  [{i+1}/{len(all_articles)}] {listing_title[:60]}...")

        result = scrape_article(url)
        if not result:
            failed += 1
            time.sleep(1)
            continue

        title, date_str, content = result

        # Parse the date
        date_formatted, year = parse_date(date_str)

        # If date parse failed, try to extract year from formatted date
        if year == "unknown" and date_str:
            year_match = re.search(r'20\d{2}', date_str)
            if year_match:
                year = year_match.group()

        # Create filename
        slug = slugify(title)
        filename = f"{year}_{slug}.txt"
        filepath = os.path.join(OUTPUT_DIR, filename)

        # Handle duplicates
        counter = 1
        while os.path.exists(filepath):
            filename = f"{year}_{slug}_{counter}.txt"
            filepath = os.path.join(OUTPUT_DIR, filename)
            counter += 1

        # Write file
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"Title: {title}\n")
            f.write(f"Date: {date_formatted}\n")
            f.write(f"Source: {url}\n")
            f.write(f"{'='*80}\n\n")
            f.write(content)

        saved += 1
        print(f"    Saved: {filename}")
        time.sleep(1.5)  # Be polite

    print(f"\n{'='*60}")
    print(f"DONE. Saved: {saved}, Failed: {failed}, Total found: {len(all_articles)}")
    print(f"Output: {OUTPUT_DIR}")

if __name__ == "__main__":
    main()
