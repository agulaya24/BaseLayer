#!/usr/bin/env python3
"""
Scrape Jack Clark's Import AI newsletter from Substack + jack-clark.net blog.
Saves each post as .txt in data/jack_clark_source/
"""

import subprocess
import json
import re
import os
import time
import html
from pathlib import Path

OUTPUT_DIR = Path(r"C:\Users\Aarik\Anthropic\memory_system\data\jack_clark_source")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def curl_json(url):
    """Fetch URL via curl and return parsed JSON."""
    r = subprocess.run(
        ["curl", "-s", "-H", "User-Agent: Mozilla/5.0", url],
        capture_output=True, timeout=30
    )
    return json.loads(r.stdout.decode("utf-8", errors="replace"))


def curl_html(url):
    """Fetch URL via curl and return HTML string."""
    r = subprocess.run(
        ["curl", "-s", "-H", "User-Agent: Mozilla/5.0", url],
        capture_output=True, timeout=30
    )
    return r.stdout.decode("utf-8", errors="replace")


def strip_html(html_str):
    """Strip HTML tags and decode entities, preserving paragraph breaks."""
    if not html_str:
        return ""
    # Replace block elements with newlines
    text = re.sub(r'<br\s*/?>', '\n', html_str)
    text = re.sub(r'</p>', '\n\n', text)
    text = re.sub(r'</div>', '\n\n', text)
    text = re.sub(r'</h[1-6]>', '\n\n', text)
    text = re.sub(r'</li>', '\n', text)
    text = re.sub(r'</blockquote>', '\n\n', text)
    # Remove all remaining tags
    text = re.sub(r'<[^>]+>', '', text)
    # Decode HTML entities
    text = html.unescape(text)
    # Normalize whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n[ \t]+', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def make_slug(title):
    """Convert title to clean filename slug."""
    slug = title.lower().strip()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s-]+', '-', slug)
    slug = slug.strip('-')
    return slug[:120]


def scrape_substack():
    """Scrape all Import AI posts from Substack API."""
    all_posts = []
    offset = 0
    batch_size = 12

    print("=== Scraping Import AI Substack ===")

    while True:
        url = f"https://importai.substack.com/api/v1/archive?sort=new&limit={batch_size}&offset={offset}"
        try:
            data = curl_json(url)
        except Exception as e:
            print(f"  Error at offset {offset}: {e}")
            break

        if not data:
            print(f"  No more posts at offset {offset}")
            break

        for post in data:
            title = post.get("title", "").strip()
            slug = post.get("slug", "")
            body_html = post.get("body_html", "")
            post_date = post.get("post_date", "")[:10]
            audience = post.get("audience", "everyone")

            if not title or not body_html:
                print(f"  Skipping (no title/body): offset={offset} slug={slug}")
                continue

            body_text = strip_html(body_html)
            word_count = len(body_text.split())

            if word_count < 200:
                print(f"  Skipping (too short, {word_count} words): {title[:60]}")
                continue

            all_posts.append({
                "title": title,
                "slug": slug,
                "date": post_date,
                "body": body_text,
                "word_count": word_count,
                "source": "substack",
                "audience": audience,
            })

        print(f"  Fetched offset {offset}: {len(data)} posts (total collected: {len(all_posts)})")
        offset += batch_size
        time.sleep(1)

    print(f"\nSubstack total: {len(all_posts)} substantive posts")
    return all_posts


def scrape_jack_clark_net():
    """Scrape jack-clark.net blog posts via WordPress REST API or sitemap."""
    all_posts = []
    print("\n=== Scraping jack-clark.net ===")

    # Try WordPress REST API first
    page = 1
    while True:
        url = f"https://jack-clark.net/wp-json/wp/v2/posts?per_page=100&page={page}"
        try:
            r = subprocess.run(
                ["curl", "-s", "-H", "User-Agent: Mozilla/5.0", url],
                capture_output=True, timeout=30
            )
            data = json.loads(r.stdout.decode("utf-8", errors="replace"))
            if isinstance(data, dict) and data.get("code"):
                # API error or no more pages
                print(f"  WP API page {page}: {data.get('message', 'done')}")
                break
            if not data:
                break
        except Exception as e:
            print(f"  WP API error page {page}: {e}")
            break

        for post in data:
            title = strip_html(post.get("title", {}).get("rendered", "")).strip()
            body_html = post.get("content", {}).get("rendered", "")
            post_date = post.get("date", "")[:10]
            slug = post.get("slug", "")

            if not title or not body_html:
                continue

            body_text = strip_html(body_html)
            word_count = len(body_text.split())

            if word_count < 200:
                print(f"  Skipping (too short, {word_count} words): {title[:60]}")
                continue

            all_posts.append({
                "title": title,
                "slug": slug,
                "date": post_date,
                "body": body_text,
                "word_count": word_count,
                "source": "jack-clark.net",
            })

        print(f"  WP API page {page}: {len(data)} posts (total collected: {len(all_posts)})")
        page += 1
        time.sleep(1)

    print(f"\njack-clark.net total: {len(all_posts)} substantive posts")
    return all_posts


def save_posts(posts):
    """Save posts as .txt files."""
    saved = 0
    skipped_dupes = 0
    seen_slugs = set()

    for post in posts:
        slug = make_slug(post["title"])
        if not slug:
            slug = post.get("slug", f"post-{saved}")

        # Deduplicate by slug
        if slug in seen_slugs:
            skipped_dupes += 1
            continue
        seen_slugs.add(slug)

        filename = f"{slug}.txt"
        filepath = OUTPUT_DIR / filename

        content = f"{post['title']}\n\n{post['body']}"

        filepath.write_text(content, encoding="utf-8")
        saved += 1

    print(f"\nSaved {saved} files to {OUTPUT_DIR}")
    if skipped_dupes:
        print(f"Skipped {skipped_dupes} duplicate slugs")
    return saved


def main():
    # Scrape both sources
    substack_posts = scrape_substack()
    jcnet_posts = scrape_jack_clark_net()

    # Combine, substack first (primary source)
    all_posts = substack_posts + jcnet_posts

    print(f"\n=== TOTAL: {len(all_posts)} posts collected ===")
    print(f"  Substack: {len(substack_posts)}")
    print(f"  jack-clark.net: {len(jcnet_posts)}")

    # Save
    saved = save_posts(all_posts)

    print(f"\n=== DONE: {saved} files saved to {OUTPUT_DIR} ===")

    # Summary stats
    if all_posts:
        total_words = sum(p["word_count"] for p in all_posts)
        avg_words = total_words // len(all_posts)
        print(f"Total words: {total_words:,}")
        print(f"Average words per post: {avg_words:,}")


if __name__ == "__main__":
    main()
