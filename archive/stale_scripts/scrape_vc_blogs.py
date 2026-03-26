"""Scrape Jerry Chen (Greylock) and Martin Casado (a16z) blog posts."""
import requests
from bs4 import BeautifulSoup
import re
import os
import time
import json
import ssl
from urllib.parse import urljoin

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

def slugify(title):
    s = title.lower().strip()
    s = re.sub(r'[^\w\s-]', '', s)
    s = re.sub(r'[\s_]+', '-', s)
    s = re.sub(r'-+', '-', s)
    return s[:80].strip('-')

def fetch_url(url, verify_ssl=True):
    """Fetch URL with retries."""
    for attempt in range(3):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20, verify=verify_ssl)
            return resp
        except requests.exceptions.SSLError:
            if verify_ssl:
                return fetch_url(url, verify_ssl=False)
            return None
        except Exception as e:
            if attempt == 2:
                print(f"    Failed after 3 attempts: {e}")
            time.sleep(2)
    return None

def extract_article_text(soup):
    """Extract clean article text."""
    # Remove unwanted elements
    for tag in soup.find_all(['script', 'style', 'nav', 'footer', 'aside', 'iframe',
                              'button', 'form', 'svg', 'noscript']):
        tag.decompose()

    # Remove share/social buttons
    for cls in ['share', 'social', 'sidebar', 'newsletter', 'subscribe', 'related',
                'comments', 'author-bio', 'nav', 'menu', 'footer', 'header-nav']:
        for el in soup.find_all(class_=re.compile(cls, re.I)):
            el.decompose()

    # Try specific content selectors
    selectors = [
        'article .post-content',
        'article .entry-content',
        '.article-content',
        '.post-body',
        '.blog-post-content',
        'article',
        '.content-body',
        '[class*="article"]',
        '[class*="post-content"]',
        'main .content',
        'main',
    ]

    for sel in selectors:
        content = soup.select_one(sel)
        if content:
            paragraphs = content.find_all(['p', 'h2', 'h3', 'h4', 'blockquote', 'li'])
            if paragraphs:
                parts = []
                for p in paragraphs:
                    text = p.get_text(strip=True)
                    if len(text) > 15:
                        if p.name in ['h2', 'h3', 'h4']:
                            parts.append(f"\n## {text}\n")
                        elif p.name == 'blockquote':
                            parts.append(f'> {text}')
                        elif p.name == 'li':
                            parts.append(f"- {text}")
                        else:
                            parts.append(text)
                result = '\n\n'.join(parts)
                if len(result) > 300:
                    return result

    # Fallback: all paragraphs
    paragraphs = soup.find_all('p')
    text = '\n\n'.join(p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 30)
    return text

def extract_date(soup, url, page_text):
    """Try to extract date from page."""
    # Try time/datetime elements
    for time_tag in soup.find_all('time'):
        dt = time_tag.get('datetime', time_tag.get_text(strip=True))
        m = re.search(r'(\d{4})-(\d{2})-(\d{2})', str(dt))
        if m:
            return m.group(0)

    # Try meta tags
    for meta in soup.find_all('meta'):
        content = meta.get('content', '')
        name = meta.get('property', meta.get('name', ''))
        if 'date' in name.lower() or 'published' in name.lower():
            m = re.search(r'(\d{4})-(\d{2})-(\d{2})', content)
            if m:
                return m.group(0)

    # Try MM.DD.YYYY pattern (Greylock)
    m = re.search(r'(\d{2})\.(\d{2})\.(\d{4})', page_text)
    if m:
        return f"{m.group(3)}-{m.group(1)}-{m.group(2)}"

    # Try Month DD, YYYY
    months = {'january':'01','february':'02','march':'03','april':'04','may':'05','june':'06',
              'july':'07','august':'08','september':'09','october':'10','november':'11','december':'12',
              'jan':'01','feb':'02','mar':'03','apr':'04','may':'05','jun':'06',
              'jul':'07','aug':'08','sep':'09','oct':'10','nov':'11','dec':'12'}
    m = re.search(r'((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*)\s+(\d{1,2}),?\s+(\d{4})', page_text, re.I)
    if m:
        month_str = m.group(1).lower()[:3]
        if month_str in months:
            return f"{m.group(3)}-{months[month_str]}-{int(m.group(2)):02d}"

    return None

def save_post(title, date, url, text, output_dir):
    """Save a post to a text file."""
    if not text or len(text) < 200:
        print(f"  SKIP (too short, {len(text) if text else 0} chars): {title}")
        return False

    slug = slugify(title)
    if not date:
        date = "0000-00-00"
    filename = f"{date}_{slug}.txt"
    filepath = os.path.join(output_dir, filename)

    # Avoid duplicates
    if os.path.exists(filepath):
        print(f"  SKIP (duplicate): {filename}")
        return False

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(f"Title: {title}\n")
        f.write(f"Date: {date}\n")
        f.write(f"Source: {url}\n")
        f.write(f"\n{'='*80}\n\n")
        f.write(text)

    print(f"  SAVED: {filename} ({len(text):,} chars)")
    return True


# ============================================================================
# JERRY CHEN - GREYLOCK
# ============================================================================

JERRY_OUTPUT = r"C:\Users\Aarik\Anthropic\memory_system\data\jerry_chen_source"

# All known Jerry Chen URLs from searches
JERRY_URLS = [
    # Greylock greymatter (newer site)
    "https://greylock.com/greymatter/the-new-new-moats/",
    "https://greylock.com/greymatter/the-new-moats/",
    "https://greylock.com/greymatter/castles-in-the-cloud/",
    "https://greylock.com/greymatter/chronosphere/",
    "https://greylock.com/greymatter/the-big-4-era/",
    "https://greylock.com/greymatter/jerry-chen-the-evolution-of-cloud/",
    "https://greylock.com/greymatter/three-trends-in-vc-backed-cloud/",
    "https://greylock.com/greymatter/how-to-break-up-big-clouds-dominance/",
    "https://greylock.com/greymatter/powering-the-multi-cloudparadigm/",
    "https://greylock.com/greymatter/rockset-the-data-driven-future/",
    "https://greylock.com/greymatter/seth-rosenberg-product-led-ai/",
    "https://greylock.com/greymatter/securing-ai/",
    # Greylock archive
    "https://greylock.com/jerry-chen-riding-the-waves-of-change/",
    # news.greylock.com (Medium-hosted Greylock Perspectives)
    "https://news.greylock.com/the-new-moats-53f61aeac2d9",
    "https://news.greylock.com/unit-of-value-a-framework-for-scaling-42c092fba887",
    "https://news.greylock.com/the-on-demand-enterprise-2461bed87cd9",
    "https://news.greylock.com/our-investment-in-rockset-d46231f6a748",
    "https://news.greylock.com/risk-58241916e9bc",
    "https://news.greylock.com/our-investment-in-instabase-8c4f02d6ce90",
    "https://news.greylock.com/why-were-betting-on-notable-health-acf996ccb6f",
    "https://news.greylock.com/the-new-moats-slides-edition-remix-a226dfd6c896",
    "https://news.greylock.com/our-investment-in-cato-networks-73cdcfa67c6f",
    "https://news.greylock.com/https-news-greylock-com-chronosphere-f7221aac8c80",
    "https://news.greylock.com/the-on-demand-enterprise-4bedbe894d03",
]

def discover_jerry_chen_greylock():
    """Try to discover more Jerry Chen posts from Greylock blog."""
    extra_urls = []
    print("  Discovering more Jerry Chen posts from Greylock blog...")

    # Paginate through greylock.com/blog/
    for page in range(1, 15):
        url = f"https://greylock.com/blog/page/{page}/" if page > 1 else "https://greylock.com/blog/"
        resp = fetch_url(url)
        if not resp or resp.status_code != 200:
            break
        soup = BeautifulSoup(resp.text, 'lxml')
        # Find all greymatter links
        for a in soup.find_all('a', href=True):
            href = a['href']
            if '/greymatter/' in href:
                full_url = urljoin("https://greylock.com", href)
                if full_url not in JERRY_URLS and full_url not in extra_urls:
                    extra_urls.append(full_url)
        time.sleep(1)

    # Also check greymatter category pages
    for page in range(1, 10):
        url = f"https://greylock.com/blog/greymatter/page/{page}/" if page > 1 else "https://greylock.com/blog/greymatter/"
        resp = fetch_url(url)
        if not resp or resp.status_code != 200:
            break
        soup = BeautifulSoup(resp.text, 'lxml')
        for a in soup.find_all('a', href=True):
            href = a['href']
            if '/greymatter/' in href and href != '/blog/greymatter/':
                full_url = urljoin("https://greylock.com", href)
                if full_url not in JERRY_URLS and full_url not in extra_urls and 'page/' not in full_url:
                    extra_urls.append(full_url)
        time.sleep(1)

    print(f"  Discovered {len(extra_urls)} additional Greylock URLs")
    return extra_urls

def scrape_jerry_chen():
    """Scrape all Jerry Chen posts."""
    print("\n" + "="*60)
    print("SCRAPING JERRY CHEN (Greylock)")
    print("="*60)

    os.makedirs(JERRY_OUTPUT, exist_ok=True)

    # Clear old files
    for f in os.listdir(JERRY_OUTPUT):
        os.remove(os.path.join(JERRY_OUTPUT, f))

    # Discover more URLs
    extra_urls = discover_jerry_chen_greylock()
    all_urls = JERRY_URLS + extra_urls

    saved = 0
    for url in all_urls:
        print(f"\n  Fetching: {url}")
        resp = fetch_url(url)
        if not resp or resp.status_code != 200:
            print(f"    Status: {resp.status_code if resp else 'Failed'}")
            continue

        soup = BeautifulSoup(resp.text, 'lxml')
        page_text = resp.text.lower()

        # Check if Jerry Chen is mentioned (author)
        is_jerry = ('jerry chen' in page_text or 'jerry-chen' in url.lower()
                     or '@jerrychen' in page_text)

        # For greymatter posts, many are by Jerry even without explicit attribution
        is_greymatter = '/greymatter/' in url

        title_tag = soup.find('h1')
        title = title_tag.get_text(strip=True) if title_tag else url.rstrip('/').split('/')[-1].replace('-', ' ').title()

        # Skip generic/non-article pages
        if title.lower() in ['greymatter', 'blog', 'greylock']:
            print(f"    Skip (index page): {title}")
            continue

        date = extract_date(soup, url, page_text)
        text = extract_article_text(soup)

        if (is_jerry or is_greymatter) and text and len(text) > 200:
            if save_post(title, date, url, text, JERRY_OUTPUT):
                saved += 1
        elif not is_jerry and not is_greymatter:
            print(f"    Not by Jerry Chen")
        else:
            print(f"    Text too short or missing")

        time.sleep(1.5)

    print(f"\n  Jerry Chen total saved: {saved}")
    return saved


# ============================================================================
# MARTIN CASADO - A16Z
# ============================================================================

CASADO_OUTPUT = r"C:\Users\Aarik\Anthropic\memory_system\data\martin_casado_source"

def discover_casado_a16z():
    """Discover Martin Casado posts from a16z author page and category pages."""
    urls = []
    print("  Discovering Martin Casado posts from a16z...")

    # Try author page (may have pagination)
    for page in range(1, 20):
        url = f"https://a16z.com/author/martin-casado/page/{page}/" if page > 1 else "https://a16z.com/author/martin-casado/"
        print(f"    Checking: {url}")
        resp = fetch_url(url)
        if not resp or resp.status_code != 200:
            print(f"    Status: {resp.status_code if resp else 'Failed'}, stopping")
            break

        soup = BeautifulSoup(resp.text, 'lxml')
        found_on_page = 0
        for a in soup.find_all('a', href=True):
            href = a['href']
            # a16z blog post URLs are like a16z.com/YYYY/MM/DD/title or a16z.com/title
            if href.startswith('https://a16z.com/') and href not in urls:
                # Filter out category/author/tag pages
                path = href.replace('https://a16z.com/', '').rstrip('/')
                if (path and
                    not path.startswith('author/') and
                    not path.startswith('category/') and
                    not path.startswith('tag/') and
                    not path.startswith('podcast/') and
                    not path.startswith('page/') and
                    '/' not in path and  # a16z uses flat URLs like a16z.com/slug
                    len(path) > 5):
                    if href not in urls:
                        urls.append(href)
                        found_on_page += 1
                # Also check YYYY/MM/DD format
                elif re.match(r'\d{4}/\d{2}/\d{2}/', path):
                    if href not in urls:
                        urls.append(href)
                        found_on_page += 1

        print(f"    Found {found_on_page} article URLs on page {page}")
        if found_on_page == 0:
            break
        time.sleep(1.5)

    print(f"  Total discovered: {len(urls)} a16z URLs")
    return urls

def scrape_casado():
    """Scrape all Martin Casado posts."""
    print("\n" + "="*60)
    print("SCRAPING MARTIN CASADO (a16z)")
    print("="*60)

    os.makedirs(CASADO_OUTPUT, exist_ok=True)

    # Clear old files
    for f in os.listdir(CASADO_OUTPUT):
        os.remove(os.path.join(CASADO_OUTPUT, f))

    urls = discover_casado_a16z()

    # Add known URLs that might not appear on the author page
    known = [
        "https://a16z.com/the-cost-of-cloud-a-trillion-dollar-paradox/",
        "https://a16z.com/who-owns-the-generative-ai-platform/",
        "https://a16z.com/the-new-business-of-ai-and-how-its-different-from-traditional-software/",
        "https://a16z.com/navigating-the-high-cost-of-ai-compute/",
        "https://a16z.com/ai-canon/",
        "https://a16z.com/supporting-the-open-source-ai-community/",
        "https://a16z.com/where-we-go-from-here/",
        "https://a16z.com/advancing-open-source-ai-through-benchmarks-and-bold-experimentation/",
        "https://a16z.com/open-source-software-is-eating-the-world/",
        "https://a16z.com/the-rising-tide-of-open-source/",
    ]
    for u in known:
        if u not in urls:
            urls.append(u)

    saved = 0
    for url in urls:
        print(f"\n  Fetching: {url}")
        resp = fetch_url(url)
        if not resp or resp.status_code != 200:
            print(f"    Status: {resp.status_code if resp else 'Failed'}")
            continue

        soup = BeautifulSoup(resp.text, 'lxml')
        page_text = resp.text.lower()

        # Check if Martin Casado is the author
        is_casado = ('martin casado' in page_text or 'martin-casado' in page_text)

        title_tag = soup.find('h1')
        title = title_tag.get_text(strip=True) if title_tag else url.rstrip('/').split('/')[-1].replace('-', ' ').title()

        if not title or title.lower() in ['andreessen horowitz', 'a16z']:
            print(f"    Skip (non-article): {title}")
            continue

        date = extract_date(soup, url, page_text)
        text = extract_article_text(soup)

        if is_casado and text and len(text) > 200:
            if save_post(title, date, url, text, CASADO_OUTPUT):
                saved += 1
        elif not is_casado:
            print(f"    Not by Martin Casado, skipping")
        else:
            print(f"    Text too short or missing ({len(text) if text else 0} chars)")

        time.sleep(1.5)

    print(f"\n  Martin Casado total saved: {saved}")
    return saved


if __name__ == "__main__":
    j = scrape_jerry_chen()
    c = scrape_casado()

    print("\n" + "="*60)
    print(f"FINAL RESULTS")
    print(f"="*60)
    print(f"Jerry Chen: {j} posts")
    print(f"Martin Casado: {c} posts")

    for name, d in [("Jerry Chen", JERRY_OUTPUT), ("Martin Casado", CASADO_OUTPUT)]:
        files = sorted(os.listdir(d))
        print(f"\n{name} files ({len(files)}):")
        for f in files:
            size = os.path.getsize(os.path.join(d, f))
            print(f"  {f} ({size:,} bytes)")
