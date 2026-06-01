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

## Database Info

`info` shows a database's metadata and verse count:

```sh
versiref-bible info kjv.db
```

```text
built_at: 2026-05-31T19:02:18
schema_version: 1.0
source: kjv.cat
title: King James Version
verse_count: 31102
versification: eng
verses: 31102
```

Use this to discover a database's title and versification before querying it.

## Options Reference

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

Takes a single database path. No additional options.

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
