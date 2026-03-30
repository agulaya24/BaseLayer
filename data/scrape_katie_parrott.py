"""
Scraper for Katie Parrott articles from:
1. every.to/working-overtime (her column at Every)
2. katieparrott.substack.com (The Curiosity Gap, her personal Substack)

Saves each article as a separate .txt file in katie_parrott_source/
"""

import os
import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "katie_parrott_source")
os.makedirs(OUTPUT_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# All known Katie Parrott article URLs
EVERY_TO_URLS = [
    "https://every.to/working-overtime/i-hired-chatgpt-as-my-career-coach",
    "https://every.to/working-overtime/the-once-and-future-history-of-knowledge-work",
    "https://every.to/working-overtime/ai-phobia-is-really-just-fear-that-easier-equals-cheating",
    "https://every.to/working-overtime/i-asked-claude-the-question-i-could-never-ask-my-boss",
    "https://every.to/working-overtime/every-ceo-is-writing-the-same-ai-memo-here-s-what-they-re-really-saying",
    "https://every.to/working-overtime/how-to-keep-your-writing-weird-in-the-age-of-ai",
    "https://every.to/working-overtime/the-18-month-career-is-here",
    "https://every.to/working-overtime/i-taught-claude-every-s-standards-it-taught-me-mine",
    "https://every.to/working-overtime/i-didn-t-know-typing-held-me-back-until-i-started-thinking-out-loud",
    "https://every.to/working-overtime/i-fed-my-essays-to-chatgpt-until-it-learned-my-voice",
    "https://every.to/working-overtime/ai-was-supposed-to-free-my-time-it-consumed-it",
    "https://every.to/working-overtime/when-o3-plans-your-career-better-than-you-do",
    "https://every.to/working-overtime/how-i-successfully-failed-at-my-first-ai-operations-project",
    "https://every.to/working-overtime/ai-doesn-t-care-about-your-resume",
    "https://every.to/working-overtime/i-tried-ai-coding-tools-now-i-want-to-learn-to-code",
    "https://every.to/working-overtime/it-s-me-hi-i-m-the-vibe-coder",
    "https://every.to/working-overtime/ai-isn-t-making-me-more-productive-it-s-making-it-possible-to-work-at-all",
    "https://every.to/working-overtime/ai-turned-me-into-a-content-agency-of-one-561948be-5370-4306-a433-b352a572705e",
    "https://every.to/working-overtime/how-i-run-three-ai-models-in-parallel-without-losing-my-mind",
    "https://every.to/working-overtime/what-happens-when-ai-joins-the-org-chart",
]

SUBSTACK_URLS = [
    "https://katieparrott.substack.com/p/duking-it-out-with-chatgpt",
    "https://katieparrott.substack.com/p/these-are-my-confessions",
    "https://katieparrott.substack.com/p/earning-credits-from-the-school-of",
    "https://katieparrott.substack.com/p/the-dystopia-that-programmed-me",
    "https://katieparrott.substack.com/p/the-medium-is-the-video-essay",
    "https://katieparrott.substack.com/p/my-diagnosis",
    "https://katieparrott.substack.com/p/professional-chaos-theory",
    "https://katieparrott.substack.com/p/friday-night-bible-study-with-chatgpt",
    "https://katieparrott.substack.com/p/finishing-the-app",
    "https://katieparrott.substack.com/p/the-software-that-raised-me",
]


def slug_from_url(url):
    """Extract a filename-safe slug from a URL."""
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    slug = path.split("/")[-1]
    # Remove UUID suffixes
    slug = re.sub(r'-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', '', slug)
    slug = re.sub(r'[^a-zA-Z0-9-]', '-', slug)
    slug = re.sub(r'-+', '-', slug).strip('-')
    return slug[:80]


def extract_every_to_article(html):
    """Extract article text from every.to HTML."""
    soup = BeautifulSoup(html, 'html.parser')

    title = ""
    title_tag = soup.find('h1')
    if title_tag:
        title = title_tag.get_text(strip=True)

    article = soup.find('article')
    if not article:
        article = soup.find('div', class_=re.compile(r'post|article|content|body', re.I))
    if not article:
        article = soup.find('main')

    if not article:
        paragraphs = soup.find_all('p')
        text = '\n\n'.join(p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 20)
    else:
        parts = []
        for elem in article.find_all(['h1', 'h2', 'h3', 'h4', 'p', 'li', 'blockquote']):
            text = elem.get_text(strip=True)
            if not text:
                continue
            if elem.name in ('h1', 'h2', 'h3', 'h4'):
                parts.append(f"\n## {text}\n")
            elif elem.name == 'blockquote':
                parts.append(f"> {text}")
            elif elem.name == 'li':
                parts.append(f"- {text}")
            else:
                parts.append(text)
        text = '\n\n'.join(parts)

    return title, text


def extract_substack_article(html):
    """Extract article text from Substack HTML."""
    soup = BeautifulSoup(html, 'html.parser')

    title = ""
    title_tag = soup.find('h1', class_=re.compile(r'post-title', re.I))
    if not title_tag:
        title_tag = soup.find('h1')
    if title_tag:
        title = title_tag.get_text(strip=True)

    # Substack uses div.body for post content
    article = soup.find('div', class_='body')
    if not article:
        article = soup.find('div', class_=re.compile(r'post-content|available-content|entry-content', re.I))
    if not article:
        article = soup.find('article')
    if not article:
        article = soup.find('main')

    if not article:
        paragraphs = soup.find_all('p')
        text = '\n\n'.join(p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 20)
    else:
        parts = []
        for elem in article.find_all(['h1', 'h2', 'h3', 'h4', 'p', 'li', 'blockquote']):
            text = elem.get_text(strip=True)
            if not text:
                continue
            if elem.name in ('h1', 'h2', 'h3', 'h4'):
                parts.append(f"\n## {text}\n")
            elif elem.name == 'blockquote':
                parts.append(f"> {text}")
            elif elem.name == 'li':
                parts.append(f"- {text}")
            else:
                parts.append(text)
        text = '\n\n'.join(parts)

    return title, text


def scrape_url(url, extractor):
    """Fetch and extract an article."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code == 200:
            return extractor(resp.text)
        elif resp.status_code in (402, 403):
            print(f"  PAYWALLED ({resp.status_code}): {url}")
            return None, None
        else:
            print(f"  HTTP {resp.status_code}: {url}")
            return None, None
    except Exception as e:
        print(f"  ERROR: {url} - {e}")
        return None, None


def save_article(slug, title, text, prefix=""):
    """Save article to file."""
    if not text or len(text.strip()) < 100:
        return False

    filename = f"{prefix}{slug}.txt"
    filepath = os.path.join(OUTPUT_DIR, filename)

    if os.path.exists(filepath):
        return False

    with open(filepath, 'w', encoding='utf-8') as f:
        if title:
            f.write(f"# {title}\n\n")
        f.write(text)

    return True


def discover_substack_archive():
    """Try to discover more posts from the Substack archive page."""
    print("  Discovering Substack archive...")
    discovered = []
    try:
        resp = requests.get("https://katieparrott.substack.com/archive", headers=HEADERS, timeout=30)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            for a in soup.find_all('a', href=True):
                href = a['href']
                if '/p/' in href and 'katieparrott.substack.com' in href:
                    if href not in SUBSTACK_URLS:
                        discovered.append(href)
                elif href.startswith('/p/'):
                    full = f"https://katieparrott.substack.com{href}"
                    if full not in SUBSTACK_URLS:
                        discovered.append(full)
    except Exception as e:
        print(f"  Archive discovery error: {e}")

    # Also try sitemap
    try:
        resp = requests.get("https://katieparrott.substack.com/sitemap.xml", headers=HEADERS, timeout=30)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'xml')
            for loc in soup.find_all('loc'):
                url = loc.get_text(strip=True)
                if '/p/' in url:
                    if url not in SUBSTACK_URLS and url not in discovered:
                        discovered.append(url)
    except Exception as e:
        print(f"  Sitemap discovery error: {e}")

    return list(set(discovered))


def discover_every_archive():
    """Try to discover more Working Overtime posts."""
    print("  Discovering every.to Working Overtime archive...")
    discovered = []
    try:
        # Try the feed
        resp = requests.get("https://every.to/working-overtime/feed.xml", headers=HEADERS, timeout=30)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'xml')
            for link in soup.find_all('link'):
                url = link.get_text(strip=True)
                if '/working-overtime/' in url and url not in EVERY_TO_URLS:
                    discovered.append(url)
    except Exception as e:
        print(f"  Feed discovery error: {e}")

    return list(set(discovered))


def main():
    new_count = 0
    skipped_paywall = 0
    failed = 0

    print(f"=== Katie Parrott Scraper ===")
    print(f"Output: {OUTPUT_DIR}")
    print()

    # Discover additional URLs
    extra_substack = discover_substack_archive()
    extra_every = discover_every_archive()

    all_substack = SUBSTACK_URLS + extra_substack
    all_every = EVERY_TO_URLS + extra_every

    if extra_substack:
        print(f"  Discovered {len(extra_substack)} additional Substack posts")
    if extra_every:
        print(f"  Discovered {len(extra_every)} additional Every posts")
    print()

    # Scrape every.to Working Overtime
    print(f"--- every.to/working-overtime ({len(all_every)} URLs) ---")
    for url in all_every:
        slug = slug_from_url(url)
        filepath = os.path.join(OUTPUT_DIR, f"every_{slug}.txt")

        if os.path.exists(filepath):
            continue

        print(f"  Fetching: {slug}")
        title, text = scrape_url(url, extract_every_to_article)

        if title is None and text is None:
            skipped_paywall += 1
            continue

        if save_article(slug, title, text, prefix="every_"):
            new_count += 1
            print(f"    SAVED: every_{slug}.txt ({len(text)} chars)")
        else:
            failed += 1
            print(f"    SKIPPED (too short): {slug}")

        time.sleep(1.5)

    # Scrape Substack
    print(f"\n--- katieparrott.substack.com ({len(all_substack)} URLs) ---")
    for url in all_substack:
        slug = slug_from_url(url)
        filepath = os.path.join(OUTPUT_DIR, f"substack_{slug}.txt")

        if os.path.exists(filepath):
            continue

        print(f"  Fetching: {slug}")
        title, text = scrape_url(url, extract_substack_article)

        if title is None and text is None:
            skipped_paywall += 1
            continue

        if save_article(slug, title, text, prefix="substack_"):
            new_count += 1
            print(f"    SAVED: substack_{slug}.txt ({len(text)} chars)")
        else:
            failed += 1
            print(f"    SKIPPED (too short): {slug}")

        time.sleep(1.5)

    total_files = len([f for f in os.listdir(OUTPUT_DIR) if f.endswith('.txt')])
    print(f"\n=== RESULTS ===")
    print(f"New files saved: {new_count}")
    print(f"Skipped (paywalled/error): {skipped_paywall}")
    print(f"Too short / failed: {failed}")
    print(f"Total .txt files: {total_files}")


if __name__ == "__main__":
    main()
