"""Scrape older Elad Gil posts from his Substack (older posts accessible via /p/ URLs)."""
import requests
from bs4 import BeautifulSoup
import re
import os
import time
import sys

sys.stdout.reconfigure(encoding='utf-8')

OUTPUT_DIR = r"C:\Users\Aarik\Anthropic\memory_system\data\elad_gil_source"
os.makedirs(OUTPUT_DIR, exist_ok=True)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

# Known older posts found via web search (pre-Substack migrated posts + Substack posts not in archive API)
OLDER_POSTS = [
    ("https://blog.eladgil.com/p/ai-startup-vs-incumbent-value", "AI Startup Vs Incumbent Value"),
    ("https://blog.eladgil.com/p/startups-in-machine-learning-ai", "Startups in Machine Learning and AI"),
    ("https://blog.eladgil.com/p/startup-founders-personal-view-of", "A Startup Founders Personal View of the Financial Crisis"),
    ("https://blog.eladgil.com/p/founder-investors-scout-programs", "Founder Investors and Scout Programs"),
    ("https://blog.eladgil.com/p/running-business", "Running A Business"),
    ("https://blog.eladgil.com/p/7-types-of-angel-investors-what-is", "The 7 Types of Angel Investors"),
    ("https://blog.eladgil.com/p/bad-advice", "Bad Advice"),
    ("https://blog.eladgil.com/p/how-to-be-good-angel-angel-etiquette", "Angel Etiquette"),
    ("https://blog.eladgil.com/p/how-to-choose-right-vc-partner-for-you", "How To Choose The Right VC Partner For You"),
    ("https://blog.eladgil.com/p/put-your-investors-to-work-for-you", "Put Your Investors To Work For You"),
    ("https://blog.eladgil.com/p/how-to-sell-secondary-stock", "How To Sell Secondary Stock"),
    ("https://blog.eladgil.com/p/end-of-cycle", "End of Cycle"),
    ("https://blog.eladgil.com/p/how-to-win-as-second-mover", "How To Win As Second Mover"),
    ("https://blog.eladgil.com/p/moats-are-rarely-wrong", "Moats Are Rarely Wrong"),
    ("https://blog.eladgil.com/p/how-to-negotiate-with-venture-capitalists", "How To Negotiate With Venture Capitalists"),
    ("https://blog.eladgil.com/p/building-great-products", "Building Great Products"),
    ("https://blog.eladgil.com/p/10x-your-output", "10x Your Output"),
    ("https://blog.eladgil.com/p/what-is-strategy", "What Is Strategy"),
    ("https://blog.eladgil.com/p/m-and-a-how-to-sell-your-company", "M&A - How To Sell Your Company"),
    ("https://blog.eladgil.com/p/how-to-hire-great-people", "How To Hire Great People"),
    ("https://blog.eladgil.com/p/covid-silicon-valley-and-changes-ahead", "COVID Silicon Valley and Changes Ahead"),
    ("https://blog.eladgil.com/p/some-observations-on-tech-ipos-and-spacs", "Some Observations on Tech IPOs and SPACs"),
    ("https://blog.eladgil.com/p/fintech-the-bull-case", "Fintech The Bull Case"),
    ("https://blog.eladgil.com/p/where-are-the-robotic-bees", "Where Are The Robotic Bees"),
    ("https://blog.eladgil.com/p/social-strikes-back", "Social Strikes Back"),
    ("https://blog.eladgil.com/p/the-case-for-defense-tech", "The Case For Defense Tech"),
    ("https://blog.eladgil.com/p/machine-learning-and-ai-as-horizontal", "Machine Learning and AI as Horizontal Technology"),
    ("https://blog.eladgil.com/p/how-to-pick-career-for-maximum-impact", "How To Pick A Career For Maximum Impact"),
    ("https://blog.eladgil.com/p/how-to-work-with-pms", "How To Work With PMs"),
    ("https://blog.eladgil.com/p/how-to-fire-someone", "How To Fire Someone"),
    ("https://blog.eladgil.com/p/how-to-ask-for-a-raise", "How To Ask For A Raise"),
    ("https://blog.eladgil.com/p/unequal-opportunity", "Unequal Opportunity"),
    ("https://blog.eladgil.com/p/welcome-to-my-blog", "Welcome To My Blog"),
    ("https://blog.eladgil.com/p/high-growth-handbook", "High Growth Handbook"),
    ("https://blog.eladgil.com/p/the-election-technology-and-regulation", "The Election Technology and Regulation"),
    ("https://blog.eladgil.com/p/big-technology-acquisitions-that-almost", "Big Technology Acquisitions That Almost Happened"),
    ("https://blog.eladgil.com/p/the-3-types-of-platform-companies", "The 3 Types of Platform Companies"),
    ("https://blog.eladgil.com/p/how-to-build-a-brand", "How To Build A Brand"),
    ("https://blog.eladgil.com/p/fundraising-will-never-be-the-same", "Fundraising Will Never Be The Same"),
    ("https://blog.eladgil.com/p/defensibility-and-lock-in", "Defensibility and Lock In"),
    ("https://blog.eladgil.com/p/how-mergers-happen", "How Mergers Happen"),
]

def slugify(title):
    s = title.lower().strip()
    s = re.sub(r'[^a-z0-9\s-]', '', s)
    s = re.sub(r'[\s]+', '-', s)
    s = re.sub(r'-+', '-', s)
    return s[:80].strip('-')

def scrape_post(url, title):
    """Scrape a single Substack post."""
    r = requests.get(url, headers=HEADERS, timeout=15)
    if r.status_code != 200:
        return None, None

    soup = BeautifulSoup(r.text, 'lxml')

    # Try to extract date from meta tags
    date = "0000-00-00"
    date_meta = soup.find('meta', {'property': 'article:published_time'})
    if date_meta and date_meta.get('content'):
        date = date_meta['content'][:10]
    else:
        time_tag = soup.find('time')
        if time_tag and time_tag.get('datetime'):
            date = time_tag['datetime'][:10]

    # Get article body
    body = soup.find('div', class_='body')
    if not body:
        body = soup.find('div', class_='available-content')
    if not body:
        body = soup.find('article')
    if not body:
        return None, None

    for tag in body.find_all(['script', 'style', 'button', 'svg']):
        tag.decompose()

    paragraphs = []
    for elem in body.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'li', 'blockquote']):
        text = elem.get_text(strip=True)
        if text:
            tag = elem.name
            if tag.startswith('h'):
                paragraphs.append(f"\n## {text}\n")
            elif tag == 'li':
                paragraphs.append(f"- {text}")
            elif tag == 'blockquote':
                paragraphs.append(f"> {text}")
            else:
                paragraphs.append(text)

    content = '\n\n'.join(paragraphs)
    return content, date

def main():
    print("Scraping older Elad Gil posts...")

    # Check which files we already have
    existing = set(os.listdir(OUTPUT_DIR))
    print(f"Already have {len(existing)} files")

    saved = 0
    skipped = 0
    for i, (url, title) in enumerate(OLDER_POSTS):
        slug = slugify(title)

        # Check if we already have a file with this slug
        already_exists = any(slug in f for f in existing)
        if already_exists:
            print(f"[{i+1}/{len(OLDER_POSTS)}] SKIP (exists): {title[:60]}")
            skipped += 1
            continue

        print(f"[{i+1}/{len(OLDER_POSTS)}] Scraping: {title[:60]}...")
        content, date = scrape_post(url, title)

        if content and len(content) > 100:
            filename = f"{date}_{slug}.txt"
            filepath = os.path.join(OUTPUT_DIR, filename)
            header = f"Title: {title}\nDate: {date}\nSource: {url}\n\n---\n\n"
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(header + content)
            saved += 1
            print(f"  Saved: {filename} ({len(content)} chars)")
        else:
            print(f"  FAILED or too short")

        time.sleep(1)

    print(f"\nDone! Saved {saved} new posts, skipped {skipped}")
    total = len(os.listdir(OUTPUT_DIR))
    print(f"Total files in {OUTPUT_DIR}: {total}")

if __name__ == '__main__':
    main()
