"""Scrape Jerry Chen's blog posts from Greylock and Medium."""
import requests
from bs4 import BeautifulSoup
import re
import os
import time
from urllib.parse import urljoin

OUTPUT_DIR = r"C:\Users\Aarik\Anthropic\memory_system\data\jerry_chen_source"
os.makedirs(OUTPUT_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def slugify(title):
    s = title.lower().strip()
    s = re.sub(r'[^\w\s-]', '', s)
    s = re.sub(r'[\s_]+', '-', s)
    s = re.sub(r'-+', '-', s)
    return s[:80].strip('-')

def extract_text_from_article(soup):
    """Extract clean text from article body."""
    # Try common article containers
    for selector in ['article', '.post-content', '.article-content', '.entry-content',
                     '[class*="content"]', '.section-inner', 'main']:
        content = soup.select_one(selector)
        if content:
            # Remove script, style, nav, header, footer
            for tag in content.find_all(['script', 'style', 'nav', 'header', 'footer', 'aside']):
                tag.decompose()
            text = content.get_text(separator='\n', strip=True)
            if len(text) > 200:
                return text
    # Fallback: get all paragraphs
    paragraphs = soup.find_all('p')
    text = '\n\n'.join(p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 20)
    return text

def save_post(title, date, url, text, output_dir):
    if not text or len(text) < 100:
        print(f"  SKIP (too short): {title}")
        return False
    slug = slugify(title)
    filename = f"{date}_{slug}.txt"
    filepath = os.path.join(output_dir, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(f"Title: {title}\n")
        f.write(f"Date: {date}\n")
        f.write(f"Source: {url}\n")
        f.write(f"\n{'='*80}\n\n")
        f.write(text)
    print(f"  SAVED: {filename} ({len(text)} chars)")
    return True

def scrape_greylock_blog():
    """Scrape Jerry Chen posts from greylock.com."""
    print("=== Scraping Greylock Blog ===")

    # Known Jerry Chen URLs from greylock.com
    known_urls = [
        "https://greylock.com/greymatter/the-new-new-moats/",
        "https://greylock.com/greymatter/castles-in-the-cloud/",
        "https://greylock.com/jerry-chen-riding-the-waves-of-change/",
        "https://greylock.com/greymatter/chronosphere/",
    ]

    # Try to find more from the blog index
    try:
        # Scrape the blog page for Jerry Chen posts
        for page in range(1, 10):
            url = f"https://greylock.com/blog/page/{page}/" if page > 1 else "https://greylock.com/blog/"
            print(f"  Fetching blog index: {url}")
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                print(f"  Status {resp.status_code}, stopping pagination")
                break
            soup = BeautifulSoup(resp.text, 'lxml')
            links = soup.find_all('a', href=True)
            for link in links:
                href = link['href']
                text = link.get_text(strip=True).lower()
                if 'jerry' in text or 'chen' in text:
                    full_url = urljoin("https://greylock.com", href)
                    if full_url not in known_urls and '/greymatter/' in full_url:
                        known_urls.append(full_url)
                # Also grab greymatter articles
                if '/greymatter/' in href and href not in known_urls:
                    full_url = urljoin("https://greylock.com", href)
                    if full_url not in known_urls:
                        known_urls.append(full_url)
            time.sleep(1)
    except Exception as e:
        print(f"  Error fetching blog index: {e}")

    # Also try the greymatter index
    try:
        url = "https://greylock.com/blog/greymatter/"
        print(f"  Fetching greymatter index: {url}")
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'lxml')
            links = soup.find_all('a', href=True)
            for link in links:
                href = link['href']
                if '/greymatter/' in href and href != '/blog/greymatter/' and 'greylock.com' in href or href.startswith('/'):
                    full_url = urljoin("https://greylock.com", href)
                    if full_url not in known_urls and full_url != "https://greylock.com/blog/greymatter/":
                        known_urls.append(full_url)
    except Exception as e:
        print(f"  Error: {e}")

    print(f"  Found {len(known_urls)} Greylock URLs to check")

    saved = 0
    for url in known_urls:
        try:
            print(f"  Fetching: {url}")
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                print(f"    Status {resp.status_code}")
                continue
            soup = BeautifulSoup(resp.text, 'lxml')

            # Check if Jerry Chen is the author
            page_text = resp.text.lower()
            is_jerry = 'jerry chen' in page_text or 'jerry-chen' in url.lower()

            title_tag = soup.find('h1')
            title = title_tag.get_text(strip=True) if title_tag else url.split('/')[-2].replace('-', ' ').title()

            # Try to find date
            date = "2023-01-01"  # default
            date_tag = soup.find('time')
            if date_tag:
                date_text = date_tag.get('datetime', date_tag.get_text(strip=True))
                date_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', date_text)
                if date_match:
                    date = date_match.group(0)
            else:
                # Try to find date in text
                date_match = re.search(r'(\d{2})\.(\d{2})\.(\d{4})', page_text)
                if date_match:
                    date = f"{date_match.group(3)}-{date_match.group(1)}-{date_match.group(2)}"

            text = extract_text_from_article(soup)

            if is_jerry and text and len(text) > 200:
                if save_post(title, date, url, text, OUTPUT_DIR):
                    saved += 1
            elif not is_jerry:
                print(f"    Not by Jerry Chen, skipping")

            time.sleep(1.5)
        except Exception as e:
            print(f"    Error: {e}")

    return saved

def scrape_medium():
    """Scrape Jerry Chen's Medium posts."""
    print("\n=== Scraping Medium ===")

    known_medium_urls = [
        "https://medium.com/greylock-perspectives/unit-of-value-a-framework-for-scaling-42c092fba887",
        "https://medium.com/greylock-perspectives/risk-58241916e9bc",
        "https://news.greylock.com/the-new-moats-slides-edition-remix-a226dfd6c896",
    ]

    # Try Jerry Chen's Medium profile
    try:
        print("  Fetching Jerry Chen Medium profile...")
        resp = requests.get("https://medium.com/@jerrychen", headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'lxml')
            links = soup.find_all('a', href=True)
            for link in links:
                href = link['href']
                if '/greylock-perspectives/' in href or '/@jerrychen/' in href:
                    full_url = href.split('?')[0]
                    if not full_url.startswith('http'):
                        full_url = 'https://medium.com' + full_url
                    if full_url not in known_medium_urls:
                        known_medium_urls.append(full_url)
    except Exception as e:
        print(f"  Error: {e}")

    # Also try greylock perspectives
    try:
        print("  Fetching Greylock Perspectives...")
        resp = requests.get("https://medium.com/greylock-perspectives", headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'lxml')
            links = soup.find_all('a', href=True)
            for link in links:
                href = link['href']
                if '/greylock-perspectives/' in href and len(href) > 40:
                    full_url = href.split('?')[0]
                    if not full_url.startswith('http'):
                        full_url = 'https://medium.com' + full_url
                    if full_url not in known_medium_urls:
                        known_medium_urls.append(full_url)
    except Exception as e:
        print(f"  Error: {e}")

    print(f"  Found {len(known_medium_urls)} Medium URLs")

    saved = 0
    for url in known_medium_urls:
        try:
            print(f"  Fetching: {url}")
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                print(f"    Status {resp.status_code}")
                continue
            soup = BeautifulSoup(resp.text, 'lxml')

            page_text = resp.text.lower()
            is_jerry = 'jerry chen' in page_text

            title_tag = soup.find('h1')
            title = title_tag.get_text(strip=True) if title_tag else "Unknown"

            date = "2018-01-01"
            # Medium dates
            time_tags = soup.find_all('time')
            for t in time_tags:
                dt = t.get('datetime', '')
                m = re.search(r'(\d{4})-(\d{2})-(\d{2})', dt)
                if m:
                    date = m.group(0)
                    break

            text = extract_text_from_article(soup)

            if is_jerry and text and len(text) > 200:
                if save_post(title, date, url, text, OUTPUT_DIR):
                    saved += 1

            time.sleep(1.5)
        except Exception as e:
            print(f"    Error: {e}")

    return saved

if __name__ == "__main__":
    total = 0
    total += scrape_greylock_blog()
    total += scrape_medium()
    print(f"\n=== TOTAL Jerry Chen posts saved: {total} ===")

    # List saved files
    files = os.listdir(OUTPUT_DIR)
    print(f"Files in output dir: {len(files)}")
    for f in sorted(files):
        print(f"  {f}")
