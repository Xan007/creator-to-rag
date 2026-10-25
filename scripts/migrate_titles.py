import re
import sqlite3
import os

BOILERPLATE_PATTERNS = [
    r'^[¡!\s]*comenta\s+(la\s+palabra\s+)?[\w\d_\-]+\s+(y\s+.*?(?:!|\.|\n|$)|si\s+quieres.*?(?:!|\.|\n|$))',
    r'^[¡!\s]*si\s+quieres\s+(que\s+te\s+asesore|mi\s+asesor[ií]a).*?(?:!|\.|\n|$)',
    r'^[¡!\s]*link\s+en\s+mi\s+biograf[ií]a.*?(?:!|\.|\n|$)',
]

def clean_title(raw: str) -> str:
    title = raw.strip().strip('"\'').rstrip('.').lstrip('#* ')
    return title[:120] if title else ''

def extract_best_title(title: str, k: str, desc: str) -> str:
    if k:
        m = re.search(r'##\s*Topic\s*[:\n\- ]*([^\n#]+)', k, re.IGNORECASE)
        if m:
            clean = clean_title(m.group(1))
            if clean:
                return clean
    if title and not any(re.search(p, title, re.IGNORECASE) for p in BOILERPLATE_PATTERNS):
        return clean_title(title)
    
    raw = desc or title or ''
    lines = [l.strip() for l in raw.splitlines() if l.strip() and l.strip() not in ('-', '—', '..', '...', '.')]
    for line in lines:
        cleaned = line
        for p in BOILERPLATE_PATTERNS:
            cleaned = re.sub(p, '', cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r'#\w+', '', cleaned).strip()
        cleaned = re.sub(r'[\U00010000-\U0010ffff]', '', cleaned).strip()
        if len(cleaned) >= 10:
            return clean_title(cleaned)
    return clean_title(title or desc or 'Reel Content')

def run_migration():
    db_path = os.path.expanduser('~/.crag/crag.db')
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.execute('SELECT id, title, extracted_knowledge, description FROM posts')
    posts = c.fetchall()
    
    updated_posts = 0
    post_title_map = {}
    for pid, title, k, desc in posts:
        new_title = extract_best_title(title or '', k or '', desc or '')
        if new_title and new_title != title:
            c.execute('UPDATE posts SET title = ? WHERE id = ?', (new_title, pid))
            updated_posts += 1
            post_title_map[pid] = new_title
        elif new_title:
            post_title_map[pid] = new_title

    # Also update sources where shortcode or url matches
    c.execute('SELECT id, url, title FROM sources')
    sources = c.fetchall()
    updated_sources = 0
    for sid, url, stitle in sources:
        # shortcode is after colon or from url
        shortcode = sid.split(':')[-1]
        best_title = post_title_map.get(shortcode)
        if best_title and best_title != stitle:
            c.execute('UPDATE sources SET title = ? WHERE id = ?', (best_title, sid))
            updated_sources += 1

    conn.commit()
    conn.close()
    print(f"Migration completed successfully:")
    print(f" - Updated {updated_posts} posts in crag.db")
    print(f" - Updated {updated_sources} sources in crag.db")

if __name__ == '__main__':
    run_migration()

