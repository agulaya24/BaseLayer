"""
Scraper for Amanda Askell's public writing.
Sources:
  1. askell.blog (Ghost blog) - 22 posts via Ghost Content API
  2. askell.io/publication/* - publication pages (abstracts/summaries)
  3. askell.io/talks/* - talk descriptions
"""

import requests
import json
import re
import os
import time
import html as html_module
from pathlib import Path

OUTPUT_DIR = Path(r"C:\Users\Aarik\Anthropic\memory_system\data\amanda_askell_source")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

GHOST_API_KEY = "b912c742c6d2fe7b43738dfde7"
GHOST_API_URL = f"https://askell.ghost.io/ghost/api/content/posts/?key={GHOST_API_KEY}&limit=all&fields=title,slug,url,published_at,html"

# Publication URLs from sitemap
PUBLICATION_URLS = [
    "https://askell.io/publication/objective-epistemic-consequentialism",
    "https://askell.io/publication/epistemic-consequentialism-and-epistemic-enkrasia",
    "https://askell.io/publication/pareto-principles-in-infinite-ethics",
    "https://askell.io/publication/ai-safety-needs-social-scientists",
    "https://askell.io/publication/prudential-objections-to-atheism",
    "https://askell.io/publication/the-role-of-cooperation-in-responsible-ai-development",
    "https://askell.io/publication/release-strategies-and-the-social-impacts-of-large-language-models",
    "https://askell.io/publication/evidence-neutrality-and-the-moral-value-of-information",
    "https://askell.io/publication/toward-trustworthy-ai-development",
    "https://askell.io/publication/language-models-are-few-shot-learners",
    "https://askell.io/publication/learning-transferable-visual-models",
    "https://askell.io/publication/hhh-from-rlhf",
    "https://askell.io/publication/beyond-the-imitation-game",
    "https://askell.io/publication/predictability-and-surprise",
    "https://askell.io/publication/ensuring-the-safety-of-artificial-intelligence",
    "https://askell.io/publication/a-general-language-assistant-as-a-laboratory-for-alignment",
    "https://askell.io/publication/transformer-circuits",
    "https://askell.io/publication/instructions-with-feedback",
    "https://askell.io/publication/language-models-mostly-know-what-they-know",
    "https://askell.io/publication/red-teaming-language-models",
    "https://askell.io/publication/induction-heads",
    "https://askell.io/publication/measuring-scalable-oversight",
    "https://askell.io/publication/cai",
    "https://askell.io/publication/model-written-evals",
    "https://askell.io/publication/moral-self-correction",
    "https://askell.io/publication/measuring-subjective-global-opinions",
    "https://askell.io/publication/towards-monosemanticity",
    "https://askell.io/publication/specific-general-principles",
    "https://askell.io/publication/sycophancy",
    "https://askell.io/publication/evaulating-mitigating-discrimination",
    "https://askell.io/publication/sleeper-agents",
    "https://askell.io/publication/carbon-offsetting",
]

TALK_URLS = [
    "https://askell.io/talks/eagx-boston-moral-value-of-information",
    "https://askell.io/talks/rationally-speaking-pascal",
    "https://askell.io/talks/rome-moral-offsetting",
    "https://askell.io/talks/80000-hours-moral-empathy",
    "https://askell.io/talks/ea-global-ai-safety-needs-social-scientists",
    "https://askell.io/talks/bagi-2019-civilization-goal",
    "https://askell.io/talks/twiml-gpt2",
    "https://askell.io/talks/80000-hours-latest-in-ai-policy-and-strategy",
    "https://askell.io/talks/eagx-boston-responsible-ai-development",
    "https://askell.io/talks/berkman-klein-ai-collective-action",
    "https://askell.io/talks/ai-salon-dual-use",
    "https://askell.io/talks/cnas-american-leadership-ai",
    "https://askell.io/talks/girl-geek-x-ai-policy",
    "https://askell.io/talks/code-org",
    "https://askell.io/talks/neurips-ai-ethics",
]


def strip_html(html_content):
    """Strip HTML tags, decode entities, clean whitespace."""
    if not html_content:
        return ""
    # Replace <br>, <p>, <div>, <li> with newlines
    text = re.sub(r'<br\s*/?>', '\n', html_content)
    text = re.sub(r'</p>', '\n\n', text)
    text = re.sub(r'</div>', '\n', text)
    text = re.sub(r'</li>', '\n', text)
    text = re.sub(r'<li[^>]*>', '- ', text)
    text = re.sub(r'</h[1-6]>', '\n\n', text)
    # Remove blockquote tags but keep content
    text = re.sub(r'<blockquote[^>]*>', '\n> ', text)
    text = re.sub(r'</blockquote>', '\n', text)
    # Remove all remaining tags
    text = re.sub(r'<[^>]+>', '', text)
    # Decode HTML entities
    text = html_module.unescape(text)
    # Clean up whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' +', ' ', text)
    return text.strip()


def make_slug(title):
    """Create a filesystem-safe slug from title."""
    slug = title.lower()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s]+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    slug = slug.strip('-')
    return slug[:80]


def word_count(text):
    return len(text.split())


def save_post(title, text, date, source_url, prefix=""):
    """Save a post to a .txt file. Returns True if saved."""
    wc = word_count(text)
    if wc < 200:
        print(f"  SKIP ({wc} words): {title}")
        return False

    slug = make_slug(title)
    if prefix:
        filename = f"{prefix}_{slug}.txt"
    else:
        filename = f"{slug}.txt"

    filepath = OUTPUT_DIR / filename

    content = f"{title}\n"
    content += f"Source: {source_url}\n"
    if date:
        content += f"Date: {date}\n"
    content += f"\n{text}\n"

    filepath.write_text(content, encoding='utf-8')
    print(f"  SAVED ({wc} words): {filename}")
    return True


def scrape_blog_posts():
    """Scrape all posts from askell.blog via Ghost Content API."""
    print("=" * 60)
    print("SCRAPING askell.blog (Ghost API)")
    print("=" * 60)

    resp = requests.get(GHOST_API_URL, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    posts = data.get('posts', [])

    print(f"Found {len(posts)} posts\n")

    saved = 0
    for post in posts:
        title = post['title']
        html_content = post.get('html', '')
        date = post.get('published_at', '')[:10]
        url = post.get('url', '')

        text = strip_html(html_content)
        if save_post(title, text, date, url, prefix="blog"):
            saved += 1

        time.sleep(0.2)  # Light delay since it's a single API call

    print(f"\nBlog posts saved: {saved}/{len(posts)}")
    return saved


def extract_page_text(html_content):
    """Extract main content from an askell.io page."""
    # Try to find the main content area
    # Look for article or main content divs
    main = re.search(r'<article[^>]*>(.*?)</article>', html_content, re.DOTALL)
    if not main:
        main = re.search(r'<div class="[^"]*content[^"]*">(.*?)</div>\s*</div>', html_content, re.DOTALL)
    if not main:
        main = re.search(r'<main[^>]*>(.*?)</main>', html_content, re.DOTALL)

    if main:
        return strip_html(main.group(1))

    # Fallback: strip the whole page
    # Remove nav, header, footer, script, style
    text = re.sub(r'<(nav|header|footer|script|style|head)[^>]*>.*?</\1>', '', html_content, flags=re.DOTALL)
    return strip_html(text)


def scrape_publication_pages():
    """Scrape publication pages from askell.io."""
    print("\n" + "=" * 60)
    print("SCRAPING askell.io/publication/* pages")
    print("=" * 60)

    saved = 0
    for url in PUBLICATION_URLS:
        slug = url.split('/')[-1]
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            html_content = resp.text

            # Extract title
            title_match = re.search(r'<title>([^<]+)</title>', html_content)
            title = title_match.group(1).strip() if title_match else slug.replace('-', ' ').title()
            # Clean title
            title = re.sub(r'\s*[\|–-]\s*Amanda Askell.*$', '', title).strip()

            text = extract_page_text(html_content)

            if save_post(title, text, None, url, prefix="pub"):
                saved += 1
            else:
                # Check if there's at least an abstract
                abstract_match = re.search(r'(?:abstract|summary|description)["\s:>]*(.*?)(?:<|$)', html_content, re.DOTALL | re.IGNORECASE)
                if abstract_match:
                    abstract_text = strip_html(abstract_match.group(1))
                    if word_count(abstract_text) >= 50:
                        save_post(title + " (Abstract)", abstract_text, None, url, prefix="pub")

        except Exception as e:
            print(f"  ERROR: {slug}: {e}")

        time.sleep(1)

    print(f"\nPublication pages saved: {saved}/{len(PUBLICATION_URLS)}")
    return saved


def scrape_talk_pages():
    """Scrape talk description pages from askell.io."""
    print("\n" + "=" * 60)
    print("SCRAPING askell.io/talks/* pages")
    print("=" * 60)

    saved = 0
    for url in TALK_URLS:
        slug = url.split('/')[-1]
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            html_content = resp.text

            title_match = re.search(r'<title>([^<]+)</title>', html_content)
            title = title_match.group(1).strip() if title_match else slug.replace('-', ' ').title()
            title = re.sub(r'\s*[\|–-]\s*Amanda Askell.*$', '', title).strip()

            text = extract_page_text(html_content)

            if save_post(title, text, None, url, prefix="talk"):
                saved += 1

        except Exception as e:
            print(f"  ERROR: {slug}: {e}")

        time.sleep(1)

    print(f"\nTalk pages saved: {saved}/{len(TALK_URLS)}")
    return saved


def scrape_additional_pages():
    """Scrape CV and other content pages from askell.io."""
    print("\n" + "=" * 60)
    print("SCRAPING askell.io additional pages")
    print("=" * 60)

    pages = [
        "https://askell.io/",
        "https://askell.io/cv/",
        "https://askell.io/projects/",
    ]

    saved = 0
    for url in pages:
        slug = url.rstrip('/').split('/')[-1] or 'home'
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()

            title_match = re.search(r'<title>([^<]+)</title>', resp.text)
            title = title_match.group(1).strip() if title_match else slug.title()
            title = re.sub(r'\s*[\|–-]\s*Amanda Askell.*$', '', title).strip()

            text = extract_page_text(resp.text)
            if save_post(title, text, None, url, prefix="page"):
                saved += 1

        except Exception as e:
            print(f"  ERROR: {slug}: {e}")

        time.sleep(1)

    print(f"\nAdditional pages saved: {saved}/{len(pages)}")
    return saved


if __name__ == "__main__":
    print("Amanda Askell Public Writing Scraper")
    print("=" * 60)
    print(f"Output: {OUTPUT_DIR}\n")

    total = 0
    total += scrape_blog_posts()
    total += scrape_publication_pages()
    total += scrape_talk_pages()
    total += scrape_additional_pages()

    print("\n" + "=" * 60)
    print(f"TOTAL FILES SAVED: {total}")
    print("=" * 60)

    # List all files
    files = sorted(OUTPUT_DIR.glob("*.txt"))
    print(f"\nFiles in output directory: {len(files)}")
    for f in files:
        size = f.stat().st_size
        print(f"  {f.name} ({size:,} bytes)")
