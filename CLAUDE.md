# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**versiref-bible** stores a Bible in an SQLite database and serves its verses by reference or by full-text search.
It extends the [versiref](https://github.com/fiapps/versiref) ecosystem and is a sibling of `versiref-search`, sharing its conventions.

- **Package name**: `versiref.bible` (namespace package)
- **PyPI name**: `versiref-bible`
- **Purpose**: Build an SQLite Bible from a CCAT-format text file, then retrieve verse ranges by reference and search verse text with FTS5.
- **Intended consumer**: an LLM. Output is compact plain text, one verse per line as `reference<TAB>text`.

## Development Commands

### Package Management
```sh
# Install dependencies and sync environment
uv sync

# Add a new dependency
uv add <package-name>

# Run the CLI in the project environment
uv run versiref-bible --help
```

### Testing, Type Checking, Linting
```sh
uv run pytest        # tests live in tests/
uv run mypy src      # type checking
uv run ruff check    # linting (ruff pydocstyle rules are enabled)
```

## Architecture

### Core Data Model

Each Bible is a single SQLite database (`database.py`) with three tables:

1. **verses**: one row per Bible verse.
   - `verse_key`: integer primary key, the `BBCCCVVV` key computed under the database's versification; it doubles as the FTS5 rowid.
   - `book_id`: Paratext book ID (e.g. `JHN`).
   - `chapter`, `verse`: integers.
   - `text`: the verse text, stored verbatim.

2. **verses_fts**: an FTS5 external-content virtual table over `verses.text`.
   - `content='verses'`, `content_rowid='verse_key'`.
   - Built once after a bulk insert with `INSERT INTO verses_fts(verses_fts) VALUES('rebuild')` — there are no sync triggers because a build is one-shot.

3. **metadata**: key-value pairs (`title`, `versification`, `book_style`, `source`, `verse_count`, `built_at`, `schema_version`).

### Verse Encoding

Verse keys are integers of the form `BBCCCVVV`:
- BB: book number according to the versification's book order.
- CCC: chapter (001-999).
- VVV: verse (001-999).

Example: John 3:16 in `eng` → `43003016`.

Keys come from versiref, not from hand-rolled arithmetic.
The build side computes them with `SimpleBibleRef.for_range(book_id, chapter, verse).range_keys(versification)`, and the show side gets the matching integers from `BibleRef.range_keys()` after parsing a reference.
Because both use the same versification, the keys line up, which is what makes range lookups correct.

### Range Lookup

`show` resolves a reference to one `(start_key, end_key)` pair per single-book range (`BibleRef.range_keys()`), then selects `verses` rows with `verse_key BETWEEN start AND end`.
Each pair stays within one book, so the `BETWEEN` is always safe, including across chapter boundaries.
`--in` on `search` reuses the same mechanism to scope a full-text query.

### Build Gating (warn-and-skip)

`build` (`builder.py`) never aborts on unusable lines; it skips and tallies them in `BuildStats`.
It maps the file's book abbreviation to a book ID via `RefStyle.named(book_style).recognized_names` — it does **not** call `RefParser.parse` on data lines.
A line is skipped when:
- the abbreviation is not recognized (e.g. the Sirach prologue `Sip`, which is not a canonical book), or
- the book is not in the chosen versification.

The off-scheme check gates on `range_keys` returning an **empty** list (book absent from the versification), **not** on `SimpleBibleRef.is_valid`.
This is deliberate: `is_valid` also rejects a verse whose number exceeds the bundled versification's chapter length, which would wrongly drop legitimate verses when the source text and the bundled versification disagree on verse counts.
`range_keys` still yields a usable key in that case, so the verse is preserved.

A future versiref `BibleRef`-overlap/inclusion feature could let off-scheme verses be stored and shown instead of skipped; the build gate is the single place to revisit if that lands.

### Source Modules (`src/versiref/bible/`)

- `models.py`: `Verse` and `BuildStats` data classes.
- `database.py`: schema and the `Database` wrapper (insert, rebuild FTS, range and FTS queries, counts).
- `builder.py`: `build_database` — parse the `.cat` file, map abbreviations, compute keys, skip-and-tally, write the DB.
- `reader.py`: `show_verses`, `search_verses`, and the `format_verse` plain-text formatter.
- `cli.py`: Click CLI with the `build`, `show`, `search`, and `info` commands.
- `__init__.py`: public API exports.

Tests in `tests/` build a small in-memory fixture Bible and exercise build/show/search end to end.

## Input Format

Input is CCAT-format `.cat` text, one verse per line: `Abbrev C:V text`.
The abbreviation is a BibleWorks-style book name (`en-bibleworks`) by default.
CCAT footnotes and inline formatting are treated as **plain text** for now; parsing them is future work.
The sample CEI 2008 file is `cp1252`, not UTF-8, so `build` accepts `--encoding`.

Sample `.cat` Bibles live in `reference/samples/` (gitignored): a Brenton LXX (Old Testament and Apocrypha, **no New Testament**), a KJV (Strong's numbers kept as plain text), and an Italian CEI 2008.

## Key Dependencies

- **versiref** (>=0.5.1): parsing references, versification, and verse keys. First-party (same maintainer as this package).
- **click** (>=8.1.0): CLI framework.
- **Python** (>=3.10).
- **SQLite** (with FTS5): built into Python.

## Design Principles

1. **One database per Bible**: portable and easy to regenerate.
2. **Per-verse storage**: each verse is one row, so search is naturally verse-scoped.
3. **LLM-first output**: plain text, one verse per line as `reference<TAB>text`; no JSON, which costs tokens without helping a Claude reader.
4. **Versification-aware keys**: each database records its versification and keys every verse against it; `show` parses in the database's versification by default, with `--from-versification` to map a foreign reference in.
5. **Tolerant builds**: unusable lines are warned-and-skipped, never fatal.

## Build System

This project uses `uv_build` as the build backend (see `pyproject.toml`), configured as a namespace package under `versiref.bible` (no `src/versiref/__init__.py`).

Key configuration:
- Build backend: `uv_build>=0.9.28,<0.10.0`
- Module name: `versiref.bible`

## Markdown Style

When writing or editing Markdown (docs, README, this file):
- One sentence per line; do not hard-wrap at a column width.
- Always specify a language on fenced code blocks (e.g. ```sh, ```python).

## Important Files

- `docs/`: user-facing documentation (tracked in git): `building.md`, `querying.md`.
- `reference/`: the `versiref` API docs and sample `.cat` Bibles (gitignored; for AI-agent use).
- `pyproject.toml`: package configuration and dependencies; sole source of the version number.
- `src/versiref/bible/__init__.py`: public API exports.
- `uv.lock`: lock file for reproducible dependency resolution.
