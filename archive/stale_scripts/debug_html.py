import requests, re
r = requests.get('https://a16z.com/the-cost-of-cloud-a-trillion-dollar-paradox/', headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
t = r.text
print(f"Page length: {len(t)}")
for marker in ['entry-content', 'article-content', 'post-body', 'wp-block', '<article', 'id="content"']:
    idx = t.find(marker)
    if idx >= 0:
        print(f'Found "{marker}" at position {idx}')
for word in ['repatriation', 'infrastructure bill', 'gross margin', 'cloud spend']:
    idx = t.lower().find(word)
    if idx >= 0:
        print(f'Found "{word}" at position {idx}')
        print(t[max(0,idx-100):idx+300])
        print("---")

# Also check greylock
print("\n=== GREYLOCK ===")
r2 = requests.get('https://greylock.com/greymatter/the-new-new-moats/', headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
t2 = r2.text
print(f"Page length: {len(t2)}")
for marker in ['entry-content', 'article-content', 'wp-block', '<article', '__NEXT_DATA__', 'systems of intelligence']:
    idx = t2.lower().find(marker.lower())
    if idx >= 0:
        print(f'Found "{marker}" at position {idx}')
        if marker == 'systems of intelligence':
            print(t2[max(0,idx-100):idx+300])
