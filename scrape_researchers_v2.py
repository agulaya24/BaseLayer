"""
Round 2: Fix issues from first scrape.
- Tal Yarkoni: SPA site, try his old blog (talyarkoni.org is Nuxt, need different approach)
- Maarten Sap: scrape ALL notes (some had < 200 char threshold), add Semantic Scholar with delay
- Cristian: add more project pages
- Dan Jurafsky: scrape languageoffood.blogspot.com
- Myra Cheng: scrape arxiv papers directly
"""
import os
import re
import time
import requests
import warnings
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

warnings.filterwarnings('ignore')

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
BASE = r'C:\Users\Aarik\Anthropic\memory_system\data'

def safe_filename(text, max_len=80):
    text = re.sub(r'[^\w\s-]', '', text.lower().strip())
    text = re.sub(r'[\s]+', '_', text)
    return text[:max_len] if text else 'untitled'

def get_soup(url, timeout=15):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        return BeautifulSoup(r.text, 'html.parser'), r.text
    except Exception as e:
        print(f'  ERROR fetching {url}: {e}')
        return None, None

def extract_text(soup):
    for tag in soup.find_all(['script', 'style', 'nav', 'footer']):
        tag.decompose()
    content = soup.find('article') or soup.find('main') or soup.find(class_=re.compile(r'content|post|entry|article'))
    if not content:
        content = soup.find('body') or soup
    text = content.get_text(separator='\n', strip=True)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text

def save_file(directory, filename, content, title=''):
    os.makedirs(directory, exist_ok=True)
    filepath = os.path.join(directory, filename)
    if title:
        content = f"Title: {title}\n\n{content}"
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

def get_semantic_scholar_papers(query, outdir, limit=30):
    """Get papers via Semantic Scholar API with rate limiting."""
    count = 0
    try:
        api_url = f'https://api.semanticscholar.org/graph/v1/author/search?query={query}&fields=papers'
        r = requests.get(api_url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            print(f'  Semantic Scholar search returned {r.status_code}')
            return 0
        data = r.json()
        if not data.get('data'):
            print(f'  No authors found on Semantic Scholar')
            return 0

        author_id = data['data'][0].get('authorId')
        if not author_id:
            return 0

        time.sleep(1)  # Rate limit
        papers_url = f'https://api.semanticscholar.org/graph/v1/author/{author_id}/papers?fields=title,abstract,year,citationCount&limit=100'
        r2 = requests.get(papers_url, headers=HEADERS, timeout=15)
        if r2.status_code != 200:
            print(f'  Papers endpoint returned {r2.status_code}')
            return 0

        papers = r2.json().get('data', [])
        papers_with_abstract = [p for p in papers if p.get('abstract') and len(p.get('abstract', '')) > 50]
        papers_with_abstract.sort(key=lambda x: x.get('citationCount', 0), reverse=True)
        print(f'  Found {len(papers_with_abstract)} papers with abstracts (of {len(papers)} total)')

        for p in papers_with_abstract[:limit]:
            title = p['title']
            abstract = p['abstract']
            year = p.get('year', 'unknown')
            citations = p.get('citationCount', 0)
            content = f"Year: {year}\nCitations: {citations}\n\nAbstract:\n{abstract}"
            fname = safe_filename(title) + '.txt'
            save_file(outdir, fname, content, title)
            count += 1
    except Exception as e:
        print(f'  Semantic Scholar error: {e}')
    return count


# ============================================================
# 1. MAARTEN SAP - Fix: scrape ALL notes, lower threshold
# ============================================================
def fix_maarten_sap():
    print('\n' + '='*60)
    print('MAARTEN SAP - Fixing notes scrape')
    print('='*60)

    outdir = os.path.join(BASE, 'maarten_sap_source')
    count = 0

    # All notes URLs found earlier
    notes = [
        ('notes/01-apply-grad-school.html', 'Applying to grad school'),
        ('notes/02-giving-talk-feedback.html', 'Giving feedback for talks'),
        ('notes/03-presenting-your-research.html', 'Presenting your research'),
        ('notes/04-turking-tips.html', 'Turking tips'),
        ('notes/05-rebuttals.html', 'Writing rebuttals'),
        ('notes/06-job-search-2020.html', 'Job search 2020'),
        ('notes/07-writing-rec-letters.html', 'Writing recommendation letters'),
        ('notes/08-third-year-part-0-postdoc.html', 'Reflections - Part 0 Postdoc'),
        ('notes/09-third-year-part-1-first-year.html', 'Reflections - Part 1 First Year'),
        ('notes/10-third-year-part-2-second-year.html', 'Reflections - Part 2 Second Year'),
    ]

    for path, title in notes:
        url = f'https://maartensap.com/{path}'
        soup, raw = get_soup(url)
        if soup:
            # Use full body text, lower threshold
            for tag in soup.find_all(['script', 'style', 'nav']):
                tag.decompose()
            body = soup.find('body')
            if body:
                text = body.get_text(separator='\n', strip=True)
                text = re.sub(r'\n{3,}', '\n\n', text)
                if len(text) > 100:
                    fname = safe_filename(title) + '.txt'
                    # Don't overwrite if already exists with more content
                    filepath = os.path.join(outdir, fname)
                    if not os.path.exists(filepath) or os.path.getsize(filepath) < len(text):
                        save_file(outdir, fname, text, title)
                        count += 1
                        print(f'  Saved: {fname} ({len(text)} chars)')
                else:
                    print(f'  Skipped {title}: only {len(text)} chars')
        else:
            print(f'  Failed: {url}')

    # Semantic Scholar with rate limiting
    print('  Fetching Semantic Scholar papers...')
    time.sleep(1)
    sc_count = get_semantic_scholar_papers('Maarten+Sap', outdir, limit=30)
    count += sc_count

    print(f'\n  NEW files for Maarten Sap: {count}')
    return count


# ============================================================
# 2. CRISTIAN - Add project pages
# ============================================================
def fix_cristian():
    print('\n' + '='*60)
    print('CRISTIAN - Adding project pages')
    print('='*60)

    outdir = os.path.join(BASE, 'cristian_danescu_source')
    count = 0

    # His well-known project pages
    project_pages = [
        'https://www.cs.cornell.edu/~cristian/Politeness.html',
        'https://www.cs.cornell.edu/~cristian/Cornell_Movie-Dialogs_Corpus.html',
        'https://www.cs.cornell.edu/~cristian/Winning_arguments.html',
        'https://www.cs.cornell.edu/~cristian/Echoes_of_power.html',
        'https://www.cs.cornell.edu/~cristian/Conversations_gone_awry.html',
        'https://www.cs.cornell.edu/~cristian/Asking_too_much.html',
        'https://www.cs.cornell.edu/~cristian/Reading_tea_leaves.html',
        'https://www.cs.cornell.edu/~cristian/Linguistic_change.html',
        'https://www.cs.cornell.edu/~cristian/A_computational_approach.html',
        'https://www.cs.cornell.edu/~cristian/Memorability.html',
        'https://www.cs.cornell.edu/~cristian/No_country_for_old_members.html',
        'https://www.cs.cornell.edu/~cristian/Youshouldknowabout.html',
    ]

    for url in project_pages:
        soup, _ = get_soup(url)
        if soup:
            text = extract_text(soup)
            if len(text) > 100:
                slug = safe_filename(url.split('/')[-1].replace('.html', ''))
                filepath = os.path.join(outdir, f'{slug}.txt')
                if not os.path.exists(filepath):
                    save_file(outdir, f'{slug}.txt', text)
                    count += 1
                    print(f'  Saved: {slug}.txt ({len(text)} chars)')

    # Semantic Scholar
    print('  Fetching Semantic Scholar papers...')
    time.sleep(2)
    sc_count = get_semantic_scholar_papers('Cristian+Danescu-Niculescu-Mizil', outdir, limit=30)
    count += sc_count

    print(f'\n  NEW files for Cristian: {count}')
    return count


# ============================================================
# 3. TAL YARKONI - His site is SPA. Try his old WordPress blog + Semantic Scholar
# ============================================================
def fix_tal_yarkoni():
    print('\n' + '='*60)
    print('TAL YARKONI - SPA site, trying alternative approaches')
    print('='*60)

    outdir = os.path.join(BASE, 'tal_yarkoni_source')
    count = 0

    # His old blog was at talyarkoni.org but it's now a Nuxt SPA
    # Try the Wayback Machine CDX API to find his blog posts
    # Or check if there's a sitemap
    sitemap_urls = [
        'https://talyarkoni.org/sitemap.xml',
        'https://talyarkoni.org/sitemap_index.xml',
    ]

    post_urls = set()
    for sm_url in sitemap_urls:
        soup, raw = get_soup(sm_url)
        if soup and raw:
            # Parse XML sitemap
            for loc in soup.find_all('loc'):
                url = loc.get_text(strip=True)
                if '/blog/' in url or '/post/' in url or re.search(r'/\d{4}/', url):
                    post_urls.add(url)
            print(f'  Sitemap {sm_url}: found {len(post_urls)} post URLs')

    # Try known blog URL patterns
    # Tal Yarkoni was known for his blog "[citation needed]"
    # Try old WordPress-style URLs
    test_urls = [
        'https://talyarkoni.org/blog',
        'https://talyarkoni.org/posts',
        'https://talyarkoni.org/writing',
    ]

    for url in test_urls:
        soup, raw = get_soup(url)
        if soup and raw and len(raw) > 1000:
            print(f'  Found content at {url} ({len(raw)} chars)')
            # Extract post links
            for a in soup.find_all('a', href=True):
                href = a['href']
                if '/blog/' in href or '/post/' in href:
                    full = urljoin(url, href)
                    post_urls.add(full)

    # The Nuxt site has blog content rendered client-side
    # Let's try to find the API/data endpoints
    soup, raw = get_soup('https://talyarkoni.org')
    if raw:
        # Look for __NUXT__ data in the HTML
        nuxt_match = re.search(r'window\.__NUXT__\s*=\s*(\{.*?\});', raw, re.DOTALL)
        if nuxt_match:
            print(f'  Found __NUXT__ data ({len(nuxt_match.group(1))} chars)')

        # Look for API endpoints in JS
        js_urls = re.findall(r'(?:href|to|path)["\s:]+["\']?(/[^"\'>\s]+)', raw)
        for u in set(js_urls):
            if any(k in u.lower() for k in ['blog', 'post', 'article']):
                print(f'  Potential route: {u}')
                post_urls.add(urljoin('https://talyarkoni.org', u))

    # Try fetching content from found URLs
    for url in sorted(post_urls):
        soup, raw = get_soup(url)
        if soup and raw and len(raw) > 2000:
            text = extract_text(soup)
            if len(text) > 200:
                title_tag = soup.find('h1')
                title = title_tag.get_text(strip=True) if title_tag else urlparse(url).path.split('/')[-1]
                fname = safe_filename(title) + '.txt'
                save_file(outdir, fname, text, title)
                count += 1
                print(f'  Saved: {fname}')

    # If still no blog posts, use Semantic Scholar heavily
    if count < 5:
        print('  Blog scrape limited. Falling back to Semantic Scholar papers...')
        time.sleep(2)
        sc_count = get_semantic_scholar_papers('Tal+Yarkoni', outdir, limit=40)
        count += sc_count

    # Also try his GitHub repos for README content
    gh_repos = [
        'https://raw.githubusercontent.com/tyarkoni/pybids/master/README.md',
        'https://raw.githubusercontent.com/tyarkoni/pliers/master/README.rst',
    ]
    for url in gh_repos:
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            if r.status_code == 200 and len(r.text) > 200:
                fname = safe_filename(url.split('/')[-3]) + '_readme.txt'
                save_file(outdir, fname, r.text)
                count += 1
                print(f'  Saved: {fname}')
        except:
            pass

    print(f'\n  TOTAL files for Tal Yarkoni: {count}')
    return count


# ============================================================
# 4. DAN JURAFSKY - Scrape Language of Food blog
# ============================================================
def fix_dan_jurafsky():
    print('\n' + '='*60)
    print('DAN JURAFSKY - Language of Food blogspot')
    print('='*60)

    outdir = os.path.join(BASE, 'dan_jurafsky_source')
    count = 0

    # Scrape languageoffood.blogspot.com
    base_url = 'https://languageoffood.blogspot.com'
    soup, _ = get_soup(base_url)
    if not soup:
        print('  Could not reach blogspot')
        return 0

    # Get all post links from main page and archives
    post_urls = set()

    # Find archive links
    archive_links = set()
    for a in soup.find_all('a', href=True):
        href = a['href']
        if 'languageoffood.blogspot.com' in href:
            if re.search(r'/\d{4}/\d{2}/', href):
                post_urls.add(href)
            if 'archive' in href.lower() or re.match(r'.*\d{4}_\d{2}.*', href):
                archive_links.add(href)

    # Check archive sidebar
    for widget in soup.find_all(class_=re.compile(r'archive|BlogArchive')):
        for a in widget.find_all('a', href=True):
            href = a['href']
            if re.search(r'/\d{4}[/_]\d{2}', href):
                archive_links.add(href)

    print(f'  Found {len(post_urls)} posts and {len(archive_links)} archive links on main page')

    # Visit archive pages to find more posts
    for arch_url in sorted(archive_links)[:30]:
        arch_soup, _ = get_soup(arch_url)
        if arch_soup:
            for a in arch_soup.find_all('a', href=True):
                href = a['href']
                if 'languageoffood.blogspot.com' in href and re.search(r'/\d{4}/\d{2}/[^/]+\.html', href):
                    post_urls.add(href)
        time.sleep(0.3)

    print(f'  Total posts found: {len(post_urls)}')

    # Scrape each post
    for url in sorted(post_urls):
        post_soup, _ = get_soup(url)
        if post_soup:
            # Get title
            title_tag = post_soup.find('h3', class_='post-title') or post_soup.find('h1', class_='post-title') or post_soup.find('h1')
            title = title_tag.get_text(strip=True) if title_tag else url.split('/')[-1].replace('.html', '')

            # Get post body
            post_body = post_soup.find(class_='post-body') or post_soup.find(class_='entry-content')
            if post_body:
                text = post_body.get_text(separator='\n', strip=True)
            else:
                text = extract_text(post_soup)

            if len(text) > 100:
                fname = safe_filename(title) + '.txt'
                filepath = os.path.join(outdir, fname)
                if not os.path.exists(filepath):
                    save_file(outdir, fname, text, title)
                    count += 1
                    print(f'  Saved: {fname} ({len(text)} chars)')
        time.sleep(0.3)

    print(f'\n  NEW files for Dan Jurafsky: {count}')
    return count


# ============================================================
# 5. MYRA CHENG - Get arxiv papers + subpages
# ============================================================
def fix_myra_cheng():
    print('\n' + '='*60)
    print('MYRA CHENG - Adding arxiv papers')
    print('='*60)

    outdir = os.path.join(BASE, 'myra_cheng_source')
    count = 0

    # Arxiv papers from her site
    arxiv_urls = [
        'https://arxiv.org/abs/2505.13995',  # social sycophancy
        'https://arxiv.org/abs/2502.13259',   # measuring
        'https://arxiv.org/abs/2502.14019',   # mitigating
        'https://arxiv.org/abs/2501.18045',   # metaphors AI
        'https://arxiv.org/abs/2410.08526',   # Cyber BFF
    ]

    for url in arxiv_urls:
        # Get abstract page
        soup, _ = get_soup(url)
        if soup:
            title_tag = soup.find('h1', class_='title')
            title = title_tag.get_text(strip=True).replace('Title:', '').strip() if title_tag else 'untitled'

            abstract_tag = soup.find('blockquote', class_='abstract')
            abstract = abstract_tag.get_text(strip=True).replace('Abstract:', '').strip() if abstract_tag else ''

            # Get authors
            authors_tag = soup.find('div', class_='authors')
            authors = authors_tag.get_text(strip=True) if authors_tag else ''

            if abstract and len(abstract) > 50:
                content = f"Authors: {authors}\n\nAbstract:\n{abstract}"
                fname = safe_filename(title) + '.txt'
                filepath = os.path.join(outdir, fname)
                if not os.path.exists(filepath):
                    save_file(outdir, fname, content, title)
                    count += 1
                    print(f'  Saved: {fname}')
        time.sleep(0.5)

    # Also get her research and teaching pages
    for path in ['research', 'teaching']:
        url = f'https://myracheng.github.io/{path}'
        soup, raw = get_soup(url)
        if soup and raw and len(raw) > 1000:
            text = extract_text(soup)
            if len(text) > 100:
                fname = f'{path}.txt'
                filepath = os.path.join(outdir, fname)
                if not os.path.exists(filepath):
                    save_file(outdir, fname, text, f'Myra Cheng - {path.title()}')
                    count += 1
                    print(f'  Saved: {fname}')

    # More papers from Semantic Scholar
    print('  Fetching more from Semantic Scholar...')
    time.sleep(2)
    sc_count = get_semantic_scholar_papers('Myra+Cheng', outdir, limit=20)
    count += sc_count

    print(f'\n  NEW files for Myra Cheng: {count}')
    return count


# ============================================================
# RUN ALL FIXES
# ============================================================
if __name__ == '__main__':
    results = {}
    results['Maarten Sap'] = fix_maarten_sap()
    results['Cristian'] = fix_cristian()
    results['Tal Yarkoni'] = fix_tal_yarkoni()
    results['Dan Jurafsky'] = fix_dan_jurafsky()
    results['Myra Cheng'] = fix_myra_cheng()

    print('\n' + '='*60)
    print('ROUND 2 RESULTS')
    print('='*60)
    for name, count in results.items():
        print(f'  {name}: {count} new files')

    # Count total files per directory
    print('\nFINAL FILE COUNTS:')
    dirs = [
        ('Maarten Sap', 'maarten_sap_source'),
        ('Cristian', 'cristian_danescu_source'),
        ('Tal Yarkoni', 'tal_yarkoni_source'),
        ('Dan Jurafsky', 'dan_jurafsky_source'),
        ('Myra Cheng', 'myra_cheng_source'),
    ]
    total = 0
    for name, dirname in dirs:
        dirpath = os.path.join(BASE, dirname)
        if os.path.exists(dirpath):
            files = [f for f in os.listdir(dirpath) if f.endswith('.txt')]
            total += len(files)
            print(f'  {name}: {len(files)} files in {dirname}/')
        else:
            print(f'  {name}: 0 files (directory not created)')
    print(f'  GRAND TOTAL: {total} files')
