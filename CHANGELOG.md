# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Bible name resolution: `show`, `search`, and `info` now accept a bare Bible name (e.g. `kjv`) in addition to a path to a `.db` file. A name is resolved to `<name>.db` by searching the directories on the `VERSIREF_BIBLE_PATH` environment variable (`os.pathsep`-separated, like `PATH`), the first match winning; when it is unset a single per-user data directory is searched (`~/Library/Application Support/versiref-bible` on macOS, `$XDG_DATA_HOME/versiref-bible` on Linux, `%LOCALAPPDATA%\versiref-bible` on Windows).
- `list` subcommand: print the Bible databases found on the search path, one per line as `name<TAB>versification<TAB>verses<TAB>title`.
- Public Python API: `resolve_bible`, `list_bibles`, `bible_search_path`, `default_data_dir`, and `BibleNotFoundError`.

## 0.1.0

Initial release. Includes:

- `build` subcommand: build an SQLite Bible from a CCAT-format `.cat` text file. Maps each line's book abbreviation to a Paratext ID (via the `--book-style` recognized names, default `en-bibleworks`) and stores one row per verse, keyed by the `BBCCCVVV` integer computed under `--versification`, with an FTS5 index over the verse text. Supports `--title`, `--encoding` (e.g. `cp1252`), and `-o`/`--output`. Lines whose book is unrecognized or absent from the versification are warned-and-skipped.
- `show` subcommand: print the verses a Bible reference covers, one per line as `reference<TAB>text`. Supports `--style` (default `en-sbl`) for parsing and labelling, and `--from-versification` to map a reference from another scheme into the database's.
- `search` subcommand: full-text search of verse text with SQLite FTS5. Returns results in canonical verse order by default, or by bm25 relevance with `--order relevance` (ties broken by canonical order). Supports `-n`/`--limit`, `--in` to scope to a reference, and `--style`.
- `info` subcommand: print a database's metadata and verse count.
- Public Python API: `build_database`, `show_verses`, `search_verses`, `format_verse`, `Database`, `Verse`, `BuildStats`.
- User-facing documentation in `docs/` (`building.md`, `querying.md`).
