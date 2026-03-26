"""Scrape Elad Gil's blog from blog.eladgil.com (Substack)"""
import requests
from bs4 import BeautifulSoup
import re
import os
import time
import json

OUTPUT_DIR = r"C:\Users\Aarik\Anthropic\memory_system\data\elad_gil_source"
os.makedirs(OUTPUT_DIR, exist_ok=True)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

def get_archive_posts():
    """Get post list from Substack API."""
    posts = []
    offset = 0
    limit = 50
    while True:
        url = f"https://blog.eladgil.com/api/v1/archive?sort=new&search=&offset={offset}&limit={limit}"
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            print(f"Archive API returned {r.status_code} at offset {offset}")
            break
        data = r.json()
        if not data:
            break
        for post in data:
            posts.append({
                'title': post.get('title', ''),
                'slug': post.get('slug', ''),
                'date': post.get('post_date', ''),
                'url': post.get('canonical_url', ''),
                'id': post.get('id', ''),
            })
        print(f"  Fetched {len(data)} posts at offset {offset} (total: {len(posts)})")
        if len(data) < limit:
            break
        offset += limit
        time.sleep(0.5)
    return posts

def slugify(title):
    s = title.lower().strip()
    s = re.sub(r'[^a-z0-9\s-]', '', s)
    s = re.sub(r'[\s]+', '-', s)
    s = re.sub(r'-+', '-', s)
    return s[:80].strip('-')

def scrape_post(post):
    """Scrape a single post."""
    url = post['url']
    if not url:
        url = f"https://blog.eladgil.com/p/{post['slug']}"

    r = requests.get(url, headers=HEADERS, timeout=15)
    if r.status_code != 200:
        print(f"  FAILED {r.status_code}: {url}")
        return None

    soup = BeautifulSoup(r.text, 'lxml')

    # Get article body
    body = soup.find('div', class_='body')
    if not body:
        body = soup.find('div', class_='available-content')
    if not body:
        body = soup.find('article')

    if not body:
        print(f"  NO BODY: {url}")
        return None

    # Remove script/style tags
    for tag in body.find_all(['script', 'style', 'button', 'svg']):
        tag.decompose()

    # Extract text
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
    if len(content) < 100:
        print(f"  TOO SHORT ({len(content)} chars): {url}")
        return None

    return content

def main():
    print("Fetching Elad Gil archive...")
    posts = get_archive_posts()
    print(f"Found {len(posts)} posts total")

    # Take up to 60 posts
    posts = posts[:60]

    saved = 0
    for i, post in enumerate(posts):
        title = post['title']
        date_str = post['date'][:10] if post['date'] else '0000-00-00'
        slug = slugify(title)
        url = post['url'] or f"https://blog.eladgil.com/p/{post['slug']}"

        filename = f"{date_str}_{slug}.txt"
        filepath = os.path.join(OUTPUT_DIR, filename)

        if os.path.exists(filepath):
            print(f"[{i+1}/{len(posts)}] SKIP (exists): {title[:60]}")
            saved += 1
            continue

        print(f"[{i+1}/{len(posts)}] Scraping: {title[:60]}...")
        content = scrape_post(post)
        if content:
            header = f"Title: {title}\nDate: {date_str}\nSource: {url}\n\n---\n\n"
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(header + content)
            saved += 1
            print(f"  Saved: {filename} ({len(content)} chars)")

        time.sleep(1)

    print(f"\nDone! Saved {saved}/{len(posts)} posts to {OUTPUT_DIR}")

if __name__ == '__main__':
    main()
