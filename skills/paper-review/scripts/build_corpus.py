#!/usr/bin/env python3
"""Download arXiv PDFs for every entry in an ADS BibTeX export.

PDFs land in <directory-of-bibfile>/papers_pdf/<FirstAuthor><Year>.pdf and are
cached: re-runs skip anything already on disk. Prints one JSON line per entry
to stdout with bibkey, first_author, year, journal, title, eprint, pdf_path,
pdf_status.
"""

import argparse
import json
import sys

from _lib import build_citation_index, ensure_corpus


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bibfile', help='Path to an ADS BibTeX export (.bib)')
    parser.add_argument('--keys', default=None,
                        help='Comma-separated bibkeys to process (default: all)')
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--jitter', type=float, default=2.0)
    args = parser.parse_args()

    keys = [k.strip() for k in args.keys.split(',')] if args.keys else None
    cache_dir, entries = ensure_corpus(
        args.bibfile, keys=keys, workers=args.workers, jitter=args.jitter, log=sys.stderr,
    )
    print(f"[paper-review] cache: {cache_dir}", file=sys.stderr)
    print(f"[paper-review] {len(entries)} entries processed", file=sys.stderr)
    citation_index = build_citation_index(entries, cache_dir, log=sys.stderr)
    citation_count = sum(len(record['citations']) for record in citation_index.values())
    print(f"[paper-review] {citation_count} citation-sentence pairs cached", file=sys.stderr)
    for entry in entries:
        print(json.dumps(entry, ensure_ascii=False))


if __name__ == '__main__':
    main()
