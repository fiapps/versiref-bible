# Building Databases

This document covers creating a versiref-bible database from a CCAT-format Bible text file.
If you only need to query an existing database, see [querying.md](querying.md).

## Quick Start

Build a Bible into a searchable database:

```sh
versiref-bible build kjv.cat --versification eng --title "King James Version"
```

The output database defaults to the input name with a `.db` suffix (here, `kjv.db`); pass
`-o`/`--output` to choose another path.

A build prints a one-line summary, e.g.:

```text
✓ Built kjv.db (31102 verses)
```

Any skipped lines are reported as warnings on **stderr** (see
[Skipped lines](#skipped-lines) below).

## Input Format

The input is a CCAT-format `.cat` file with one verse per line:

```text
Gen 1:1 In the beginning God made the heaven and the earth.
Gen 1:2 But the earth was unsightly and unfurnished...
```

Each line is `Abbrev C:V text`:

- **`Abbrev`** — a book abbreviation. By default these are read as BibleWorks-style names
  (versiref's `en-bibleworks` style); change this with `--book-style`.
- **`C:V`** — chapter and verse, colon-separated.
- **`text`** — the verse text, taken verbatim. CCAT footnotes and inline formatting are kept
  as plain text for now; parsing them is future work. (For example, KJV Strong's numbers like
  `<07225>` are stored as-is.)

Each verse is stored as one row, keyed by an integer verse key (`BBCCCVVV`) computed under the
chosen versification, and indexed for full-text search with SQLite FTS5.

## Choosing a Versification

`--versification` is **required**: it fixes the chapter/verse scheme the verse keys are
computed against, and it is what later lets `show` resolve a reference to the right rows. Use a
named versification such as `eng` (Protestant English), `lxx` (Septuagint), `cei` (Italian
CEI), `vulgata`, `org`, and so on.

Pick the scheme the text was actually authored against. Differences usually show up in Psalm
numbering and in the inclusion and arrangement of deuterocanonical books. A book that is **not
part of the chosen versification** cannot be assigned a verse key, so its verses are skipped
(see below). If a build skips a whole book you expected to keep, that is the signal to choose a
versification that includes it.

## Skipped Lines

versiref-bible never aborts on unusable lines; it skips them and tallies a warning. There are
four categories:

| Category | Meaning |
| -------- | ------- |
| unrecognized book abbreviation | The abbreviation is not in the book style's recognized names (e.g. the Sirach prologue `Sip`, which is not a canonical book). |
| book not in the versification | The book is recognized but absent from `--versification`, so no verse key can be computed. |
| malformed line | A non-blank line that does not parse as `Abbrev C:V text`. |
| duplicate verse key | Two lines map to the same key; the later line wins. |

Example warnings (stderr):

```text
✓ Built brenton_w_apoocrypha.db (28592 verses)
  warning: skipped 1 line(s) with unrecognized book abbreviations: Sip
```

## Encoding

`--encoding` selects the text encoding of the input file (default `utf-8`). Not every CCAT
file is UTF-8; the sample CEI 2008 text, for instance, is `cp1252`:

```sh
versiref-bible build cei_2008.cat --versification cei --encoding cp1252 --title "CEI 2008"
```

## Book-Name Style

`--book-style` names the reference style whose recognized names map the file's abbreviations
to book IDs. The default, `en-bibleworks`, matches the BibleWorks abbreviations used by the
sample `.cat` files. Use a different style if your source file uses different abbreviations.

This style affects only how the *input file's* book names are read; it is independent of the
`--style` used to label output when you later run `show` or `search`.

## CLI Options Reference

```text
versiref-bible build [OPTIONS] INPUT_FILE
```

| Option | Description |
| ------ | ----------- |
| `-v`, `--versification` | Named versification of the Bible (required, e.g. `eng`, `lxx`, `cei`) |
| `-o`, `--output` | Output database path (default: input name with a `.db` suffix) |
| `--title` | Human-readable title stored in the database metadata |
| `--book-style` | Reference style whose names map the file's abbreviations (default: `en-bibleworks`) |
| `--encoding` | Text encoding of the input file (default: `utf-8`) |

## Stored Metadata

`build` records these keys in the database (view them with `versiref-bible info`):

| Key | Description |
| --- | ----------- |
| `schema_version` | Database schema version |
| `versification` | The versification the verse keys were computed against |
| `book_style` | The book-name style used to read the input |
| `source` | The input file name |
| `verse_count` | Number of verses stored |
| `built_at` | Local timestamp of the build |
| `title` | Title, if `--title` was given |

## Python API

The `versiref.bible` package exports `build_database` for programmatic use:

```python
from versiref.bible import build_database

stats = build_database(
    "kjv.cat",
    "kjv.db",
    versification="eng",
    title="King James Version",
)
print(stats.stored, stats.unknown_books)
```

It returns a `BuildStats` describing what was stored and skipped. See its docstring for full
parameter documentation.
