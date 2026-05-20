# NMonsalvesSkill

Claude Code plugin with personal skills for astrophysics research workflows.

## Skills

### `paper-review`

Build and analyse a corpus of arXiv papers from a BibTeX (`.bib`) export.
Downloads PDFs (cached, deduped), extracts each paper's Introduction into a
shared citation index, and runs analyses on it (first-line tables, citation
frequency rankings, citation contexts).

**Input.** A `.bib` file exported from the SAO/NASA Astrophysics Data System
(ADS). From any ADS search result list use *Export → BibTeX*. The skill reads
the `eprint` field of each entry (the arXiv ID) to download PDFs, so entries
without an arXiv preprint are skipped. Other BibTeX dialects may work as long
as they expose an `eprint` field.

See `skills/paper-review/SKILL.md` for the full workflow and analysis catalog.

## Installation

Clone the repo into your Claude Code skills directory:

```bash
git clone <repo-url> ~/Claude_plugins/NMonsalvesSkill
ln -s ~/Claude_plugins/NMonsalvesSkill/skills/paper-review ~/.claude/skills/paper-review
```

Skills are auto-discovered the next time Claude Code starts.

## External dependencies

- `python3` (3.8+)
- `pdftotext` (from poppler — install with `brew install poppler` on macOS)

No pip dependencies; everything uses the standard library.

## Adding a new skill

Drop a new folder under `skills/`, e.g. `skills/<new-skill>/SKILL.md` with the
standard frontmatter (`name`, `description`). The plugin manifest does not
need to list it — directory layout is the source of truth.
