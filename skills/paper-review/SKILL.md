---
name: paper-review
description: Build and analyse a corpus of arXiv papers from an ADS BibTeX (.bib) export. Always downloads the PDFs first (cached, deduped per bibkey) into <bibfile-dir>/papers_pdf/, extracts each paper's Introduction once into a citation index, and then runs one of several analyses on it. Use whenever the user supplies a .bib file and asks for first-line summaries, citation frequency rankings, citation context comparisons, or any other intro-level analysis across multiple papers.
---

# paper-review

Works in three layers:

1. **PDF corpus** (`papers_pdf/`): every analysis ensures every paper in the
   `.bib` has a PDF, named `{FirstAuthor}{Year}[suffix].pdf`. The bibkey →
   filename mapping is persisted in `_index.json` so names stay stable.
2. **Citation index** (`papers_pdf/_citations.json`): per paper, the full
   Introduction text plus every detected citation paired with the sentence
   that contains it. Built once, reused by every analysis.
3. **Analyses**: each script reads the citation index, never re-parses PDFs.

All caches live next to the `.bib` file, so each project has its own corpus.

## Workflow

When the user supplies a `.bib`:

- To just download + index: `python3 scripts/build_corpus.py <bibfile.bib>`
- For analyses: pick the script that matches the question (catalog below).
  Each one calls the corpus + index step internally — never run them twice.
- If the user didn't specify which analysis, list the catalog options and ask.

All scripts accept `--keys K1,K2,...` to restrict to a subset of bibkeys.

## Citation index schema

`papers_pdf/_citations.json` is the single source of truth for analyses:

```json
{
  "<bibkey>": {
    "intro": "<full introduction text or null>",
    "citations": [
      {"author": "Abbott et al.", "year": "2017", "suffix": "a",
       "canonical": "Abbott2017",
       "sentence": "The full sentence containing this citation."}
    ],
    "status": "ok" | "no-pdf" | "no-intro"
  }
}
```

The same sentence appears once per citation it contains (a sentence with three
citations produces three records). Canonical keys are `Slugified-Surname +
Year` (e.g. `OConnor2025`, `AnguloValdez2026`).

## Analysis catalog

### `analyses/first_line.py` — Primera línea de la introducción

Emits the cached intro of each paper. Claude formats a markdown table from
the JSON output, keeping the first sentence(s) with inline citations:

| # | Paper | Primera línea de la introducción (con citas) |
|---|-------|----------------------------------------------|
| N | Author et al. YYYY, *Journal* | *"First sentence(s) with (Author et al. YEAR) citations."* |

### `analyses/citation_frequency.py` — Citas más frecuentes

Ranks references by how many introductions cite them. The `.bib` defines the
**citing** corpus, not the allowed references — every citation found in any
intro is counted, whether or not it appears in the bib.

Defaults: `--min-count 2` (drops single-occurrence false positives from the
regex). Pass `--filter-to-bib` to restrict the ranking to references whose
Author+Year is also in the .bib (rare, only useful for citation graphs within
the bib itself).

### `analyses/citation_contexts.py` — Frases con que se cita cada paper

For each reference cited by ≥2 distinct papers, lists every sentence across
the corpus that cites it. Reveals how different authors frame the same work.
Pass `--ref Smith2017` to focus on one reference, or `--filter-to-bib` to
restrict to bib-internal references.

## Adding a new analysis

Drop a new script in `scripts/analyses/`. It should:

1. Call `ensure_corpus(bibfile, keys=..., log=sys.stderr)` then
   `build_citation_index(entries, cache_dir, log=sys.stderr)` from `_lib`.
   Both are idempotent and cheap when the cache is warm.
2. Iterate over the returned index; do **not** re-extract intros or re-run
   the citation regex — the per-citation sentences are already there.
3. Emit JSON to stdout. Claude formats user-facing output from there.

Keep `_lib.py` as the single source of truth for parsing, downloading,
indexing, and citation detection.

## Caveats

- Entries without an `eprint` (arXiv ID) field in the bib are skipped — no
  PDF to fetch. `pdf_status` reports the reason per entry.
- The citation regex in `_lib.iter_citations` is pragmatic, not perfect.
  It matches `(Author Year)`, `Author (Year)`, `Author et al. Year`,
  `Author & Other Year`. False positives exist (proper nouns near 4-digit
  numbers); they typically have count=1, so `--min-count 2` filters them.
- Intro extraction relies on the literal word `INTRODUCTION` appearing as a
  heading. Papers using unusual section structure return `status: no-intro`.
- The sentence splitter (`_lib.split_sentences`) protects common patterns
  (`et al.`, single-letter initials like `H.`, `R.`) but pdftotext output
  from heavily-formatted PDFs can still produce noisy sentence boundaries.
