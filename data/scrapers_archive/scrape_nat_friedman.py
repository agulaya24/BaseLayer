"""
Scrape Nat Friedman's writing from multiple sources.
Nat doesn't have a single blog - his writing is spread across:
1. nat.org (manifesto/beliefs page)
2. GitHub Blog posts (as CEO)
3. Dwarkesh Podcast transcript
4. Various interview transcripts and appearances
5. Scroll Prize / Vesuvius Challenge posts
"""
import requests
from bs4 import BeautifulSoup
import re
import os
import time
import sys
import json

sys.stdout.reconfigure(encoding='utf-8')

OUTPUT_DIR = r"C:\Users\Aarik\Anthropic\memory_system\data\nat_friedman_source"
os.makedirs(OUTPUT_DIR, exist_ok=True)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

def slugify(title):
    s = title.lower().strip()
    s = re.sub(r'[^a-z0-9\s-]', '', s)
    s = re.sub(r'[\s]+', '-', s)
    s = re.sub(r'-+', '-', s)
    return s[:80].strip('-')

def save_post(title, date, url, content, prefix=""):
    if len(content.strip()) < 100:
        print(f"  TOO SHORT ({len(content)} chars): {title[:60]}")
        return False
    slug = slugify(title)
    filename = f"{date}_{slug}.txt"
    filepath = os.path.join(OUTPUT_DIR, filename)
    if os.path.exists(filepath):
        print(f"  SKIP (exists): {filename}")
        return True
    header = f"Title: {title}\nDate: {date}\nSource: {url}\n\n---\n\n"
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(header + content)
    print(f"  Saved: {filename} ({len(content)} chars)")
    return True

def extract_article_text(soup):
    """Extract clean text from an article page."""
    # Remove unwanted elements
    for tag in soup.find_all(['script', 'style', 'nav', 'footer', 'header', 'button', 'svg', 'form']):
        tag.decompose()

    # Try various content selectors
    body = (soup.find('div', class_='post-content') or
            soup.find('div', class_='entry-content') or
            soup.find('article') or
            soup.find('div', class_='body') or
            soup.find('div', class_='available-content') or
            soup.find('main'))

    if not body:
        body = soup.find('body')

    if not body:
        return ""

    paragraphs = []
    for elem in body.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'li', 'blockquote']):
        text = elem.get_text(strip=True)
        if text and len(text) > 1:
            tag = elem.name
            if tag.startswith('h'):
                paragraphs.append(f"\n## {text}\n")
            elif tag == 'li':
                paragraphs.append(f"- {text}")
            elif tag == 'blockquote':
                paragraphs.append(f"> {text}")
            else:
                paragraphs.append(text)

    return '\n\n'.join(paragraphs)


def scrape_nat_org():
    """Scrape the nat.org manifesto page."""
    print("\n=== Scraping nat.org ===")
    r = requests.get('https://nat.org', headers=HEADERS, timeout=15)
    if r.status_code != 200:
        print(f"  Failed: {r.status_code}")
        return 0

    soup = BeautifulSoup(r.text, 'lxml')
    # Get the full page text - it's a simple HTML page
    body = soup.find('body')
    if not body:
        return 0

    # Extract structured content
    content_parts = []
    for elem in body.find_all(['h2', 'p', 'li', 'ul']):
        if elem.name == 'li':
            text = elem.get_text(strip=True)
            if text:
                # Check if it has nested ul (sub-items)
                if elem.find('ul'):
                    # Get just the direct text
                    direct_text = ''
                    for child in elem.children:
                        if hasattr(child, 'name') and child.name == 'ul':
                            continue
                        if hasattr(child, 'get_text'):
                            direct_text += child.get_text(strip=True)
                        else:
                            direct_text += str(child).strip()
                    if direct_text:
                        content_parts.append(f"- {direct_text}")
                else:
                    content_parts.append(f"  - {text}")
        elif elem.name == 'h2':
            content_parts.append(f"\n## {elem.get_text(strip=True)}\n")
        elif elem.name == 'p':
            text = elem.get_text(strip=True)
            if text:
                content_parts.append(text)

    content = '\n'.join(content_parts)
    save_post("Nat Friedman - Personal Beliefs and Principles", "2023-01-01", "https://nat.org", content)
    return 1


def scrape_github_blog():
    """Scrape Nat's posts from GitHub Blog."""
    print("\n=== Scraping GitHub Blog posts ===")

    # Known Nat Friedman GitHub Blog URLs
    urls = [
        ("https://github.blog/news-insights/company-news/thank-you-github/", "Thank You GitHub", "2021-11-03"),
        ("https://github.blog/news-insights/product-news/introducing-github-copilot-ai-pair-programmer/", "Introducing GitHub Copilot: Your AI Pair Programmer", "2021-06-29"),
        ("https://github.blog/news-insights/company-news/goodbye-github/", "Auf Wiedersehen GitHub", "2021-11-03"),
        ("https://github.blog/news-insights/company-news/github-microsoft/", "A Bright Future for GitHub", "2018-10-26"),
        ("https://github.blog/news-insights/company-news/supporting-the-community-we-all-share/", "Supporting the Community We All Share", "2019-10-09"),
    ]

    # Also try to discover more from the author page
    try:
        r = requests.get('https://github.blog/author/nat/', headers=HEADERS, timeout=15)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'lxml')
            for a in soup.find_all('a', href=True):
                href = a['href']
                if 'github.blog/' in href and any(x in href for x in ['news-insights/', '/2019/', '/2020/', '/2021/']):
                    title = a.get_text(strip=True)
                    slug = href.rstrip('/').split('/')[-1]
                    if title and len(title) > 15 and slug not in ['news-insights', 'company-news', 'product-news', 'the-library']:
                        known_urls = [u[0] for u in urls]
                        if not any(slug in ku for ku in known_urls):
                            urls.append((href, title, "2020-01-01"))
    except Exception as e:
        print(f"  Error fetching author page: {e}")

    saved = 0
    for url, title, date in urls:
        print(f"  Fetching: {title[:60]}...")
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code != 200:
                # Try alternate URL format
                alt_url = url.replace('news-insights/company-news/', '').replace('news-insights/product-news/', '')
                r = requests.get(alt_url, headers=HEADERS, timeout=15)
                if r.status_code != 200:
                    print(f"    Failed: {r.status_code}")
                    continue

            soup = BeautifulSoup(r.text, 'lxml')
            content = extract_article_text(soup)
            if save_post(title, date, url, content):
                saved += 1
            time.sleep(1)
        except Exception as e:
            print(f"    Error: {e}")

    return saved


def scrape_dwarkesh_transcript():
    """Try to get Nat Friedman's Dwarkesh podcast transcript."""
    print("\n=== Scraping Dwarkesh Podcast transcript ===")

    # Try to find the episode
    try:
        r = requests.get('https://www.dwarkeshpatel.com/p/nat-friedman', headers=HEADERS, timeout=15)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'lxml')
            content = extract_article_text(soup)
            if content:
                save_post("Nat Friedman - Reading Ancient Scrolls, Open Source, and AI (Dwarkesh Podcast)",
                         "2023-03-22", "https://www.dwarkeshpatel.com/p/nat-friedman", content)
                return 1
            else:
                print("  No content extracted")
        else:
            print(f"  Status: {r.status_code}")
    except Exception as e:
        print(f"  Error: {e}")
    return 0


def scrape_scrollprize():
    """Scrape Vesuvius Challenge / Scroll Prize blog posts."""
    print("\n=== Scraping Scroll Prize posts ===")

    try:
        r = requests.get('https://scrollprize.org/blog', headers=HEADERS, timeout=15)
        if r.status_code != 200:
            r = requests.get('https://scrollprize.org', headers=HEADERS, timeout=15)

        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'lxml')
            # Find blog post links
            links = []
            for a in soup.find_all('a', href=True):
                href = a['href']
                title = a.get_text(strip=True)
                if '/blog' in href and title and len(title) > 10:
                    if not href.startswith('http'):
                        href = 'https://scrollprize.org' + href
                    links.append((href, title))

            print(f"  Found {len(links)} potential posts")
            saved = 0
            seen = set()
            for url, title in links[:15]:
                if url in seen:
                    continue
                seen.add(url)
                try:
                    r2 = requests.get(url, headers=HEADERS, timeout=15)
                    if r2.status_code == 200:
                        soup2 = BeautifulSoup(r2.text, 'lxml')
                        content = extract_article_text(soup2)
                        if content and len(content) > 200:
                            save_post(f"Vesuvius Challenge - {title}", "2023-06-01", url, content)
                            saved += 1
                    time.sleep(1)
                except Exception as e:
                    print(f"    Error: {e}")
            return saved
        else:
            print(f"  Status: {r.status_code}")
    except Exception as e:
        print(f"  Error: {e}")
    return 0


def scrape_plasticlist():
    """Scrape plasticlist.org - Nat's food testing project."""
    print("\n=== Scraping Plastic List ===")
    try:
        r = requests.get('https://plasticlist.org', headers=HEADERS, timeout=15)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'lxml')
            content = extract_article_text(soup)
            if content:
                save_post("The Plastic List - Testing Bay Area Foods for Plastic Chemicals",
                         "2024-01-01", "https://plasticlist.org", content)
                return 1
    except Exception as e:
        print(f"  Error: {e}")
    return 0


def scrape_nat_github_hello():
    """Scrape Nat's GitHub hello page."""
    print("\n=== Scraping nat.github.io/hello ===")
    try:
        r = requests.get('https://nat.github.io/hello/', headers=HEADERS, timeout=15)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'lxml')
            content = extract_article_text(soup)
            if content:
                save_post("Hello GitHub - Nat Friedman Introduction as CEO",
                         "2018-10-29", "https://nat.github.io/hello/", content)
                return 1
    except Exception as e:
        print(f"  Error: {e}")
    return 0


def scrape_colemanm_summary():
    """Scrape Coleman McCormick's summary of Nat's AI views."""
    print("\n=== Scraping Coleman McCormick summary ===")
    try:
        r = requests.get('https://www.colemanm.org/post/daniel-gross-and-nat-friedman-on-ai/', headers=HEADERS, timeout=15)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'lxml')
            content = extract_article_text(soup)
            if content:
                save_post("Daniel Gross and Nat Friedman on AI - Summary and Notes",
                         "2023-08-01", "https://www.colemanm.org/post/daniel-gross-and-nat-friedman-on-ai/", content)
                return 1
    except Exception as e:
        print(f"  Error: {e}")
    return 0


def scrape_interviews_and_appearances():
    """Scrape freely available interview content."""
    print("\n=== Scraping interviews and appearances ===")

    sources = [
        # Lex Fridman podcast notes
        ("https://lexfridman.com/nat-friedman/", "Nat Friedman on Lex Fridman Podcast", "2023-01-01"),
        # Cost of Glory interview
        ("https://costofglory.substack.com/p/mysteries-of-the-scrolls", "Mysteries of the Scrolls - Interview", "2024-05-30"),
        # LessWrong Vesuvius post
        ("https://www.lesswrong.com/posts/boWGNiQ3oemiKgDw7/metascience-of-the-vesuvius-challenge", "Metascience of the Vesuvius Challenge", "2024-01-01"),
    ]

    saved = 0
    for url, title, date in sources:
        print(f"  Trying: {title[:60]}...")
        try:
            r = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, 'lxml')
                content = extract_article_text(soup)
                if content and len(content) > 200:
                    if save_post(title, date, url, content):
                        saved += 1
            else:
                print(f"    Status: {r.status_code}")
            time.sleep(1)
        except Exception as e:
            print(f"    Error: {e}")

    return saved


def scrape_medium_archive():
    """Try to get Nat's Medium posts."""
    print("\n=== Scraping Medium archive ===")
    try:
        # Medium API for user posts
        r = requests.get('https://medium.com/nat-friedman/archive', headers=HEADERS, timeout=15)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'lxml')
            links = []
            for a in soup.find_all('a', href=True):
                href = a['href']
                title = a.get_text(strip=True)
                if '/nat-friedman/' in href and title and len(title) > 10 and 'archive' not in href:
                    if href not in [l[0] for l in links]:
                        links.append((href, title))

            print(f"  Found {len(links)} potential posts")
            saved = 0
            for url, title in links[:20]:
                if not url.startswith('http'):
                    url = 'https://medium.com' + url
                try:
                    r2 = requests.get(url, headers=HEADERS, timeout=15)
                    if r2.status_code == 200:
                        soup2 = BeautifulSoup(r2.text, 'lxml')
                        content = extract_article_text(soup2)
                        if content and len(content) > 200:
                            if save_post(title[:100], "2019-01-01", url, content):
                                saved += 1
                    time.sleep(1)
                except Exception as e:
                    print(f"    Error: {e}")
            return saved
        else:
            print(f"  Status: {r.status_code}")
    except Exception as e:
        print(f"  Error: {e}")
    return 0


def main():
    total = 0
    total += scrape_nat_org()
    total += scrape_nat_github_hello()
    total += scrape_github_blog()
    total += scrape_dwarkesh_transcript()
    total += scrape_scrollprize()
    total += scrape_plasticlist()
    total += scrape_colemanm_summary()
    total += scrape_interviews_and_appearances()
    total += scrape_medium_archive()

    print(f"\n{'='*60}")
    print(f"TOTAL SAVED: {total} files")
    print(f"Output dir: {OUTPUT_DIR}")

    # List saved files
    files = os.listdir(OUTPUT_DIR)
    print(f"\nFiles in output directory ({len(files)}):")
    for f in sorted(files):
        filepath = os.path.join(OUTPUT_DIR, f)
        size = os.path.getsize(filepath)
        print(f"  {f} ({size:,} bytes)")


if __name__ == '__main__':
    main()
