"""
Scrape public blog content for 5 researchers.
"""
import os
import re
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
    """Extract readable text from a page."""
    # Remove scripts, styles
    for tag in soup.find_all(['script', 'style', 'nav', 'footer', 'header']):
        tag.decompose()

    # Try main content areas first
    content = soup.find('article') or soup.find('main') or soup.find(class_=re.compile(r'content|post|entry|article'))
    if not content:
        content = soup.find('body') or soup

    text = content.get_text(separator='\n', strip=True)
    # Clean up excessive blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text

def save_file(directory, filename, content, title=''):
    os.makedirs(directory, exist_ok=True)
    filepath = os.path.join(directory, filename)
    if title:
        content = f"Title: {title}\n\n{content}"
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    return filepath

# ============================================================
# 1. MAARTEN SAP
# ============================================================
def scrape_maarten_sap():
    print('\n' + '='*60)
    print('MAARTEN SAP - maartensap.com')
    print('='*60)

    outdir = os.path.join(BASE, 'maarten_sap_source')
    count = 0

    # Get notes/blog posts
    soup, _ = get_soup('https://maartensap.com')
    if not soup:
        return 0

    # Find all notes links
    notes_links = []
    for a in soup.find_all('a', href=True):
        if 'notes/' in a['href'] and a['href'].endswith('.html'):
            url = urljoin('https://maartensap.com/', a['href'])
            title = a.get_text(strip=True)
            notes_links.append((url, title))

    print(f'  Found {len(notes_links)} notes/blog posts')

    for url, title in notes_links:
        page_soup, _ = get_soup(url)
        if page_soup:
            text = extract_text(page_soup)
            if len(text) > 200:
                fname = safe_filename(title or url.split('/')[-1]) + '.txt'
                save_file(outdir, fname, text, title)
                count += 1
                print(f'  Saved: {fname} ({len(text)} chars)')

    # Also save the main page content (research themes, about)
    text = extract_text(soup)
    if len(text) > 200:
        save_file(outdir, 'homepage_research_themes.txt', text, 'Maarten Sap - Research Overview')
        count += 1
        print(f'  Saved: homepage_research_themes.txt')

    # Check news page for additional content
    news_soup, _ = get_soup('https://maartensap.com/news.html')
    if news_soup:
        text = extract_text(news_soup)
        if len(text) > 200:
            save_file(outdir, 'news_and_updates.txt', text, 'Maarten Sap - News and Updates')
            count += 1
            print(f'  Saved: news_and_updates.txt')

    # Try to get paper abstracts from his publications
    # Check Google Scholar page or DBLP
    print(f'  Checking for paper abstracts via Semantic Scholar...')
    try:
        api_url = 'https://api.semanticscholar.org/graph/v1/author/search?query=Maarten+Sap&fields=papers'
        r = requests.get(api_url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            data = r.json()
            if data.get('data'):
                author_id = data['data'][0].get('authorId')
                if author_id:
                    papers_url = f'https://api.semanticscholar.org/graph/v1/author/{author_id}/papers?fields=title,abstract,year,citationCount&limit=50'
                    r2 = requests.get(papers_url, headers=HEADERS, timeout=15)
                    if r2.status_code == 200:
                        papers = r2.json().get('data', [])
                        papers_with_abstract = [p for p in papers if p.get('abstract')]
                        papers_with_abstract.sort(key=lambda x: x.get('citationCount', 0), reverse=True)
                        print(f'  Found {len(papers_with_abstract)} papers with abstracts')
                        for p in papers_with_abstract[:30]:
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

    print(f'\n  TOTAL: {count} files saved for Maarten Sap')
    return count

# ============================================================
# 2. CRISTIAN DANESCU-NICULESCU-MIZIL
# ============================================================
def scrape_cristian():
    print('\n' + '='*60)
    print('CRISTIAN DANESCU-NICULESCU-MIZIL - Cornell')
    print('='*60)

    outdir = os.path.join(BASE, 'cristian_danescu_source')
    count = 0

    # His site is a React SPA, not easily scrapeable. Try ConvoKit docs
    # and Semantic Scholar for paper abstracts

    # Check ConvoKit documentation for his research perspective
    convo_soup, _ = get_soup('https://convokit.cornell.edu')
    if convo_soup:
        text = extract_text(convo_soup)
        if len(text) > 200:
            save_file(outdir, 'convokit_overview.txt', text, 'ConvoKit - Cornell Conversational Analysis Toolkit')
            count += 1
            print(f'  Saved: convokit_overview.txt')

    # Get ConvoKit documentation pages
    if convo_soup:
        doc_links = set()
        for a in convo_soup.find_all('a', href=True):
            href = a['href']
            if any(k in href for k in ['documentation', 'tutorial', 'guide', 'example']):
                full_url = urljoin('https://convokit.cornell.edu/', href)
                doc_links.add(full_url)

        for url in list(doc_links)[:10]:
            page_soup, _ = get_soup(url)
            if page_soup:
                text = extract_text(page_soup)
                if len(text) > 300:
                    slug = safe_filename(urlparse(url).path.replace('/', '_'))
                    save_file(outdir, f'convokit_{slug}.txt', text)
                    count += 1
                    print(f'  Saved: convokit_{slug}.txt')

    # Try his older static pages
    old_urls = [
        'https://www.cs.cornell.edu/~cristian/Politeness.html',
        'https://www.cs.cornell.edu/~cristian/Cornell_Movie-Dialogs_Corpus.html',
        'https://www.cs.cornell.edu/~cristian/Winning_arguments.html',
        'https://www.cs.cornell.edu/~cristian/Echoes_of_power.html',
        'https://www.cs.cornell.edu/~cristian/Conversations_gone_awry.html',
        'https://www.cs.cornell.edu/~cristian/Asking_too_much.html',
    ]
    for url in old_urls:
        page_soup, _ = get_soup(url)
        if page_soup:
            text = extract_text(page_soup)
            if len(text) > 200:
                slug = safe_filename(url.split('/')[-1].replace('.html', ''))
                save_file(outdir, f'{slug}.txt', text)
                count += 1
                print(f'  Saved: {slug}.txt ({len(text)} chars)')

    # Semantic Scholar papers
    print(f'  Checking Semantic Scholar for paper abstracts...')
    try:
        api_url = 'https://api.semanticscholar.org/graph/v1/author/search?query=Cristian+Danescu-Niculescu-Mizil&fields=papers'
        r = requests.get(api_url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            data = r.json()
            if data.get('data'):
                author_id = data['data'][0].get('authorId')
                if author_id:
                    papers_url = f'https://api.semanticscholar.org/graph/v1/author/{author_id}/papers?fields=title,abstract,year,citationCount&limit=50'
                    r2 = requests.get(papers_url, headers=HEADERS, timeout=15)
                    if r2.status_code == 200:
                        papers = r2.json().get('data', [])
                        papers_with_abstract = [p for p in papers if p.get('abstract')]
                        papers_with_abstract.sort(key=lambda x: x.get('citationCount', 0), reverse=True)
                        print(f'  Found {len(papers_with_abstract)} papers with abstracts')
                        for p in papers_with_abstract[:30]:
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

    print(f'\n  TOTAL: {count} files saved for Cristian')
    return count

# ============================================================
# 3. TAL YARKONI
# ============================================================
def scrape_tal_yarkoni():
    print('\n' + '='*60)
    print('TAL YARKONI - talyarkoni.org')
    print('='*60)

    outdir = os.path.join(BASE, 'tal_yarkoni_source')
    count = 0

    # Tal's site is likely a blog. Check structure
    soup, raw = get_soup('https://talyarkoni.org')
    if not soup:
        return 0

    # Find blog post links
    post_links = set()
    for a in soup.find_all('a', href=True):
        href = a['href']
        # WordPress-style blog URLs with dates
        if re.search(r'/\d{4}/\d{2}/', href) and 'talyarkoni.org' in href:
            post_links.add(href)
        elif re.search(r'/\d{4}/\d{2}/', href) and href.startswith('/'):
            post_links.add(urljoin('https://talyarkoni.org', href))

    print(f'  Found {len(post_links)} blog post links on homepage')

    # Check for pagination / archives
    archive_links = set()
    for a in soup.find_all('a', href=True):
        href = a['href']
        if 'page/' in href or 'archive' in href.lower():
            full = urljoin('https://talyarkoni.org/', href)
            archive_links.add(full)

    # Get more posts from paginated pages
    for page_url in sorted(archive_links)[:20]:
        page_soup, _ = get_soup(page_url)
        if page_soup:
            for a in page_soup.find_all('a', href=True):
                href = a['href']
                if re.search(r'/\d{4}/\d{2}/', href):
                    if 'talyarkoni.org' in href:
                        post_links.add(href)
                    elif href.startswith('/'):
                        post_links.add(urljoin('https://talyarkoni.org', href))

    print(f'  Total post links after pagination: {len(post_links)}')

    # Scrape each post
    for url in sorted(post_links):
        post_soup, _ = get_soup(url)
        if post_soup:
            title_tag = post_soup.find('h1', class_=re.compile(r'title|entry')) or post_soup.find('h1')
            title = title_tag.get_text(strip=True) if title_tag else url.split('/')[-2]
            text = extract_text(post_soup)
            if len(text) > 300:
                fname = safe_filename(title) + '.txt'
                save_file(outdir, fname, text, title)
                count += 1
                print(f'  Saved: {fname} ({len(text)} chars)')

    print(f'\n  TOTAL: {count} files saved for Tal Yarkoni')
    return count

# ============================================================
# 4. DAN JURAFSKY
# ============================================================
def scrape_dan_jurafsky():
    print('\n' + '='*60)
    print('DAN JURAFSKY - Stanford')
    print('='*60)

    outdir = os.path.join(BASE, 'dan_jurafsky_source')
    count = 0

    # Check main page
    soup, _ = get_soup('https://web.stanford.edu/~jurafsky/')
    if soup:
        print('  Links on main page:')
        all_links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            text = a.get_text(strip=True)[:60]
            all_links.append((href, text))
            if any(k in href.lower() for k in ['blog', 'essay', 'writing', 'book', 'talk']):
                print(f'    {href} -> {text}')

        # Save main page
        text = extract_text(soup)
        if len(text) > 200:
            save_file(outdir, 'homepage.txt', text, 'Dan Jurafsky - Stanford Homepage')
            count += 1

    # Check for his book pages, essays, etc.
    subpages = [
        'https://web.stanford.edu/~jurafsky/slp3/',  # Speech and Language Processing textbook
        'https://web.stanford.edu/~jurafsky/linguisticsofFood.html',
        'https://web.stanford.edu/~jurafsky/foodreview.html',
    ]

    for url in subpages:
        page_soup, _ = get_soup(url)
        if page_soup:
            text = extract_text(page_soup)
            if len(text) > 200:
                slug = safe_filename(url.split('/')[-1].replace('.html', '') or 'slp3')
                save_file(outdir, f'{slug}.txt', text)
                count += 1
                print(f'  Saved: {slug}.txt ({len(text)} chars)')

    # Check his blog / Medium / other writing
    alt_urls = [
        'https://jurafsky.medium.com',
        'https://web.stanford.edu/~jurafsky/pubs.html',
    ]
    for url in alt_urls:
        page_soup, _ = get_soup(url)
        if page_soup:
            # If medium, get post links
            if 'medium.com' in url:
                post_links = set()
                for a in page_soup.find_all('a', href=True):
                    href = a['href']
                    if '/p/' in href or re.search(r'-[a-f0-9]{8,}', href):
                        full = urljoin(url, href)
                        post_links.add(full)
                print(f'  Found {len(post_links)} Medium posts')
                for post_url in list(post_links)[:20]:
                    p_soup, _ = get_soup(post_url)
                    if p_soup:
                        title_tag = p_soup.find('h1')
                        title = title_tag.get_text(strip=True) if title_tag else 'untitled'
                        text = extract_text(p_soup)
                        if len(text) > 300:
                            fname = safe_filename(title) + '.txt'
                            save_file(outdir, fname, text, title)
                            count += 1
                            print(f'  Saved: {fname}')
            else:
                text = extract_text(page_soup)
                if len(text) > 200:
                    slug = safe_filename(urlparse(url).path.replace('/', '_'))
                    save_file(outdir, f'{slug}.txt', text)
                    count += 1

    # Semantic Scholar for his most cited papers
    print(f'  Checking Semantic Scholar for paper abstracts...')
    try:
        api_url = 'https://api.semanticscholar.org/graph/v1/author/search?query=Dan+Jurafsky&fields=papers'
        r = requests.get(api_url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            data = r.json()
            if data.get('data'):
                author_id = data['data'][0].get('authorId')
                if author_id:
                    papers_url = f'https://api.semanticscholar.org/graph/v1/author/{author_id}/papers?fields=title,abstract,year,citationCount&limit=50'
                    r2 = requests.get(papers_url, headers=HEADERS, timeout=15)
                    if r2.status_code == 200:
                        papers = r2.json().get('data', [])
                        papers_with_abstract = [p for p in papers if p.get('abstract')]
                        papers_with_abstract.sort(key=lambda x: x.get('citationCount', 0), reverse=True)
                        print(f'  Found {len(papers_with_abstract)} papers with abstracts')
                        for p in papers_with_abstract[:30]:
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

    print(f'\n  TOTAL: {count} files saved for Dan Jurafsky')
    return count

# ============================================================
# 5. MYRA CHENG
# ============================================================
def scrape_myra_cheng():
    print('\n' + '='*60)
    print('MYRA CHENG - Stanford PhD')
    print('='*60)

    outdir = os.path.join(BASE, 'myra_cheng_source')
    count = 0

    soup, _ = get_soup('https://myracheng.github.io')
    if soup:
        # Check for blog, publications, posts
        all_links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            text = a.get_text(strip=True)[:60]
            all_links.append((href, text))

        print(f'  All links on site:')
        for href, text in all_links:
            print(f'    {href} -> {text}')

        # Save main page
        text = extract_text(soup)
        if len(text) > 200:
            save_file(outdir, 'homepage.txt', text, 'Myra Cheng - Homepage')
            count += 1

        # Follow any internal links
        for href, text in all_links:
            if href.startswith('/') or 'myracheng' in href:
                full_url = urljoin('https://myracheng.github.io/', href)
                if full_url != 'https://myracheng.github.io/' and full_url != 'https://myracheng.github.io':
                    page_soup, _ = get_soup(full_url)
                    if page_soup:
                        page_text = extract_text(page_soup)
                        if len(page_text) > 200:
                            slug = safe_filename(text or href.replace('/', '_'))
                            save_file(outdir, f'{slug}.txt', page_text, text)
                            count += 1
                            print(f'  Saved: {slug}.txt')

    # Semantic Scholar
    print(f'  Checking Semantic Scholar for paper abstracts...')
    try:
        api_url = 'https://api.semanticscholar.org/graph/v1/author/search?query=Myra+Cheng&fields=papers'
        r = requests.get(api_url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            data = r.json()
            # Find the right Myra Cheng (Stanford, NLP/AI)
            for author in data.get('data', [])[:5]:
                author_id = author.get('authorId')
                if author_id:
                    papers_url = f'https://api.semanticscholar.org/graph/v1/author/{author_id}/papers?fields=title,abstract,year,citationCount,venue&limit=30'
                    r2 = requests.get(papers_url, headers=HEADERS, timeout=15)
                    if r2.status_code == 200:
                        papers = r2.json().get('data', [])
                        # Check if this is the right person (NLP/AI papers)
                        nlp_papers = [p for p in papers if p.get('abstract') and
                                     any(k in (p.get('title','') + ' ' + p.get('abstract','')).lower()
                                         for k in ['language', 'nlp', 'bias', 'fairness', 'social', 'ai', 'model'])]
                        if len(nlp_papers) >= 2:
                            papers_with_abstract = [p for p in papers if p.get('abstract')]
                            papers_with_abstract.sort(key=lambda x: x.get('citationCount', 0), reverse=True)
                            print(f'  Found {len(papers_with_abstract)} papers with abstracts')
                            for p in papers_with_abstract[:20]:
                                title = p['title']
                                abstract = p['abstract']
                                year = p.get('year', 'unknown')
                                citations = p.get('citationCount', 0)
                                content = f"Year: {year}\nCitations: {citations}\n\nAbstract:\n{abstract}"
                                fname = safe_filename(title) + '.txt'
                                save_file(outdir, fname, content, title)
                                count += 1
                            break
    except Exception as e:
        print(f'  Semantic Scholar error: {e}')

    print(f'\n  TOTAL: {count} files saved for Myra Cheng')
    return count


# ============================================================
# RUN ALL
# ============================================================
if __name__ == '__main__':
    results = {}
    results['Maarten Sap'] = scrape_maarten_sap()
    results['Cristian Danescu-Niculescu-Mizil'] = scrape_cristian()
    results['Tal Yarkoni'] = scrape_tal_yarkoni()
    results['Dan Jurafsky'] = scrape_dan_jurafsky()
    results['Myra Cheng'] = scrape_myra_cheng()

    print('\n' + '='*60)
    print('SUMMARY')
    print('='*60)
    for name, count in results.items():
        print(f'  {name}: {count} files')
    print(f'  TOTAL: {sum(results.values())} files')
