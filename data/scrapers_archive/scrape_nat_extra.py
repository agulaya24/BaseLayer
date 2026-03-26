"""
Scrape additional Nat Friedman content from GitHub Blog (using raw HTML approach)
and other freely available sources.
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
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def slugify(title):
    s = title.lower().strip()
    s = re.sub(r'[^a-z0-9\s-]', '', s)
    s = re.sub(r'[\s]+', '-', s)
    s = re.sub(r'-+', '-', s)
    return s[:80].strip('-')

def save_post(title, date, url, content):
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


def scrape_github_blog_posts():
    """Scrape GitHub Blog posts by Nat - using alternate selectors."""
    print("\n=== GitHub Blog posts (retry with broader selectors) ===")

    posts = [
        ("https://github.blog/news-insights/company-news/thank-you-github/", "Thank You GitHub - Farewell Letter", "2021-11-03"),
        ("https://github.blog/news-insights/product-news/introducing-github-copilot-ai-pair-programmer/", "Introducing GitHub Copilot Your AI Pair Programmer", "2021-06-29"),
        ("https://github.blog/news-insights/company-news/github-microsoft/", "A Bright Future for GitHub - Microsoft Acquisition", "2018-10-26"),
        ("https://github.blog/news-insights/company-news/npm-is-joining-github/", "npm is joining GitHub", "2020-03-16"),
        ("https://github.blog/news-insights/company-news/github-is-now-free-for-teams/", "GitHub is free for teams", "2020-04-14"),
        ("https://github.blog/news-insights/company-news/no-cookie-for-you/", "No cookie for you", "2020-12-17"),
        ("https://github.blog/news-insights/octoverse/github-octoverse-2020/", "The State of the Octoverse 2020", "2020-12-01"),
        ("https://github.blog/news-insights/company-news/advancing-developer-freedom-github-is-fully-available-in-iran/", "Advancing developer freedom GitHub is fully available in Iran", "2021-01-05"),
        ("https://github.blog/news-insights/company-news/open-source-goes-to-mars/", "Open source goes to Mars", "2021-02-19"),
    ]

    saved = 0
    for url, title, date in posts:
        slug = slugify(title)
        filepath = os.path.join(OUTPUT_DIR, f"{date}_{slug}.txt")
        if os.path.exists(filepath):
            print(f"  SKIP (exists): {title[:60]}")
            saved += 1
            continue

        print(f"  Fetching: {title[:60]}...")
        try:
            r = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
            if r.status_code != 200:
                print(f"    Status: {r.status_code}")
                continue

            soup = BeautifulSoup(r.text, 'lxml')

            # Remove unwanted
            for tag in soup.find_all(['script', 'style', 'nav', 'footer', 'svg', 'button']):
                tag.decompose()

            # Try multiple content selectors
            content_div = None
            for selector in [
                ('div', {'class': 'post__content'}),
                ('div', {'class': 'entry-content'}),
                ('div', {'class': 'post-content'}),
                ('div', {'class': 'content-body'}),
                ('article', {}),
                ('main', {}),
            ]:
                content_div = soup.find(selector[0], selector[1]) if selector[1] else soup.find(selector[0])
                if content_div:
                    break

            if not content_div:
                # Try to get all paragraphs from body
                content_div = soup.find('body')

            if content_div:
                paragraphs = []
                for p in content_div.find_all(['p', 'h2', 'h3', 'li']):
                    text = p.get_text(strip=True)
                    if text and len(text) > 10:
                        if p.name.startswith('h'):
                            paragraphs.append(f"\n## {text}\n")
                        elif p.name == 'li':
                            paragraphs.append(f"- {text}")
                        else:
                            paragraphs.append(text)

                content = '\n\n'.join(paragraphs)
                if save_post(title, date, url, content):
                    saved += 1
            else:
                print(f"    No content found")

            time.sleep(1)
        except Exception as e:
            print(f"    Error: {e}")

    return saved


def scrape_entire_dev():
    """Scrape info about Nat's Entire.dev project."""
    print("\n=== Entire.dev ===")
    try:
        r = requests.get('https://entire.dev', headers=HEADERS, timeout=15)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'lxml')
            for tag in soup.find_all(['script', 'style', 'nav']):
                tag.decompose()
            body = soup.find('main') or soup.find('body')
            if body:
                paragraphs = []
                for p in body.find_all(['p', 'h1', 'h2', 'h3', 'li']):
                    text = p.get_text(strip=True)
                    if text and len(text) > 5:
                        if p.name.startswith('h'):
                            paragraphs.append(f"\n## {text}\n")
                        else:
                            paragraphs.append(text)
                content = '\n\n'.join(paragraphs)
                if content and len(content) > 100:
                    save_post("Entire - AI Development Platform by Nat Friedman", "2025-01-01",
                             "https://entire.dev", content)
                    return 1
        print(f"  Status: {r.status_code if r else 'failed'}")
    except Exception as e:
        print(f"  Error: {e}")
    return 0


def scrape_databricks_talk():
    """Try to get Nat's Databricks Data+AI Summit talk info."""
    print("\n=== Databricks talk page ===")
    try:
        r = requests.get('https://www.databricks.com/dataaisummit/speaker/nat-friedman',
                        headers=HEADERS, timeout=15)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'lxml')
            for tag in soup.find_all(['script', 'style']):
                tag.decompose()
            body = soup.find('main') or soup.find('body')
            if body:
                text = body.get_text(separator='\n', strip=True)
                if len(text) > 200:
                    save_post("Nat Friedman at Databricks Data+AI Summit 2023", "2023-06-01",
                             "https://www.databricks.com/dataaisummit/speaker/nat-friedman", text)
                    return 1
    except Exception as e:
        print(f"  Error: {e}")
    return 0


def scrape_time100():
    """Scrape TIME 100 AI profile."""
    print("\n=== TIME 100 AI profile ===")
    try:
        r = requests.get('https://time.com/collections/time100-ai-2024/7012789/nat-friedman/',
                        headers=HEADERS, timeout=15)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'lxml')
            for tag in soup.find_all(['script', 'style', 'nav']):
                tag.decompose()
            article = soup.find('article') or soup.find('main')
            if article:
                paragraphs = []
                for p in article.find_all(['p', 'h2', 'h3']):
                    text = p.get_text(strip=True)
                    if text and len(text) > 10:
                        paragraphs.append(text)
                content = '\n\n'.join(paragraphs)
                if content and len(content) > 100:
                    save_post("TIME 100 Most Influential People in AI - Nat Friedman Profile", "2024-09-01",
                             "https://time.com/collections/time100-ai-2024/7012789/nat-friedman/", content)
                    return 1
    except Exception as e:
        print(f"  Error: {e}")
    return 0


def scrape_leviathan_encyclopedia():
    """Scrape the leviathan encyclopedia profile."""
    print("\n=== Leviathan Encyclopedia profile ===")
    try:
        r = requests.get('https://www.leviathanencyclopedia.com/article/nat-friedman',
                        headers=HEADERS, timeout=15)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'lxml')
            for tag in soup.find_all(['script', 'style', 'nav']):
                tag.decompose()
            article = soup.find('article') or soup.find('main') or soup.find('body')
            if article:
                paragraphs = []
                for p in article.find_all(['p', 'h2', 'h3', 'li']):
                    text = p.get_text(strip=True)
                    if text and len(text) > 10:
                        paragraphs.append(text)
                content = '\n\n'.join(paragraphs)
                if content and len(content) > 200:
                    save_post("Nat Friedman - Leviathan Encyclopedia Profile", "2024-01-01",
                             "https://www.leviathanencyclopedia.com/article/nat-friedman", content)
                    return 1
    except Exception as e:
        print(f"  Error: {e}")
    return 0


def scrape_scrollprize_updates():
    """Scrape Vesuvius Challenge updates and announcements."""
    print("\n=== Vesuvius Challenge / Scroll Prize updates ===")
    saved = 0

    urls = [
        ("https://scrollprize.org/grandprize", "Vesuvius Challenge Grand Prize Announcement", "2024-02-05"),
        ("https://scrollprize.org/firstletters", "First Letters Read Inside Herculaneum Scroll", "2023-10-12"),
        ("https://scrollprize.org", "Vesuvius Challenge - Overview", "2023-03-15"),
        ("https://scrollprize.org/2024_prizes", "Vesuvius Challenge 2024 Prizes", "2024-03-01"),
    ]

    for url, title, date in urls:
        slug = slugify(title)
        filepath = os.path.join(OUTPUT_DIR, f"{date}_{slug}.txt")
        if os.path.exists(filepath):
            print(f"  SKIP: {title[:60]}")
            saved += 1
            continue

        print(f"  Fetching: {title[:60]}...")
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, 'lxml')
                for tag in soup.find_all(['script', 'style', 'nav', 'footer']):
                    tag.decompose()
                main = soup.find('main') or soup.find('article') or soup.find('body')
                if main:
                    paragraphs = []
                    for p in main.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'li']):
                        text = p.get_text(strip=True)
                        if text and len(text) > 5:
                            if p.name.startswith('h'):
                                paragraphs.append(f"\n## {text}\n")
                            elif p.name == 'li':
                                paragraphs.append(f"- {text}")
                            else:
                                paragraphs.append(text)
                    content = '\n\n'.join(paragraphs)
                    if save_post(title, date, url, content):
                        saved += 1
            time.sleep(1)
        except Exception as e:
            print(f"    Error: {e}")

    return saved


def scrape_wikipedia():
    """Scrape Nat Friedman Wikipedia for biographical context."""
    print("\n=== Wikipedia ===")
    try:
        r = requests.get('https://en.wikipedia.org/wiki/Nat_Friedman', headers=HEADERS, timeout=15)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'lxml')
            content_div = soup.find('div', {'id': 'mw-content-text'})
            if content_div:
                # Remove reference numbers, edit links, etc
                for tag in content_div.find_all(['sup', 'style', 'script', 'table']):
                    tag.decompose()
                paragraphs = []
                for p in content_div.find_all(['p', 'h2', 'h3']):
                    text = p.get_text(strip=True)
                    if text and len(text) > 10:
                        if p.name.startswith('h'):
                            # Remove [edit] text
                            text = re.sub(r'\[edit\]', '', text).strip()
                            paragraphs.append(f"\n## {text}\n")
                        else:
                            paragraphs.append(text)
                content = '\n\n'.join(paragraphs)
                if save_post("Nat Friedman - Wikipedia Biography", "2024-01-01",
                            "https://en.wikipedia.org/wiki/Nat_Friedman", content):
                    return 1
    except Exception as e:
        print(f"  Error: {e}")
    return 0


def scrape_frederick_ai():
    """Scrape Frederick AI founder story."""
    print("\n=== Frederick AI founder story ===")
    try:
        r = requests.get('https://www.frederick.ai/blog/github-founder-nat-friedman',
                        headers=HEADERS, timeout=15)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'lxml')
            for tag in soup.find_all(['script', 'style', 'nav']):
                tag.decompose()
            article = soup.find('article') or soup.find('main') or soup.find('body')
            if article:
                paragraphs = []
                for p in article.find_all(['p', 'h2', 'h3', 'li']):
                    text = p.get_text(strip=True)
                    if text and len(text) > 10:
                        if p.name.startswith('h'):
                            paragraphs.append(f"\n## {text}\n")
                        else:
                            paragraphs.append(text)
                content = '\n\n'.join(paragraphs)
                if content and len(content) > 200:
                    save_post("Founder Story Nat Friedman of GitHub", "2024-01-01",
                             "https://www.frederick.ai/blog/github-founder-nat-friedman", content)
                    return 1
    except Exception as e:
        print(f"  Error: {e}")
    return 0


def main():
    total = 0
    total += scrape_github_blog_posts()
    total += scrape_scrollprize_updates()
    total += scrape_entire_dev()
    total += scrape_time100()
    total += scrape_leviathan_encyclopedia()
    total += scrape_wikipedia()
    total += scrape_frederick_ai()
    total += scrape_databricks_talk()

    print(f"\n{'='*60}")
    print(f"NEW FILES SAVED: {total}")

    # List all files
    files = sorted(os.listdir(OUTPUT_DIR))
    print(f"\nAll files in output directory ({len(files)}):")
    for f in files:
        filepath = os.path.join(OUTPUT_DIR, f)
        size = os.path.getsize(filepath)
        print(f"  {f} ({size:,} bytes)")

if __name__ == '__main__':
    main()
