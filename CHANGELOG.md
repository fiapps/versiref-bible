# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Added

- `build --literal-brackets` (Python: `build_database(literal_brackets=True)`, and the same keyword on `extract_markup` and `strip_markup`) keeps square brackets as printed characters instead of reading `[word]` as italics and `[[`/`]]` as escaped brackets. Bracket italics are an option of the BibleWorks compiler, so a text prepared without it — the Nestle-Aland Greek New Testament, the Westminster Hebrew text — can now be built from the export as it stands, without doubling its brackets first. The rest of the markup is still stripped.

## 0.5.0 - 2026-11-16

### Added

- `show --notes` (Python: `show_verses(..., notes=True)`, `format_note`) prints each verse's translator's notes after it, as `reference note label<TAB>text`. `build` now stores the notes of a CCAT footnote block (`<nsup>` entries) in a `notes` table instead of discarding them, reports how many it extracted, and records the number as the `notes_count` metadata key. The key is always written, so `info` shows whether a database has the feature (`0`: this Bible has no notes; no key: rebuild it). Notes stay out of the full-text index.
- `extract_markup` (with `ExtractedMarkup`, `StrongsTag`, and `Note`) returns a line's clean text together with what its markup carried: translator's notes, cross-references, note anchors, and Strong's numbers with the words each one tags. `strip_markup` is unchanged and returns the same text. Only the notes are stored so far.
- An inserted verse keeps its letter in output: the Greek additions to Esther after 4:17 are labelled `Add Esth 4:17a`, `4:17b`, … instead of all appearing as `Add Esth 4:17`. `Verse` gains a `subverse` field.
- `build --encoding beta-code` (Python: `build_database(encoding="beta-code")`, `beta_to_unicode`) converts a Greek text written in Beta Code, such as the BibleWorks export of Rahlfs' Septuagint, to Unicode: `e)n a)rxh^|` is stored as ἐν ἀρχῇ. Capitals are accepted as BibleWorks writes them (`A)ssuri/wn`) and as the TLG does (`*)assuri/wn`).
- Greek is searched without regard to breathings, accents, iota subscripts, or the form of the sigma: `θεος` finds θεὸς and θεός alike. The full-text index holds Greek folded (the stored text is unchanged) and a search folds its query to match; a build records this as the `search_folding` metadata key. A database built earlier is searched as before, matching Greek only as written, until it is rebuilt.
- `search --phrase` (`-p`; Python: `search_verses(..., phrase=...)`) searches for text exactly as written, in place of the query. The query is an FTS5 search expression, so ordinary text containing punctuation, such as "so-called" or "Isa 7:14", was refused as invalid syntax; an invalid query's error now points to `--phrase`.

### Fixed

- Markup stripping no longer mistakes a backslash inside or after a word for a small-caps marker: `\LORD\` is recognized only where the backslashes hug whole words. Since 0.4.1 any two backslashes on a line were paired, which silently removed the grave accents of Beta Code Greek (`qeo\s to\n`). A Beta Code text built without `--encoding beta-code` is now stored as written.
- `show`, `search`, and `info` report a file that is not an SQLite database, or an SQLite database with no metadata table, as "not a versiref-bible database" instead of failing with a traceback; likewise an unknown `--style`.
- `build` refuses an output path that is its own input file instead of overwriting the source with the database.
- `build` ignores a UTF-8 byte-order mark, which used to make the first verse an unrecognized book.

### Changed

- Database schema 2.1 adds the `notes` table and a `subverse` column on `verses`. The bump is additive: `show`, `search`, and `info` still read a schema 2.0 database, which keeps its old labels, and only `show --notes` asks for a rebuild.
- `build` counts an input line whose reference is a range or list (`Gen 1:4-6`) as malformed instead of storing it under its first verse.
- `build` warns when no verses at all were stored.
- `search --limit` must be at least 1.

- Requires versiref 0.13.0, whose references hold their verse ranges directly and may span books.
- `build` counts an input line whose reference names no chapter or verse as malformed instead of storing it.

## 0.4.1 - 2026-07-25

### Changed

- Markup stripping now covers the rest of the documented CCAT/BibleWorks vocabulary and the shapes real exports actually carry: SGML-like formatting tags (`<i>`, `<sup>`, `<link b="Gen 1:1">…</>`, and the generic `</>` close), the HTML-ish `<a id="…">` anchors and `<br/>` breaks found in the NETS export, single-angle Psalm superscriptions (`<A Psalm of David.>`, as the NRSV writes them), `[[`/`]]` escapes for a literal bracket, `\LORD\` small caps, and Strong's numbers with a homograph letter (`<07363b>`). Across the six Bibles built from BibleWorks exports this cuts unrecognized-markup warnings from 340 verses to 2, both genuinely corrupt source lines, and only one of them in a book its versification keeps. Only the documented tag names are recognized, so an unknown tag is still left in place and reported.
- Dropping a tag that sits between two words now leaves a space, so the words stay separately searchable (`31.9<br/>follows` → `31.9 follows`) instead of being welded into one token.
- Requires versiref >= 0.10.1, which corrects the `cei` versification's Greek Esther subverses. Under 0.10.0 a CEI source file's `Esg 1:1a`, `Esg 4:17v`, and `Esg 8:12v` all resolved to their base verse's key, so each silently overwrote the verse before it — Addition A's opening among them. Rebuild any CEI Bible built with 0.10.0.

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
