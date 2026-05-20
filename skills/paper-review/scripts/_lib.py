"""Shared helpers for the paper-review skill.

Single source of truth for: BibTeX parsing, PDF filename assignment + cache
indexing, arXiv download, and Introduction extraction. Analyses import from
here so changes propagate everywhere.
"""

import json
import random
import re
import subprocess
import time
import unicodedata
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


INDEX_FILE = "_index.json"
CITATIONS_FILE = "_citations.json"
CACHE_DIRNAME = "papers_pdf"


def cache_dir_for(bibfile):
    """Return <directory-of-bibfile>/papers_pdf/, creating it if needed."""
    cache = Path(bibfile).resolve().parent / CACHE_DIRNAME
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def strip_latex(text):
    accents = {'"': '̈', "'": '́', '`': '̀', '^': '̂',
               '~': '̃', '=': '̄', '.': '̇'}
    for command, combining in accents.items():
        text = re.sub(
            rf'\\{re.escape(command)}\s*\{{?([a-zA-Z])\}}?',
            lambda match: match.group(1) + combining,
            text,
        )
    text = re.sub(r'\\[vu]\s*\{?([a-zA-Z])\}?', r'\1', text)
    text = re.sub(r'\\textcommabelow\s*\{?([a-zA-Z])\}?', r'\1', text)
    text = re.sub(r'\\[a-zA-Z]+', '', text)
    text = text.replace('{', '').replace('}', '').strip()
    return unicodedata.normalize('NFC', text)


def slugify_author(name):
    name = re.sub(r'\\[a-zA-Z]+\s*\{([a-zA-Z])\}', r'\1', name)
    name = re.sub(r"\\[\"'`^~=.uvHc]\s*\{?([a-zA-Z])\}?", r'\1', name)
    name = re.sub(r'\\[a-zA-Z]+', '', name)
    name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('ascii')
    name = re.sub(r'[^A-Za-z]', '', name)
    return name or 'Unknown'


def parse_bibtex(bib_path):
    with open(bib_path) as file_handle:
        content = file_handle.read()
    raw_entries = re.split(r'\n(?=@)', content.strip())
    parsed = []
    for raw in raw_entries:
        bibkey_match = re.search(r'@\w+\{(\S+),', raw)
        if not bibkey_match:
            continue

        def field(name):
            match = re.search(rf'\b{name}\s*=\s*"?\{{', raw, re.IGNORECASE)
            if not match:
                return None
            start = match.end()
            depth = 1
            cursor = start
            while cursor < len(raw) and depth > 0:
                if raw[cursor] == '{':
                    depth += 1
                elif raw[cursor] == '}':
                    depth -= 1
                cursor += 1
            if depth != 0:
                return None
            return raw[start:cursor - 1].replace('\n', ' ').strip()

        year_match = re.search(r'year\s*=\s*\{?(\d{4})\}?', raw)
        eprint_match = re.search(r'eprint\s*=\s*\{([^}]+)\}', raw)
        author_field = field('author') or ''
        first_author_raw = re.split(r' and ', author_field, flags=re.IGNORECASE)[0]
        first_author = strip_latex(first_author_raw.split(',')[0])
        parsed.append({
            'bibkey': bibkey_match.group(1),
            'first_author': first_author,
            'year': year_match.group(1) if year_match else None,
            'journal': field('journal'),
            'title': field('title'),
            'eprint': eprint_match.group(1) if eprint_match else None,
        })
    return parsed


def assign_filenames(entries, cache_dir):
    """Map each bibkey to a stable '{Author}{Year}[suffix].pdf' filename.

    Persists the mapping in _index.json so names stay stable across runs.
    Disambiguates collisions (same author+year, different paper) with letter
    suffixes assigned in bibkey order.
    """
    index_path = cache_dir / INDEX_FILE
    index = {}
    if index_path.exists():
        index = json.loads(index_path.read_text())
    used_names = set(index.values())

    by_author_year = {}
    for entry in entries:
        if entry['bibkey'] in index:
            continue
        key = (slugify_author(entry['first_author']), entry['year'] or 'NA')
        by_author_year.setdefault(key, []).append(entry['bibkey'])

    for (author, year), bibkeys in by_author_year.items():
        bibkeys.sort()
        base = f"{author}{year}"
        if len(bibkeys) == 1 and f"{base}.pdf" not in used_names:
            candidates = [f"{base}.pdf"]
        else:
            candidates = []
            suffix = 0
            while len(candidates) < len(bibkeys):
                name = f"{base}{chr(ord('a') + suffix)}.pdf"
                if name not in used_names:
                    candidates.append(name)
                suffix += 1
        for bibkey, name in zip(bibkeys, candidates):
            index[bibkey] = name
            used_names.add(name)

    index_path.write_text(json.dumps(index, indent=2, sort_keys=True))
    return index


def download_pdf(arxiv_id, dest):
    """Download <arxiv_id> PDF to dest. Returns True if a network call was made."""
    if dest.exists() and dest.stat().st_size > 1000:
        return False
    url = f"https://arxiv.org/pdf/{arxiv_id}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (paper-review skill)"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        dest.write_bytes(response.read())
    return True


def ensure_corpus(bibfile, keys=None, workers=3, jitter=2.0, log=None):
    """Parse bib, dedupe filenames, download anything missing.

    Returns (cache_dir, entries) where each entry dict has an added
    'pdf_path' (Path) and 'pdf_status' ('ok' | 'missing-eprint' | 'failed: ...').
    """
    cache_dir = cache_dir_for(bibfile)
    entries = parse_bibtex(bibfile)
    if keys:
        wanted = {k.strip() for k in keys}
        entries = [entry for entry in entries if entry['bibkey'] in wanted]
    filenames = assign_filenames(entries, cache_dir)

    def fetch(entry):
        filename = filenames.get(entry['bibkey'])
        if not filename:
            return entry, None, 'missing-filename'
        pdf_path = cache_dir / filename
        if not entry['eprint']:
            return entry, pdf_path, 'missing-eprint'
        try:
            if not pdf_path.exists() or pdf_path.stat().st_size <= 1000:
                time.sleep(random.uniform(0, jitter))
                download_pdf(entry['eprint'], pdf_path)
            return entry, pdf_path, 'ok'
        except Exception as exc:
            return entry, pdf_path, f'failed: {exc}'

    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(fetch, entry) for entry in entries]
        for future in as_completed(futures):
            entry, pdf_path, status = future.result()
            entry['pdf_path'] = str(pdf_path) if pdf_path else None
            entry['pdf_status'] = status
            results.append(entry)
            if log and status != 'ok':
                print(f"[paper-review] {status}: {entry['bibkey']}", file=log)

    results.sort(key=lambda entry: entry['bibkey'])
    return cache_dir, results


def extract_introduction(pdf_path, max_chars=4000):
    """Return the Introduction section text, or None if not found."""
    result = subprocess.run(
        ["pdftotext", str(pdf_path), "-"],
        capture_output=True,
        text=True,
    )
    text = result.stdout
    match = re.search(r'\bINTRODUCTION\b', text, re.IGNORECASE)
    if not match:
        return None
    intro = text[match.end():]
    next_section = re.search(r'\n\s*(?:\d+\.?\s+)[A-Z][A-Z ]{3,}', intro)
    if next_section:
        intro = intro[:next_section.start()]
    lines = [line.strip() for line in intro.strip().splitlines() if line.strip()]
    return ' '.join(lines)[:max_chars]


CITATION_PATTERN = re.compile(
    r'\b'
    r'(?P<author>(?:[A-Z][A-Za-z\-À-ſ]+'
    r'(?:\s+et\s+al\.?)?'
    r'(?:\s*(?:&|and)\s*[A-Z][A-Za-z\-À-ſ]+)?))'
    r'\s*\(?(?P<year>\b(?:19|20)\d{2})(?P<suffix>[a-z]?)\)?'
)


def iter_citations(text):
    """Yield (author_token, year, suffix, match_span) for each citation-like hit.

    Pragmatic regex — catches `(Smith 2017)`, `Smith (2017)`, `Smith et al. 2018a`,
    `Smith & Jones 2019`. Has false positives (sentence-initial proper nouns
    near a 4-digit number) — good enough for ranking, not for ground truth.
    """
    for match in CITATION_PATTERN.finditer(text):
        yield (
            re.sub(r'\s+', ' ', match.group('author')).strip(),
            match.group('year'),
            match.group('suffix'),
            match.span(),
        )


def build_citation_index(entries, cache_dir, log=None):
    """Extract intro + per-citation sentence for every paper, persist to disk.

    Reads <cache_dir>/_citations.json if present and only processes bibkeys
    that aren't cached yet (or whose PDF status changed). Returns the full
    index as a dict keyed by bibkey.

    Each entry: {
        'intro': '<full introduction text>' | None,
        'citations': [
            {'author': str, 'year': str, 'suffix': str,
             'canonical': str, 'sentence': str},
            ...
        ],
        'status': 'ok' | 'no-pdf' | 'no-intro',
    }
    """
    cache_path = cache_dir / CITATIONS_FILE
    index = {}
    if cache_path.exists():
        index = json.loads(cache_path.read_text())

    changed = False
    for entry in entries:
        bibkey = entry['bibkey']
        if bibkey in index and index[bibkey].get('status') == 'ok':
            continue
        if entry['pdf_status'] != 'ok':
            index[bibkey] = {'intro': None, 'citations': [], 'status': 'no-pdf'}
            changed = True
            continue
        intro = extract_introduction(entry['pdf_path'])
        if intro is None:
            index[bibkey] = {'intro': None, 'citations': [], 'status': 'no-intro'}
            changed = True
            if log:
                print(f"[paper-review] no INTRODUCTION found: {bibkey}", file=log)
            continue
        citations = []
        for sentence in split_sentences(intro):
            for author_token, year, suffix, _ in iter_citations(sentence):
                citations.append({
                    'author': author_token,
                    'year': year,
                    'suffix': suffix,
                    'canonical': f"{normalise_author(author_token)}{year}",
                    'sentence': sentence,
                })
        index[bibkey] = {'intro': intro, 'citations': citations, 'status': 'ok'}
        changed = True

    if changed:
        cache_path.write_text(json.dumps(index, ensure_ascii=False, indent=2))
    return index


def known_references(entries):
    """Build the set of canonical Author+Year keys present in the bibfile.

    Used by analyses to filter out citation-regex false positives — only
    citations matching a paper actually in the corpus are kept.
    """
    references = set()
    for entry in entries:
        if not entry.get('year'):
            continue
        author_slug = slugify_author(entry['first_author'])
        if author_slug and author_slug != 'Unknown':
            references.add(f"{author_slug}{entry['year']}")
    return references


def normalise_author(author_token):
    """'Smith et al.' / 'Smith & Jones' / 'Smith' → 'Smith' (slugified)."""
    first = re.split(r'\s+(?:et\s+al\.?|&|and)\s*', author_token, maxsplit=1)[0]
    return slugify_author(first)


def split_sentences(text):
    """Split a paragraph into sentences, naive but citation-safe.

    Splits on `. ` / `? ` / `! ` followed by a capital letter, but avoids
    splitting inside `(Author et al. 2017)` style parens and on common
    abbreviations (e.g., et al.).
    """
    text = re.sub(r'\s+', ' ', text)
    protected = re.sub(r'et al\.', 'et al<DOT>', text)
    protected = re.sub(r'\b([A-Z])\.(?=\s+[A-Z])', r'\1<DOT>', protected)
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z\(])', protected)
    return [part.replace('<DOT>', '.').strip() for part in parts if part.strip()]
