"""
Extra Dan Shipper articles found from paginated archive.
Scrapes only NEW articles not already in dan_shipper_source/.
"""

import os
import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "dan_shipper_source")
os.makedirs(OUTPUT_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# New URLs discovered from paginated archive (pages 2-4) not already scraped
NEW_URLS = [
    # Page 2 discoveries
    "https://every.to/chain-of-thought/how-language-models-work-ea805869-4778-4fb8-ad8f-2d10cc439b4c",
    "https://every.to/chain-of-thought/is-ai-progress-hitting-a-wall",
    "https://every.to/chain-of-thought/everything-openai-launched-at-devday",
    "https://every.to/chain-of-thought/ai-journaling-changed-my-life",
    "https://every.to/chain-of-thought/review-chatgpt-s-new-advanced-voice-mode",
    "https://every.to/chain-of-thought/the-great-ai-unbundling",
    "https://every.to/chain-of-thought/ai-can-help-you-make-big-life-decisions",
    "https://every.to/chain-of-thought/when-ai-gets-more-capable-what-will-humans-do",
    "https://every.to/chain-of-thought/apple-embraces-the-enemy",
    "https://every.to/chain-of-thought/coding-with-devin-my-new-ai-programming-agent",
    "https://every.to/chain-of-thought/agent-native-architectures-how-to-build-apps-after-the-end-of-code",
    # Page 3 discoveries
    "https://every.to/chain-of-thought/working-right-at-the-ragged-edge-of-ai",
    "https://every.to/chain-of-thought/gpt-5-is-coming-reading-between-the-lines-at-microsoft-build",
    "https://every.to/chain-of-thought/gpt-4o-and-openai-s-race-to-win-consumers",
    "https://every.to/chain-of-thought/i-spent-24-hours-with-github-copilot-workspaces",
    "https://every.to/chain-of-thought/will-you-read-writing-from-an-ai",
    "https://every.to/chain-of-thought/capability-blindness-and-the-future-of-creativity",
    "https://every.to/chain-of-thought/hypothetical-journal-entries-written-by-ai",
    "https://every.to/chain-of-thought/simulating-one-way-door-decisions-with-ai",
    "https://every.to/chain-of-thought/can-a-startup-kill-chatgpt",
    "https://every.to/chain-of-thought/i-spent-a-week-with-gemini-pro-1-5-it-s-fantastic",
    "https://every.to/chain-of-thought/should-you-buy-a-vision-pro-a-guide",
    "https://every.to/chain-of-thought/quick-hits-new-ai-features-from-arc-and-chatgpt",
    "https://every.to/chain-of-thought/chatgpt-unlocks-the-most-powerful-force-on-earth",
    "https://every.to/chain-of-thought/ai-assisted-decision-making-6aa7c1f7-ce2e-430f-bfec-d68a13d9f3e5",
    "https://every.to/chain-of-thought/the-king-is-back-in-the-castle",
    # Page 4 discoveries
    "https://every.to/chain-of-thought/what-i-saw-at-openai-s-developer-day",
    "https://every.to/chain-of-thought/chatgpt-is-the-best-journal-i-ve-ever-used",
    "https://every.to/chain-of-thought/you-re-a-developer-now",
    "https://every.to/chain-of-thought/ai-assisted-decision-making",
    "https://every.to/chain-of-thought/wanted-high-performers-for-the-last-job-you-ll-ever-have",
    "https://every.to/chain-of-thought/great-artists-steal-with-llms",
    "https://every.to/chain-of-thought/how-to-develop-your-taste-for-new-technologies",
    "https://every.to/chain-of-thought/llms-can-simulate-personality-that-s-a-big-deal",
    "https://every.to/chain-of-thought/can-ai-and-ml-predict-depression-and-figure-out-how-to-help",
    "https://every.to/chain-of-thought/the-optimal-level-of-optimization",
    "https://every.to/chain-of-thought/please-make-a-better-kindle",
    "https://every.to/chain-of-thought/i-guess-i-m-a-programming-teacher-now",
    # Vibe check / other columns by Dan
    "https://every.to/chain-of-thought/o3-pro-vibe-check-a-slow-steady-last-resort",
    # Seeing like a LM series (some may be duplicates but will be caught)
    "https://every.to/chain-of-thought/seeing-business-like-a-language-model",
    "https://every.to/chain-of-thought/seeing-science-like-a-language-model",
    "https://every.to/chain-of-thought/seeing-like-a-language-model",
    # More from search
    "https://every.to/chain-of-thought/microsoft-s-ai-vision-an-open-internet-made-for-agents",
    "https://every.to/chain-of-thought/how-to-figure-out-what-people-want",
    "https://every.to/chain-of-thought/the-mantra-of-this-ai-age-don-t-repeat-yourself",
    "https://every.to/chain-of-thought/gpt-4-5-won-t-blow-your-mind-it-might-befriend-it-instead",
    "https://every.to/chain-of-thought/does-gpt-4-know-me-better-than-my-girlfriend",
    # sora article (may be different slug from existing)
    "https://every.to/chain-of-thought/sora-and-the-future-of-filmmaking",
]


def slug_from_url(url):
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    slug = path.split("/")[-1]
    slug = re.sub(r'-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', '', slug)
    slug = re.sub(r'[^a-zA-Z0-9-]', '-', slug)
    slug = re.sub(r'-+', '-', slug).strip('-')
    return slug[:80]


def extract_article(html):
    soup = BeautifulSoup(html, 'html.parser')
    title = ""
    title_tag = soup.find('h1')
    if title_tag:
        title = title_tag.get_text(strip=True)

    article = soup.find('article') or soup.find('div', class_=re.compile(r'post|article|content|body', re.I)) or soup.find('main')

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


def main():
    existing = set(os.listdir(OUTPUT_DIR))
    new_count = 0
    skipped = 0

    print(f"=== Dan Shipper Extra Scraper ===")
    print(f"Existing files: {len(existing)}")
    print(f"URLs to try: {len(NEW_URLS)}")
    print()

    for url in NEW_URLS:
        slug = slug_from_url(url)
        filename = f"every_{slug}.txt"

        # Check if file already exists (exact or close match)
        if filename in existing:
            skipped += 1
            continue

        # Also check slug substring in existing files
        already_have = False
        for f in existing:
            if slug in f or f.replace('.txt', '').replace('every_', '') == slug:
                already_have = True
                break
        if already_have:
            skipped += 1
            continue

        print(f"  Fetching: {slug}")
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            if resp.status_code != 200:
                print(f"    HTTP {resp.status_code}")
                continue
        except Exception as e:
            print(f"    ERROR: {e}")
            continue

        title, text = extract_article(resp.text)
        if not text or len(text.strip()) < 100:
            print(f"    SKIPPED (too short)")
            continue

        filepath = os.path.join(OUTPUT_DIR, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            if title:
                f.write(f"# {title}\n\n")
            f.write(text)

        existing.add(filename)
        new_count += 1
        print(f"    SAVED: {filename} ({len(text)} chars)")
        time.sleep(1.5)

    total = len([f for f in os.listdir(OUTPUT_DIR) if f.endswith('.txt')])
    print(f"\n=== RESULTS ===")
    print(f"New files: {new_count}")
    print(f"Skipped (already existed): {skipped}")
    print(f"Total .txt files now: {total}")


if __name__ == "__main__":
    main()
