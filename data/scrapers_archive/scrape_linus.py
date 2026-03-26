"""
Scrape Linus Lee's essays from thesephist.com.
Targets 40-50 substantial posts about personal tools, language models, creative computing, etc.
Saves as .txt files with title as first line.
"""

import requests
from bs4 import BeautifulSoup
import os
import time
import re

OUTPUT_DIR = r"C:\Users\Aarik\Anthropic\memory_system\data\linus_lee_source"
BASE_URL = "https://thesephist.com"

# Curated list of ~50 substantial essays covering his key topics:
# personal tools, language models, creative computing, software philosophy,
# thinking/writing, identity, and technical essays
POSTS = [
    # AI / Language Models / Research
    "/posts/ai/",
    "/posts/latent/",
    "/posts/representation/",
    "/posts/prism/",
    "/posts/mj-personalization/",
    "/posts/applied-research-problems-2024/",
    "/posts/backprop-through-reasoning/",
    "/posts/ai-collaborator/",
    "/posts/monocle/",
    "/posts/epistemic-calibration/",
    "/posts/search-vs-nav/",
    "/posts/synth/",

    # Tools / Software / Building
    "/posts/tools/",
    "/posts/browser/",
    "/posts/interface/",
    "/posts/notation/",
    "/posts/hypertext/",
    "/posts/software/",
    "/posts/software-architecture/",
    "/posts/programming-environment/",
    "/posts/computer-for-the-rest-of-us/",
    "/posts/complexity-conservation/",
    "/posts/unbundling-cloud/",
    "/posts/structured-thought/",
    "/posts/technical-sympathy/",
    "/posts/hyperlink/",
    "/posts/library/",
    "/posts/nav/",
    "/posts/text/",
    "/posts/micro-ux/",

    # Language / Writing / Thinking
    "/posts/how-i-write/",
    "/posts/language/",
    "/posts/pl/",
    "/posts/lua/",
    "/posts/narrative/",
    "/posts/literacy/",
    "/posts/word-experiments/",
    "/posts/extralinguistics/",
    "/posts/long-sentences/",
    "/posts/writer/",
    "/posts/thinking/",
    "/posts/ideaflow/",

    # Personal / Identity / Life Philosophy
    "/posts/im-linus/",
    "/posts/explore/",
    "/posts/alive/",
    "/posts/wonder/",
    "/posts/virtuosity/",
    "/posts/rocks-water/",
    "/posts/continuity/",
    "/posts/how-i-side-project/",
    "/posts/process/",
    "/posts/medium/",
    "/posts/resonant/",
    "/posts/infinite/",
    "/posts/legacy/",
    "/posts/materials/",
    "/posts/prove/",
    "/posts/spc/",

    # Creative / Music / Art
    "/posts/how-i-make-music/",
    "/posts/composing-the-future/",
    "/posts/beauty/",
    "/posts/painting/",
    "/posts/play/",
    "/posts/music/",
]

def clean_text(html_content):
    """Extract clean text from HTML, preserving paragraph structure."""
    soup = BeautifulSoup(html_content, 'html.parser')

    # Get the title
    title_tag = soup.find('h1')
    title = title_tag.get_text(strip=True) if title_tag else ""

    # Find the main article content - try common containers
    article = soup.find('article') or soup.find('main') or soup.find(class_=re.compile(r'post|article|content|entry'))

    if not article:
        # Fallback: use body
        article = soup.find('body')

    if not article:
        return None, None

    # Remove script, style, nav, header, footer elements
    for tag in article.find_all(['script', 'style', 'nav', 'header', 'footer', 'aside']):
        tag.decompose()

    # Build text with paragraph breaks
    lines = []
    for elem in article.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'li', 'blockquote', 'pre']):
        text = elem.get_text(separator=' ', strip=True)
        if text:
            if elem.name in ['h1', 'h2', 'h3', 'h4']:
                lines.append(f"\n{text}\n")
            elif elem.name == 'li':
                lines.append(f"- {text}")
            elif elem.name == 'blockquote':
                lines.append(f"> {text}")
            elif elem.name == 'pre':
                lines.append(f"```\n{text}\n```")
            else:
                lines.append(text)

    body = '\n\n'.join(lines)
    return title, body


def scrape_post(path):
    """Fetch and extract a single post."""
    url = BASE_URL + path
    try:
        resp = requests.get(url, timeout=30, headers={
            'User-Agent': 'Mozilla/5.0 (research scraper for personal use)'
        })
        resp.raise_for_status()
    except Exception as e:
        print(f"  FAILED to fetch {url}: {e}")
        return None, None

    return clean_text(resp.text)


def slug_from_path(path):
    """Extract slug from URL path."""
    return path.strip('/').split('/')[-1]


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    success = 0
    failed = 0
    skipped = 0

    print(f"Scraping {len(POSTS)} essays from thesephist.com...")
    print(f"Output: {OUTPUT_DIR}\n")

    for i, path in enumerate(POSTS):
        slug = slug_from_path(path)
        outfile = os.path.join(OUTPUT_DIR, f"{slug}.txt")

        if os.path.exists(outfile):
            print(f"[{i+1}/{len(POSTS)}] SKIP (exists): {slug}")
            skipped += 1
            continue

        print(f"[{i+1}/{len(POSTS)}] Fetching: {slug}...", end=" ", flush=True)

        title, body = scrape_post(path)

        if not body or len(body) < 200:
            print(f"SKIP (too short or empty)")
            failed += 1
            continue

        # Write file with title as first line
        with open(outfile, 'w', encoding='utf-8') as f:
            if title:
                f.write(f"{title}\n\n")
            f.write(body)

        word_count = len(body.split())
        print(f"OK ({word_count} words)")
        success += 1

        # Be polite - small delay between requests
        time.sleep(0.5)

    print(f"\nDone! {success} saved, {failed} failed, {skipped} skipped.")
    print(f"Total files in {OUTPUT_DIR}: {len(os.listdir(OUTPUT_DIR))}")


if __name__ == '__main__':
    main()
