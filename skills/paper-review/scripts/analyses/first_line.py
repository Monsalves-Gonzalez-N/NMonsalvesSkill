#!/usr/bin/env python3
"""Emit the cached Introduction of each paper in a BibTeX file.

Reads from papers_pdf/_citations.json (populated by build_corpus.py). Prints
one JSON line per entry with bibkey, first_author, year, journal, title,
intro. Claude formats the markdown table from these JSON lines — keeping the
first sentence(s) and preserving inline citations exactly as written.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _lib import build_citation_index, ensure_corpus  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bibfile')
    parser.add_argument('--keys', default=None)
    args = parser.parse_args()

    keys = [k.strip() for k in args.keys.split(',')] if args.keys else None
    cache_dir, entries = ensure_corpus(args.bibfile, keys=keys, log=sys.stderr)
    citation_index = build_citation_index(entries, cache_dir, log=sys.stderr)

    for entry in entries:
        record = {key: entry[key] for key in ('bibkey', 'first_author', 'year', 'journal', 'title')}
        cached = citation_index.get(entry['bibkey'], {})
        if cached.get('status') == 'ok':
            record['intro'] = cached['intro']
        else:
            record['error'] = cached.get('status') or entry['pdf_status']
        print(json.dumps(record, ensure_ascii=False))


if __name__ == '__main__':
    main()
