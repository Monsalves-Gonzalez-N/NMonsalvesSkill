#!/usr/bin/env python3
"""Rank references by how often they are cited across the introductions.

Reads from the cached citation index (papers_pdf/_citations.json) — the
intros and per-citation sentences are extracted once by build_corpus.py and
reused by every analysis.

Counts every citation-shaped string in the intros (the bib defines the citing
corpus, not the allowed references). Use --min-count to suppress regex noise,
or --filter-to-bib to restrict the ranking to references whose Author+Year
also appears in the bib (rarely what you want for a literature review).

Output: JSON to stdout, sorted by count descending:
  {
    "Smith2017": {"count": 12, "displays": [...], "citing_papers": [...]},
    ...
  }
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _lib import build_citation_index, ensure_corpus, known_references  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bibfile')
    parser.add_argument('--keys', default=None)
    parser.add_argument('--min-count', type=int, default=2,
                        help='Drop references with fewer hits (default: 2)')
    parser.add_argument('--filter-to-bib', action='store_true',
                        help='Restrict ranking to references also present in the .bib')
    args = parser.parse_args()

    keys = [k.strip() for k in args.keys.split(',')] if args.keys else None
    cache_dir, entries = ensure_corpus(args.bibfile, keys=keys, log=sys.stderr)
    citation_index = build_citation_index(entries, cache_dir, log=sys.stderr)
    allowed_references = known_references(entries) if args.filter_to_bib else None

    aggregated = defaultdict(lambda: {'count': 0, 'displays': set(), 'citing_papers': set()})
    for bibkey, record in citation_index.items():
        if record['status'] != 'ok':
            continue
        seen_in_this_paper = set()
        for citation in record['citations']:
            canonical = citation['canonical']
            if allowed_references is not None and canonical not in allowed_references:
                continue
            display = f"{citation['author']} {citation['year']}{citation['suffix']}".strip()
            aggregated[canonical]['displays'].add(display)
            seen_in_this_paper.add(canonical)
        for canonical in seen_in_this_paper:
            aggregated[canonical]['count'] += 1
            aggregated[canonical]['citing_papers'].add(bibkey)

    output = {}
    for canonical, value in aggregated.items():
        if value['count'] < args.min_count:
            continue
        output[canonical] = {
            'count': value['count'],
            'displays': sorted(value['displays']),
            'citing_papers': sorted(value['citing_papers']),
        }
    ranked = dict(sorted(output.items(), key=lambda item: -item[1]['count']))
    print(json.dumps(ranked, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
