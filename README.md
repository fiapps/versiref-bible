# VersiRef Bible

[VersiRef](https://github.com/fiapps/versiref) is a Python package for sophisticated parsing,
manipulation, and printing of references to the Bible.

`versiref-bible` provides access to Bibles in an SQLite-based format: ranges of verses can be
retrieved by reference, and verse text can be searched with SQLite FTS5. VersiRef parses the
references and handles versification.

The command-line interface is designed for use by an LLM: output is compact plain text, one
verse per line as `reference⇥text` (TAB-separated).

## Documentation

- [Building Databases](docs/building.md) — the `build` command (producers).
- [Querying Databases](docs/querying.md) — the `show`, `search`, and `info` commands (consumers).

## Installation

```sh
uv sync
```

This installs the `versiref-bible` command into the project environment (run it with
`uv run versiref-bible …`).

## Commands

### `build` — create a database from a text file

Reads a CCAT-format `.cat` file where each line is `Abbrev C:V text` (the abbreviation is a
BibleWorks-style book name) and writes an SQLite database. Each verse is stored as one row,
keyed by an integer verse key computed under the chosen versification, plus an FTS5 index over
the verse text. CCAT footnotes/formatting are kept as plain text for now.

```sh
uv run versiref-bible build BIBLE.cat -o BIBLE.db --versification eng --title "My Bible"
```

Options:

- `-v, --versification` (required) — named versification of the Bible (`eng`, `lxx`, `cei`, …).
- `-o, --output` (required) — output database path.
- `--title` — human-readable title stored in the database.
- `--book-style` — reference style whose names map the file's abbreviations
  (default `en-bibleworks`).
- `--encoding` — input text encoding (e.g., `cp1252`; default `utf-8`).

Lines whose book abbreviation is unrecognized (e.g. the Sirach prologue `Sip`), or whose book
is absent from the chosen versification, are skipped with a warning on stderr.

### `show` — print the verses of a reference

```sh
uv run versiref-bible show BIBLE.db "John 3:16-18"
```

- `--style` — reference style for parsing the input and labelling output (default `en-sbl`).
- `--from-versification` — interpret the reference in this versification and map it to the
  database's versification.

The reference is parsed in the style you choose, so use that style's conventions
(e.g. `--style it-cei` expects `Gen 1,1-3`, not `Gen 1:1-3`).

### `search` — full-text search verse text

```sh
uv run versiref-bible search BIBLE.db "living water" --limit 10
```

`QUERY` uses SQLite FTS5 syntax (e.g. `light`, `"living water"`, `love AND world`). Results
are in canonical verse order by default.

- `-n, --limit` — maximum verses to return (default 20).
- `--in` — restrict the search to a reference (e.g. `--in "Gen 1"`, `--in "John"`).
- `--order` — `canonical` (default, verse order) or `relevance` (bm25 ranking).
- `--style` — reference style for labelling output and parsing `--in` (default `en-sbl`).

### `info` — show database metadata

```sh
uv run versiref-bible info BIBLE.db
```

Prints the stored metadata (title, versification, source, build time, …) and the verse count.

## Development

```sh
uv run pytest        # tests
uv run ruff check    # lint
uv run mypy src      # type-check
```
