#!/usr/bin/env python3
"""For each cited reference, collect the sentences across the corpus that cite it.

Reads from the cached citation index (papers_pdf/_citations.json). For each
canonical Author+Year cited in at least one intro, gathers every sentence
across the corpus that mentions it. Reveals how differently authors describe
the same work.

Output: JSON to stdout:
  {
    "Smith2017": [
       {"citing_bibkey": "...", "sentence": "..."},
       ...
    ],
    ...
  }

Defaults: references with ≥2 distinct citing papers. Use --ref Smith2017 to
focus on one reference, or --filter-to-bib to restrict to references also in
the .bib.
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
    parser.add_argument('--ref', default=None,
                        help='Restrict output to a single canonical key, e.g. "Smith2017"')
    parser.add_argument('--min-count', type=int, default=2)
    parser.add_argument('--filter-to-bib', action='store_true')
    args = parser.parse_args()

    keys = [k.strip() for k in args.keys.split(',')] if args.keys else None
    cache_dir, entries = ensure_corpus(args.bibfile, keys=keys, log=sys.stderr)
    citation_index = build_citation_index(entries, cache_dir, log=sys.stderr)
    allowed_references = known_references(entries) if args.filter_to_bib else None

    contexts = defaultdict(list)
    seen_pairs = set()
    for bibkey, record in citation_index.items():
        if record['status'] != 'ok':
            continue
        for citation in record['citations']:
            canonical = citation['canonical']
            if allowed_references is not None and canonical not in allowed_references:
                continue
            pair = (canonical, bibkey, citation['sentence'])
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            contexts[canonical].append({
                'citing_bibkey': bibkey,
                'sentence': citation['sentence'],
            })

    if args.ref:
        output = {args.ref: contexts.get(args.ref, [])}
    else:
        output = {
            canonical: items
            for canonical, items in contexts.items()
            if len({item['citing_bibkey'] for item in items}) >= args.min_count
        }
        output = dict(sorted(output.items(), key=lambda item: -len(item[1])))

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
