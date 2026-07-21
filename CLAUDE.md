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

### Dependency auditing

Supply-chain checks run when upgrading dependencies and before tagging a release.
See `SECURITY.md` for the threat model and the full procedure; the key commands are:

```sh
# Upgrade third-party deps with a 7-day cooldown (BSD/macOS date)
uv lock --upgrade --exclude-newer "$(date -u -v-7d +%Y-%m-%dT%H:%M:%SZ)"

# First-party exception: pick up any newer versiref release
uv lock --upgrade-package versiref

# Scan the locked tree for known advisories
uv export --format requirements-txt --no-emit-project | uvx pip-audit -r /dev/stdin --disable-pip --require-hashes
```

A CVE on a current dependency overrides the cooldown — upgrade immediately.

## Architecture

### Core Data Model

Each Bible is a single SQLite database (`database.py`) with three tables:

1. **verses**: one row per Bible verse.
   - `verse_key`: integer primary key, the `BBCCCVVVSS` key computed under the database's versification; it doubles as the FTS5 rowid.
   - `book_id`: Paratext book ID (e.g. `JHN`).
   - `chapter`, `verse`: integers.
   - `text`: the verse text, stored verbatim.

2. **verses_fts**: an FTS5 external-content virtual table over `verses.text`.
   - `content='verses'`, `content_rowid='verse_key'`.
   - Built once after a bulk insert with `INSERT INTO verses_fts(verses_fts) VALUES('rebuild')` — there are no sync triggers because a build is one-shot.

3. **metadata**: key-value pairs (`format`, `title`, `versification`, `source`, `verse_count`, `built_at`, `schema_version`).

### Verse Encoding

Verse keys are integers of the form `BBCCCVVVSS`:

- BB: book number according to the versification's book order.
- CCC: chapter (001-999).
- VVV: verse (001-999).
- SS: subverse ordinal (00 for the base verse; nonzero for an inserted verse such as the Greek additions to Esther, ESG 4:17a-z, keyed after their base verse). From `Versification.partial_ordinal`.

Example: John 3:16 in `eng` → `4300301600`.

Keys come from versiref, not from hand-rolled arithmetic (versiref 0.10.0 widened the key from `BBCCCVVV` to `BBCCCVVVSS`; the package treats keys as opaque, so only stored width changed).
The build side parses each line's leading `Abbrev C:V` with `RefParser.parse_simple`, then calls `range_keys(versification)` on the resulting `SimpleBibleRef`; the show side gets the matching integers from `BibleRef.range_keys()` after parsing a reference.
Because both use the same versification, the keys line up, which is what makes range lookups correct.

### Range Lookup

`show` resolves a reference to one `(start_key, end_key)` pair per single-book range (`BibleRef.range_keys()`), then selects `verses` rows with `verse_key BETWEEN start AND end`.
Each pair stays within one book, so the `BETWEEN` is always safe, including across chapter boundaries.
`--in` on `search` reuses the same mechanism to scope a full-text query.

### Build Gating (warn-and-skip)

`build` (`builder.py`) never aborts on unusable lines; it skips and tallies them in `BuildStats`.
It resolves the leading `Abbrev C:V` of each line with `RefParser.parse_simple(..., silent=True)` under the `book_style` — parsing (not a bare `recognized_names` lookup) so a book can carry its own chapter styling, notably the NABRE's Esther chapter letters (`Est A:1` → `ESG`; enabled by `--chapter-letters`, which overlays the `en-nabre` style's `chapter_letters`).
A line is skipped when:

- `parse_simple` returns `None` and the abbreviation is not recognized (e.g. the Sirach prologue `Sip`, which is not a canonical book) — tallied as an unknown book;
- `parse_simple` returns `None` but the abbreviation *is* recognized (a malformed chapter/verse) — tallied as malformed; or
- the book is not in the chosen versification (off-scheme).

Crucially, `parse_simple` fails only on grammar, **not** on `SimpleBibleRef.is_valid`: a verse number that exceeds the versification's chapter length still parses.
The off-scheme check then gates on `range_keys` returning an **empty** list (book absent from the versification), **not** on `is_valid`.
This is deliberate: `is_valid` also rejects a verse whose number exceeds the bundled versification's chapter length, which would wrongly drop legitimate verses when the source text and the bundled versification disagree on verse counts.
`range_keys` still yields a usable key in that case, so the verse is preserved.

A future versiref `BibleRef`-overlap/inclusion feature could let off-scheme verses be stored and shown instead of skipped; the build gate is the single place to revisit if that lands.

### Bible Resolution (`resolver.py`)

`show`, `search`, and `info` accept their database argument as either a path or a bare name, resolved by `resolve_bible`:

1. An existing file path is used as-is (back-compatible; `kjv.db`, `./bibles/kjv.db`, absolute paths all work).
2. A path-like spec (contains a separator) that does not exist is an error — names are not searched for it.
3. A bare name resolves to `<name>.db` across the directories of `bible_search_path()`, first match winning.

`bible_search_path()` reads `VERSIREF_BIBLE_PATH` (`os.pathsep`-separated, like `PATH`); when unset it is the single `default_data_dir()` (per-platform user data dir). There is no separate repo-local search — point `VERSIREF_BIBLE_PATH` at the repo to get that. `default_data_dir` is hand-rolled (no `platformdirs` dependency) to keep the dependency surface at `versiref` + `click`.

### Database Identity and Schema Check (`database.py`)

A built Bible carries a `format` metadata marker (`PRODUCT_NAME = "versiref-bible"`) so it can be told apart from other versiref-ecosystem SQLite files (e.g. `versiref-search`) that share the `schema_version` key.
`Database.validate_schema()` checks the marker first (a foreign or unmarked database is rejected cleanly with `IncompatibleDatabaseError` rather than failing later on a missing table), then applies an additive semver rule on `schema_version`: same major, and minor >= the code's required minor (`SCHEMA_VERSION`).
Every read path calls it: `show_verses`, `search_verses` (`reader.py`), and `info` (`cli.py`).
Databases built before the marker existed are unmarked and rejected with a "rebuild the Bible" message — mirroring `versiref-search`'s identical check (its commit `6c58477`).

### Source Modules (`src/versiref/bible/`)

- `models.py`: `Verse` and `BuildStats` data classes.
- `ccat_markup.py`: `strip_markup` removes recognized BibleWorks/CCAT markup (footnote blocks, note anchors, Strong's numbers, tense/voice/mood codes; italics brackets and Psalm superscriptions are unwrapped, keeping their words); `has_markup_residue` flags leftover markup-like characters. Stripping is tolerant — unrecognized markup is kept and tallied (`BuildStats.suspect_markup`), never fatal. Named for the input format because other formats may be supported later.
- `database.py`: schema and the `Database` wrapper (insert, rebuild FTS, range and FTS queries, counts); `validate_schema`, `PRODUCT_NAME`, `IncompatibleDatabaseError`.
- `builder.py`: `build_database` — parse each `.cat` line's leading `Abbrev C:V` with `RefParser`, compute keys, strip markup (unless `keep_markup=True`), skip-and-tally, write the DB. `chapter_letters=True` overlays the NABRE Esther letters onto the book style.
- `reader.py`: `show_verses`, `search_verses`, and the `format_verse` plain-text formatter.
- `resolver.py`: resolve a Bible name or path to a `.db` file via `VERSIREF_BIBLE_PATH` (or the per-user `default_data_dir`); `resolve_bible`, `list_bibles`, `bible_search_path`, `BibleNotFoundError`.
- `cli.py`: Click CLI with the `build`, `show`, `search`, `info`, `list`, and `docs` commands. `show`/`search`/`info` accept a Bible name (resolved via `resolver.py`) or a path. `docs` prints the path to the bundled documentation (resolved with `importlib.resources.files`).
- `__init__.py`: public API exports.

Tests in `tests/` build a small in-memory fixture Bible and exercise build/show/search end to end.

## Input Format

Input is CCAT-format `.cat` text, one verse per line: `Abbrev C:V text`.
The abbreviation is a BibleWorks-style book name (`en-bibleworks`) by default.
For a file that numbers the Additions to Esther as chapters A–F (as the NABRE prints them), `--chapter-letters` makes `Est A:1` … `Est F:11` parse as `ESG`.
Recognized CCAT/BibleWorks markup — `{...}` footnote blocks (terminated, unterminated, or a stray trailing `}`), `<N1>`/`<Ra>` note anchors, `<0430>` Strong's numbers, `(08799)` tense/voice/mood codes, `[italics]`, and `<<Psalm superscriptions>>` (the latter two unwrapped, keeping the words) — is stripped by `ccat_markup.py` before storage so FTS sees clean text; `--keep-markup` stores lines verbatim.
The footnote/cross-reference *content* is discarded, not stored; extracting it into structured tables (cross-references as verse-key ranges, Strong's numbers per verse) is future work, and would be an additive schema-minor bump.
The sample CEI 2008 file is `cp1252`, not UTF-8, so `build` accepts `--encoding`.

Sample `.cat` Bibles live in `reference/samples/` (gitignored): a Brenton LXX (Old Testament and Apocrypha, **no New Testament**), a KJV (Strong's numbers kept as plain text), and an Italian CEI 2008.

## Key Dependencies

- **versiref** (>=0.9.0): parsing references, versification, and verse keys. First-party (same maintainer as this package).
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

## Releasing

When asked to make a release, Claude performs steps 1–8; publishing and pushing are done manually afterward (step 9).

1. Bump the version in `pyproject.toml` (the sole source of the version number).
2. Update `CHANGELOG.md` following the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format: rename the `## Unreleased` heading to the new version with the release date (`## X.Y.Z - YYYY-MM-DD`).
3. Run `uv lock` to update the lock file.
4. Run `pip-audit` (see "Dependency auditing") and verify no unfixed advisories apply.
5. Run tests, type checking, and linting to verify everything passes.
6. Make the release commit (subject line `Release X.Y.Z`).
7. Create an annotated tag named with the bare version number (e.g., `0.5.0`, not `v0.5.0`).
   The tag annotation message is the new version's `CHANGELOG.md` section — its `### Added`/`### Changed`/`### Removed` subsection headings and their entries, but **without** the `## X.Y.Z` version heading line.
   Tag with `git tag -a --cleanup=verbatim -F <file>`: the default cleanup strips lines beginning with `#`, which would silently drop the `###` subsection headings.
   GitHub renders this annotation as the release notes on the releases page.
8. Build the artifacts (Claude builds them but does not publish or push), in order:
   1. Delete any artifacts from previous versions with `rm -f dist/*`, so the directory holds only the current release's files and a publish step that uploads `dist/*` cannot pick up stale builds.
   2. Run `uv build` to produce the wheel and sdist in `dist/`.
9. Manual: publish and push the commit and tag.

## Markdown Style

When writing or editing Markdown (docs, README, this file):

- One sentence per line; do not hard-wrap at a column width.
- Always specify a language on fenced code blocks (e.g. `` ```sh ``, `` ```python ``).

## Important Files

- `src/versiref/bible/docs/`: user-facing documentation (tracked in git): `building.md`, `querying.md`. Bundled into the package as package data — the `uv_build` backend includes the whole module directory in the wheel and sdist by default — and exposed via the `docs` CLI subcommand, which prints the path to the bundled copy resolved with `importlib.resources.files`.
- `skill/`: a Claude Code skill (tracked) bundling versiref-bible usage and an invalid-reference workflow; `skill/versiref-bible/scripts/scan_refs.py` scans Markdown for structurally invalid Bible references with source locations, reusing `versiref-search`'s style/versification config. See `skill/README.md` to install it.
- `reference/`: sample `.cat` Bibles (gitignored; for AI-agent use). For the `versiref` API docs, run `uv run versiref docs`, which prints the path to the bundled copy.
- `pyproject.toml`: package configuration and dependencies; sole source of the version number.
- `src/versiref/bible/__init__.py`: public API exports.
- `uv.lock`: lock file for reproducible dependency resolution.
- `SECURITY.md`: disclosure process and supply-chain defenses.
- `CHANGELOG.md`: notable changes per version (Keep a Changelog format).
