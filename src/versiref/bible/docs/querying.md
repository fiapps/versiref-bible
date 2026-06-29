# Querying Databases

A versiref-bible database is an SQLite file with one row per Bible verse, keyed for
reference lookup and indexed for full-text search. You can read it by reference (`show`) or
search its text (`search`).

If you need to build a database first, see [building.md](building.md).

## Output Format

All verse output is plain text, one verse per line:

```text
John 3:16	For God so loved the world, that he gave his only begotten Son...
John 3:17	For God sent not his Son into the world to condemn the world...
```

Each line is `reference⇥text` — a formatted reference label, a TAB, then the verse text.
CCAT verse text is single-line, so the tab keeps each line unambiguous and easy to split. The
format is the same for `show` and `search`.

## Naming a Database

`show`, `search`, and `info` take a database as their first argument. You can give either:

- a **path** to a `.db` file (`kjv.db`, `./bibles/kjv.db`, an absolute path), or
- a bare **name** (`kjv`) that is looked up on a search path.

A name is resolved to `<name>.db` by searching, in order, the directories named by the
`VERSIREF_BIBLE_PATH` environment variable (separated by `:` on macOS/Linux, `;` on Windows,
like `PATH`). The first match wins. When `VERSIREF_BIBLE_PATH` is unset, a single per-user data
directory is searched:

- macOS: `~/Library/Application Support/versiref-bible`
- Linux: `$XDG_DATA_HOME/versiref-bible` (default `~/.local/share/versiref-bible`)
- Windows: `%LOCALAPPDATA%\versiref-bible`

So you can drop your `.db` files in that directory and refer to them by name from any working
directory:

```sh
versiref-bible show kjv "John 3:16"
versiref-bible search nvul "in the beginning was the word"
```

To keep a per-repo collection, point `VERSIREF_BIBLE_PATH` at the repo's directory (and, if you
want the per-user directory searched too, append it):

```sh
export VERSIREF_BIBLE_PATH="$PWD/bibles:$HOME/.local/share/versiref-bible"
```

Use `list` (below) to see which names are available.

## Showing Verses by Reference

`show` prints the verses a reference covers:

```sh
versiref-bible show kjv.db "John 3:16-18"
```

Ranges that cross a chapter boundary within a book work as expected:

```sh
versiref-bible show kjv.db "Gen 1:30-2:2"
```

### Reference Style

`--style` controls how your reference is parsed **and** how the output labels are formatted.
It defaults to `en-sbl` (Society of Biblical Literature). Because the style governs parsing,
write the reference in that style's conventions:

```sh
# en-sbl uses "C:V" and en-dash ranges
versiref-bible show cei_2008.db "Gen 1:1-3"

# it-cei uses "C,V"
versiref-bible show cei_2008.db "Gen 1,1-3" --style it-cei
```

### Versification

By default the reference is interpreted in the **database's own versification**, so keys line
up exactly. To supply a reference in a different scheme and have it mapped to the database's,
use `--from-versification`:

```sh
versiref-bible show brenton.db "Ps 23" --from-versification eng
```

This parses `Ps 23` in `eng` and maps it to the database's versification before looking up
verses. If the reference cannot be mapped, `show` reports an error.

If a reference resolves to no stored verses (for example, a New Testament reference against a
Septuagint database that has no New Testament), `show` prints `No verses found.` on stderr.

## Searching Verse Text

`search` runs a full-text query over verse text. By default results come back in **canonical
verse order**:

```sh
versiref-bible search kjv.db "light" --limit 5
```

The query uses SQLite **FTS5** syntax. It is case-insensitive and matches whole words, not
substrings (searching `grace` will not match `disgrace`). Some examples:

```sh
versiref-bible search kjv.db '"living water"'      # phrase
versiref-bible search kjv.db 'love AND world'      # boolean
versiref-bible search kjv.db 'redeem*'             # prefix
```

When more verses match than `--limit` allows, the kept verses are printed and a note is
written to stderr:

```text
… showing 5 of 209 matches (raise --limit to see more)
```

### Ordering

`--order` selects how results are sorted:

- `canonical` (default) — verse-key order, i.e. the order the verses appear in the Bible.
  Predictable and easy to navigate, and the right choice for common words.
- `relevance` — SQLite FTS5 bm25 ranking, best matches first, ties broken by canonical order.

```sh
versiref-bible search kjv.db "living water" --order relevance
```

bm25 normalizes by verse length, so under `relevance` a single-word query tends to surface the
**shortest** matching verses first (the hit is a larger fraction of the text); rarer words and
repeated occurrences also score higher. It earns its keep on phrase and multi-word queries; for
a single common word, `canonical` is usually more useful.

### Restricting the Search

`--in` scopes the search to a Bible reference (parsed in the database's versification, using
`--style`):

```sh
versiref-bible search kjv.db "light" --in "Gen 1"
versiref-bible search kjv.db "faith" --in "Romans"
```

Since `versiref` does not parse cross-book ranges, you have to list the individual books: not
`--in "Matt–John"`, but `--in "Matt; Mark; Luke; John"`.

## Database Info

`info` shows a database's metadata and verse count:

```sh
versiref-bible info kjv.db
```

```text
built_at: 2026-05-31T19:02:18
format: versiref-bible
schema_version: 1.0
source: kjv.cat
title: King James Version
verse_count: 31102
versification: eng
verses: 31102
```

Use this to discover a database's title and versification before querying it.

Every command that reads a database (`show`, `search`, `info`) first checks the `format` marker
and `schema_version`.
A file from another versiref tool (for example a `versiref-search` index), or a Bible built
before this check existed, is rejected with a message telling you to rebuild it, rather than
failing partway through a query.

## Listing Available Bibles

`list` prints the databases found on the search path (see
[Naming a Database](#naming-a-database)), one per line as
`name⇥versification⇥verses⇥title`:

```sh
versiref-bible list
```

```text
kjv	eng	31102	King James Version
nvul	vul	35817	Nova Vulgata
brenton	lxx	28145	Brenton Septuagint
```

The first column is the name you pass to `show`, `search`, and `info`. If no databases are
found, `list` prints the directories it searched on stderr and how to set
`VERSIREF_BIBLE_PATH`.

## Options Reference

In every command below, `DATABASE` is a Bible name on the search path or a path to a `.db`
file (see [Naming a Database](#naming-a-database)).

### `show` Command

```text
versiref-bible show [OPTIONS] DATABASE REFERENCE
```

| Option | Description |
| ------ | ----------- |
| `--style` | Reference style for parsing input and labelling output (default: `en-sbl`) |
| `--from-versification` | Interpret the reference in this versification and map it to the database's |

### `search` Command

```text
versiref-bible search [OPTIONS] DATABASE QUERY
```

| Option | Description |
| ------ | ----------- |
| `-n`, `--limit` | Maximum number of verses to return (default: 20) |
| `--in` | Restrict the search to a reference (e.g. `"Gen 1"`, `"John"`) |
| `--order` | Result order: `canonical` (default) or `relevance` (bm25) |
| `--style` | Reference style for labelling output and parsing `--in` (default: `en-sbl`) |

### `info` Command

```text
versiref-bible info DATABASE
```

Takes a single database (name or path). No additional options.

### `list` Command

```text
versiref-bible list
```

Takes no arguments. Lists the databases on the search path as
`name⇥versification⇥verses⇥title`; reads `VERSIREF_BIBLE_PATH` for the directories to search.

## Python API

The `versiref.bible` package exports `show_verses`, `search_verses`, and `format_verse` for
programmatic use:

```python
from versiref import RefStyle
from versiref.bible import format_verse, search_verses, show_verses

verses, db_vers = show_verses("kjv.db", "John 3:16-18")
style = RefStyle.named("en-sbl")
for verse in verses:
    print(format_verse(verse, style, db_vers))

results, total, db_vers = search_verses("kjv.db", "light", limit=5, scope="Gen 1")
```

`show_verses` returns the matching `Verse` objects plus the database's versification (for
labelling); `search_verses` also returns the total match count before the limit. See their
docstrings for full parameter documentation.
