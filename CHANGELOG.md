# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## 0.4.0 - 2026-07-20

### Added

- `build` accepts `--chapter-letters` (Python: `chapter_letters=True`) for source files that number the Additions to Esther as chapters A–F, as the NABRE prints them: `Est A:1` … `Est F:11` parse as the Greek Esther book (`ESG`) while a numeric `Est 1:1` still resolves to plain Esther. The switch overlays the letters (from versiref's `en-nabre` style) onto `--book-style`, so a versification that maps `ESG` (e.g. `nabre`) is required.

### Changed

- `build` now resolves each line's leading `Abbrev C:V` by parsing it with the book style (via versiref's `RefParser`) instead of a bare abbreviation lookup, which is what enables chapter letters. Off-scheme tolerance and the warn-and-skip tallies are unchanged.
- Requires versiref >= 0.10.0, which widens the integer verse key from `BBCCCVVV` to `BBCCCVVVSS` (a trailing subverse ordinal). This gives inserted verses such as the Greek additions to Esther (`ESG 4:17a`–`z`) distinct, correctly ordered keys instead of colliding on their base verse's key. The package treats keys as opaque, so only their stored width changes.
- **Schema version bumped to 2.0 (breaking).** Because the wider keys change the on-disk data, databases built before this release (schema 1.x, 8-digit keys) can no longer be queried correctly; they are now rejected up front with the usual "rebuild the Bible" message rather than silently returning no matches. Rebuild any existing Bible with this version.

## 0.3.0 - 2026-07-15

### Added

- `build` now strips recognized CCAT/BibleWorks markup from verse text before storage: `{...}` footnote blocks (including unterminated ones and stray trailing braces), `<N1>`/`<Ra>` note anchors, `<0430>` Strong's numbers, `(08799)` tense/voice/mood codes; `[italics]` and `<<Psalm superscriptions>>` are unwrapped, keeping their words. This keeps footnote text out of search results and stops Strong's numbers from breaking phrase queries. Stripping is tolerant — unrecognized markup is stored as-is and reported as a warning. Pass `--keep-markup` (Python: `keep_markup=True`) for the old verbatim behavior.
- Public Python API: `strip_markup`.

## 0.2.0 - 2026-06-29

### Added

- `docs` subcommand: print the filesystem path to the bundled documentation. With no argument it prints the docs directory; pass a file name (e.g. `querying.md`) to print the path to a single doc.

### Changed

- User-facing documentation now ships inside the installed package (`src/versiref/bible/docs/`), so any environment with the package installed can locate version-matched docs via the `docs` subcommand without copying files around.

## 0.1.2 - 2026-06-14

### Added

- Every command that reads a database (`show`, `search`, and `info`) now verifies that the file is a versiref-bible Bible before using it. A database from another versiref tool (e.g. versiref-search), or one built before this check existed, is rejected up front with a clear message telling you to rebuild, instead of failing partway through. New Bibles carry a `format` metadata marker (`versiref-bible`) so they pass the check.
- Public Python API: `IncompatibleDatabaseError`.

## 0.1.1 - 2026-06-14

### Added

- Bible name resolution: `show`, `search`, and `info` now accept a bare Bible name (e.g. `kjv`) in addition to a path to a `.db` file. A name is resolved to `<name>.db` by searching the directories on the `VERSIREF_BIBLE_PATH` environment variable (`os.pathsep`-separated, like `PATH`), the first match winning; when it is unset a single per-user data directory is searched (`~/Library/Application Support/versiref-bible` on macOS, `$XDG_DATA_HOME/versiref-bible` on Linux, `%LOCALAPPDATA%\versiref-bible` on Windows).
- `list` subcommand: print the Bible databases found on the search path, one per line as `name<TAB>versification<TAB>verses<TAB>title`.
- Public Python API: `resolve_bible`, `list_bibles`, `bible_search_path`, `default_data_dir`, and `BibleNotFoundError`.
- A Claude Code skill under `skill/` (not part of the published package): bundles versiref-bible usage and an invalid-reference workflow, with `scan_refs.py` to scan Markdown for structurally invalid Bible references and report their source locations, reusing `versiref-search`'s style/versification config.

## 0.1.0

Initial release. Includes:

- `build` subcommand: build an SQLite Bible from a CCAT-format `.cat` text file. Maps each line's book abbreviation to a Paratext ID (via the `--book-style` recognized names, default `en-bibleworks`) and stores one row per verse, keyed by the `BBCCCVVV` integer computed under `--versification`, with an FTS5 index over the verse text. Supports `--title`, `--encoding` (e.g. `cp1252`), and `-o`/`--output`. Lines whose book is unrecognized or absent from the versification are warned-and-skipped.
- `show` subcommand: print the verses a Bible reference covers, one per line as `reference<TAB>text`. Supports `--style` (default `en-sbl`) for parsing and labelling, and `--from-versification` to map a reference from another scheme into the database's.
- `search` subcommand: full-text search of verse text with SQLite FTS5. Returns results in canonical verse order by default, or by bm25 relevance with `--order relevance` (ties broken by canonical order). Supports `-n`/`--limit`, `--in` to scope to a reference, and `--style`.
- `info` subcommand: print a database's metadata and verse count.
- Public Python API: `build_database`, `show_verses`, `search_verses`, `format_verse`, `Database`, `Verse`, `BuildStats`.
- User-facing documentation in `docs/` (`building.md`, `querying.md`).
