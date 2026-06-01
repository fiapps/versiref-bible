# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `build` subcommand: build an SQLite Bible from a CCAT-format `.cat` text file. Maps each line's book abbreviation to a Paratext ID (via the `--book-style` recognized names, default `en-bibleworks`) and stores one row per verse, keyed by the `BBCCCVVV` integer computed under `--versification`, with an FTS5 index over the verse text. Supports `--title`, `--encoding` (e.g. `cp1252`), and `-o`/`--output`. Lines whose book is unrecognized or absent from the versification are warned-and-skipped.
- `show` subcommand: print the verses a Bible reference covers, one per line as `reference<TAB>text`. Supports `--style` (default `en-sbl`) for parsing and labelling, and `--from-versification` to map a reference from another scheme into the database's.
- `search` subcommand: full-text search of verse text with SQLite FTS5, ranked by relevance. Supports `-n`/`--limit`, `--in` to scope to a reference, and `--style`.
- `info` subcommand: print a database's metadata and verse count.
- Public Python API: `build_database`, `show_verses`, `search_verses`, `format_verse`, `Database`, `Verse`, `BuildStats`.
- User-facing documentation in `docs/` (`building.md`, `querying.md`).
