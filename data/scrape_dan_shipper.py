"""
Scraper for Dan Shipper articles from every.to (Chain of Thought + Superorganizers)
and danshipper.com personal blog.

Saves each article as a separate .txt file in dan_shipper_source/
Skips files that already exist (based on slug matching).
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

# All known Dan Shipper article URLs collected from every.to and danshipper.com
EVERY_TO_URLS = [
    # Chain of Thought - newest first (2026-2025-2024-2023-2022)
    "https://every.to/chain-of-thought/when-your-vibe-coded-app-goes-viral-and-then-goes-down",
    "https://every.to/chain-of-thought/the-two-slice-team",
    "https://every.to/chain-of-thought/openai-has-some-catching-up-to-do",
    "https://every.to/chain-of-thought/agent-native-architectures-how-to-build-apps-after-the-end-of-code",
    "https://every.to/chain-of-thought/compound-engineering-how-every-codes-with-agents",
    "https://every.to/chain-of-thought/opus-4-5-collapsed-six-months-of-development-work-into-one-week",
    "https://every.to/chain-of-thought/where-explanations-end",
    "https://every.to/chain-of-thought/how-tools-shape-how-we-see-the-world",
    "https://every.to/chain-of-thought/seeing-creativity-like-a-language-model",
    "https://every.to/chain-of-thought/seeing-business-like-a-language-model",
    "https://every.to/chain-of-thought/seeing-science-like-a-language-model",
    "https://every.to/chain-of-thought/smuggled-intelligence",
    "https://every.to/chain-of-thought/seeing-like-a-language-model",
    "https://every.to/chain-of-thought/the-magic-minimum-for-ai-agents",
    "https://every.to/chain-of-thought/toward-a-definition-of-agi",
    "https://every.to/chain-of-thought/how-to-figure-out-what-people-want-90fad8a3-fb2e-4a54-b355-44d35b6d3e86",
    "https://every.to/chain-of-thought/microsoft-s-ai-vision-an-open-internet-made-for-agents",
    "https://every.to/chain-of-thought/ai-can-fix-social-media-s-original-sin",
    "https://every.to/chain-of-thought/the-mantra-of-this-ai-age-don-t-repeat-yourself-c53a8da2-8cf6-431d-8780-8197b2e57077",
    "https://every.to/chain-of-thought/why-generalists-own-the-future-e695c27f-b6f0-447b-bcd4-e5e144439693",
    "https://every.to/chain-of-thought/gpt-4-5-won-t-blow-your-mind-it-might-befriend-it-instead",
    "https://every.to/chain-of-thought/five-new-thinking-styles-for-working-with-thinking-machines-9091eb3c-b96d-4a17-af1e-fb0a3f544bfd",
    "https://every.to/chain-of-thought/llms-turn-every-question-into-an-answer-e44c1bb4-b8d5-42a1-9335-38c0bfd2c856",
    "https://every.to/chain-of-thought/what-can-language-models-actually-do-371b969e-d470-4639-a9fa-f873c133c19b",
    "https://every.to/chain-of-thought/writing-as-a-way-of-thinking",
    "https://every.to/chain-of-thought/against-explanations",
    "https://every.to/chain-of-thought/how-i-built-spiral",
    "https://every.to/chain-of-thought/openai-s-new-model-strawberry-explained",
    "https://every.to/chain-of-thought/openai-s-o1-model-explained",
    "https://every.to/chain-of-thought/is-chat-the-future-of-ai",
    "https://every.to/chain-of-thought/a-day-at-the-center-of-the-ai-boom",
    "https://every.to/chain-of-thought/you-have-no-choice-but-to-read-this",
    "https://every.to/chain-of-thought/the-unreasonable-effectiveness-of-1-1-learning-9713d7d6-e2d2-44cc-b3d6-25c982bf523f",
    "https://every.to/chain-of-thought/will-google-s-bard-be-a-destination-chatbot",
    "https://every.to/chain-of-thought/how-to-build-a-chatbot-course",
    "https://every.to/chain-of-thought/access-to-our-science-chat-bot",
    "https://every.to/chain-of-thought/the-most-creative-month-of-your-life",
    # Previously known articles (already partially scraped, but including for completeness)
    "https://every.to/chain-of-thought/gpt-3-is-the-best-journal-you-ve-ever-used",
    "https://every.to/chain-of-thought/the-knowledge-economy-is-over-welcome-to-the-allocation-economy",
    "https://every.to/chain-of-thought/gpt-4-is-a-reasoning-engine",
    "https://every.to/chain-of-thought/the-end-of-organizing",
    "https://every.to/chain-of-thought/the-knee-of-the-exponential-curve",
    "https://every.to/chain-of-thought/how-to-make-ai-write-like-your-favorite-author",
    "https://every.to/chain-of-thought/gpt-4-a-copilot-for-the-mind",
    "https://every.to/chain-of-thought/what-i-do-when-i-can-t-sleep",
    "https://every.to/chain-of-thought/why-generalists-own-the-future",
    "https://every.to/chain-of-thought/linus-lee-is-living-with-ai",
    "https://every.to/chain-of-thought/admitting-what-is-obvious",
    "https://every.to/chain-of-thought/ai-and-the-age-of-the-individual",
    "https://every.to/chain-of-thought/using-chatgpt-custom-instructions-for-fun-and-profit",
    "https://every.to/chain-of-thought/awe-anxiety-and-ai",
    "https://every.to/chain-of-thought/can-gpt-3-explain-my-past-and-tell-me-my-future",
    "https://every.to/chain-of-thought/gpt-4-can-use-tools-now-that-s-a-big-deal",
    "https://every.to/chain-of-thought/writing-essays-with-ai-a-guide",
    "https://every.to/chain-of-thought/ai-can-do-my-email-now",
    "https://every.to/chain-of-thought/openai-launches-a-document-and-code-editor-integrated-into-chatgpt",
    "https://every.to/chain-of-thought/the-most-important-wwdc-announcement-that-you-missed",
    "https://every.to/chain-of-thought/does-gpt-4-know-me-better-than-my-girlfriend",
    "https://every.to/chain-of-thought/how-hard-should-i-push-myself-83986449-8ffb-40de-9e61-214dd387b6b8",
    "https://every.to/chain-of-thought/chatgpt-and-the-future-of-the-human-mind",
    "https://every.to/chain-of-thought/this-vc-is-slowly-automating-their-job",
    "https://every.to/chain-of-thought/what-comes-after-saas",
    "https://every.to/chain-of-thought/claude-3-is-the-most-human-ai-yet",
    "https://every.to/chain-of-thought/how-sora-works-and-what-it-means",
    # Superorganizers
    "https://every.to/superorganizers/how-hard-should-i-push-myself",
    "https://every.to/superorganizers/the-fall-of-roam",
    "https://every.to/superorganizers/the-ceo-of-no-1725658",
    "https://every.to/superorganizers/andrew-huberman-s-morning-routine-backed-by-neuroscience",
    "https://every.to/superorganizers/dan-shipper-the-sultan-of-superorganizers-4345",
    "https://every.to/superorganizers/changing-the-world-to-change-yourself",
    # On Every / other columns
    "https://every.to/on-every/every-s-master-plan",
    "https://every.to/on-every/introducing-ai-i",
    "https://every.to/on-every/introducing-proof",
]

PERSONAL_BLOG_URLS = [
    "https://danshipper.com/pricing-heuristics",
    "https://danshipper.com/would-i-do-this-for-10-years",
    "https://danshipper.com/one-good-trick-for-interviewing-candidates-at-a-small-startup",
    "https://danshipper.com/should-i-oem-my-product",
    "https://danshipper.com/building-a-better-train-to-brooklyn",
    "https://danshipper.com/charlie-munger-on-how-to-build-a-2-trillion-startup",
    "https://danshipper.com/the-inverted-pyramid-what-bertrand-russell-can-teach-us-about-the-limits-of-logic",
    "https://danshipper.com/writing-and-running-haruki-murakami",
    "https://danshipper.com/bertrand-russell-and-will-durant-on-philosophy-science-and-religion",
]


def slug_from_url(url):
    """Extract a filename-safe slug from a URL."""
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    # Get the last segment
    slug = path.split("/")[-1]
    # Remove UUID suffixes (common on every.to)
    slug = re.sub(r'-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', '', slug)
    # Clean up
    slug = re.sub(r'[^a-zA-Z0-9-]', '-', slug)
    slug = re.sub(r'-+', '-', slug).strip('-')
    return slug[:80]  # cap length


def file_already_exists(slug):
    """Check if we already have this article (by slug substring match in existing filenames)."""
    existing = os.listdir(OUTPUT_DIR)
    slug_words = set(slug.split('-'))
    for f in existing:
        fname = f.lower().replace('.txt', '').replace('.md', '')
        # Check if slug is substantially in existing filename
        fname_words = set(re.split(r'[-_]', fname))
        overlap = slug_words & fname_words
        if len(overlap) >= min(3, len(slug_words)):
            return True
    return False


def extract_every_to_article(html):
    """Extract article text from every.to HTML."""
    soup = BeautifulSoup(html, 'html.parser')

    # Try to find the article title
    title = ""
    title_tag = soup.find('h1')
    if title_tag:
        title = title_tag.get_text(strip=True)

    # Find the article body - every.to uses various article containers
    article = soup.find('article')
    if not article:
        # Try div with specific classes
        article = soup.find('div', class_=re.compile(r'post|article|content|body', re.I))
    if not article:
        article = soup.find('main')

    if not article:
        # Fallback: get all paragraphs
        paragraphs = soup.find_all('p')
        text = '\n\n'.join(p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 20)
    else:
        # Get text from the article, preserving structure
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


def extract_danshipper_article(html):
    """Extract article text from danshipper.com HTML."""
    soup = BeautifulSoup(html, 'html.parser')

    title = ""
    title_tag = soup.find('h1')
    if title_tag:
        title = title_tag.get_text(strip=True)

    # Look for article/post content
    article = soup.find('article') or soup.find('div', class_=re.compile(r'post|content|entry', re.I))
    if not article:
        article = soup.find('main') or soup

    parts = []
    for elem in article.find_all(['h1', 'h2', 'h3', 'p', 'li', 'blockquote']):
        text = elem.get_text(strip=True)
        if not text:
            continue
        if elem.name in ('h1', 'h2', 'h3'):
            parts.append(f"\n## {text}\n")
        elif elem.name == 'blockquote':
            parts.append(f"> {text}")
        elif elem.name == 'li':
            parts.append(f"- {text}")
        else:
            parts.append(text)

    return title, '\n\n'.join(parts)


def scrape_url(url, extractor):
    """Fetch and extract an article."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code == 200:
            return extractor(resp.text)
        elif resp.status_code == 402 or resp.status_code == 403:
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


def main():
    new_count = 0
    skipped_existing = 0
    skipped_paywall = 0
    failed = 0

    print(f"=== Dan Shipper Scraper ===")
    print(f"Output: {OUTPUT_DIR}")
    print(f"Existing files: {len(os.listdir(OUTPUT_DIR))}")
    print()

    # Scrape every.to articles
    print(f"--- every.to articles ({len(EVERY_TO_URLS)} URLs) ---")
    for url in EVERY_TO_URLS:
        slug = slug_from_url(url)

        if file_already_exists(slug):
            skipped_existing += 1
            continue

        print(f"  Fetching: {slug}")
        title, text = scrape_url(url, extract_every_to_article)

        if title is None and text is None:
            if "PAYWALLED" not in str(text):
                failed += 1
            else:
                skipped_paywall += 1
            continue

        if save_article(slug, title, text, prefix="every_"):
            new_count += 1
            print(f"    SAVED: {slug} ({len(text)} chars)")
        else:
            skipped_existing += 1

        time.sleep(1.5)  # Be polite

    # Scrape personal blog (only new ones)
    print(f"\n--- danshipper.com articles ({len(PERSONAL_BLOG_URLS)} URLs) ---")
    for url in PERSONAL_BLOG_URLS:
        slug = slug_from_url(url)

        if file_already_exists(slug):
            skipped_existing += 1
            continue

        print(f"  Fetching: {slug}")
        title, text = scrape_url(url, extract_danshipper_article)

        if title is None and text is None:
            failed += 1
            continue

        if save_article(slug, title, text, prefix="blog_"):
            new_count += 1
            print(f"    SAVED: {slug} ({len(text)} chars)")
        else:
            skipped_existing += 1

        time.sleep(1.5)

    total_files = len([f for f in os.listdir(OUTPUT_DIR) if f.endswith('.txt')])
    print(f"\n=== RESULTS ===")
    print(f"New files saved: {new_count}")
    print(f"Skipped (already existed): {skipped_existing}")
    print(f"Skipped (paywalled): {skipped_paywall}")
    print(f"Failed: {failed}")
    print(f"Total .txt files now: {total_files}")


if __name__ == "__main__":
    main()
