# Building Databases

This document covers creating a versiref-bible database from a CCAT-format Bible text file.
If you only need to query an existing database, see [querying.md](querying.md).

## Quick Start

Build a Bible into a searchable database:

```sh
versiref-bible build kjv.cat -o kjv.db --versification eng --title "King James Version"
```

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
- **`text`** — the verse text.
  Recognized CCAT/BibleWorks markup is stripped before storage (see [Markup stripping](#markup-stripping) below); pass `--keep-markup` to store lines verbatim.

Each verse is stored as one row, keyed by an integer verse key (`BBCCCVVVSS`) computed under the
chosen versification, and indexed for full-text search with SQLite FTS5.

## Chapter letters (Additions to Esther)

The NABRE prints the Additions to Esther as chapters **A–F** rather than numbering them as verses of the surrounding Greek chapters.
If your source file follows that convention — `Est A:1`, `Est A:2`, … `Est F:11` — pass `--chapter-letters` so the lettered chapters parse as the Greek Esther book (`ESG`):

```sh
versiref-bible build nab.cat -o nabre.db --versification nabre --chapter-letters
```

The switch overlays the letters onto whatever `--book-style` you use, so BibleWorks abbreviations keep working; a numeric `Est 1:1` still resolves to plain Esther (`EST`).
The letters are defined by versiref's `en-nabre` style, so a versification that maps `ESG` (such as `nabre`) is required — otherwise the lettered lines are [skipped as off-scheme](#skipped-lines).
To see the letters in output, query with a letter-aware style, e.g. `--style en-nabre`.

## Markup Stripping

BibleWorks CCAT exports decorate the verse text with inline markup that would break phrase search (Strong's numbers interrupt word sequences) and pollute results (footnote text matches queries).
By default, `build` strips the recognized markup so the stored text — and therefore FTS — is clean:

| Markup | Example | Handling |
| ------ | ------- | -------- |
| Footnote block | `{<p><rsup>a</rsup> Pro 8:27-29 }` | Removed (an unterminated block runs to end of line; a stray trailing `}` is also dropped); its translator's notes are [stored separately](#translators-notes) |
| Note/cross-reference anchor | `made<N1>`, `<Ra>separated` | Removed |
| Strong's number | `<0430>` (Hebrew), `<5547>` (Greek), `<07363b>` (homograph) | Removed |
| Tense/voice/mood code | `(08799)` | Removed |
| Formatting tag | `<i>…</i>`, `<sup>…</sup>`, `<link b="Gen 1:1">…</>`, and the rest of the documented SGML-like vocabulary, plus the HTML-ish `<a id="…">` and `<br/>` some exports emit | Removed — the text they wrap is kept |
| Translator-supplied italics | `[that]` | Unwrapped — the word is kept |
| Literal bracket | `[[Jews]]` | Collapsed to `[Jews]` — the CCAT escape for a bracket that is part of the text, used for passages of doubtful authenticity |
| Small caps | `\LORD\` | Unwrapped — the word is kept |
| Psalm superscription | `<<A Psalm of David.>>` (KJV), `<A Psalm of David.>` (NRSV) | Unwrapped — the title text is kept |

A tag between two words leaves a space behind, so that dropping it cannot weld them into a token no search would find (`31.9<br/>follows` → `31.9 follows`).

Stripping is tolerant: only these recognized shapes are removed, and anything else is stored as-is.
In particular, only the documented tag names are recognized: an unknown tag such as `<span class="q">` is left in place and reported rather than unwrapped into its attributes.
One documented notation is deliberately not handled — the two-digit codes for special Greek manuscript characters, which are bare digits inside Greek text and so cannot be told from ordinary digits.
A verse that still contains markup-like characters (`<`, `>`, `{`, `}`) after stripping is counted and reported as a warning, so a new source file's unrecognized quirks surface at build time instead of as silent search misses.
Cross-references and Strong's numbers are currently discarded, not stored; since the database is cheap to regenerate from the `.cat` file, nothing is lost if a future version learns to store them.

Pass `--keep-markup` to skip stripping entirely and store each line's text verbatim.

### Translator's Notes

A footnote block holds one note per `<p>`: `<nsup>1</nsup>` labels a translator's note, `<rsup>a</rsup>` a cross-reference.
The translator's notes are stored in a `notes` table, keyed by verse and kept in the block's order, so that `show --notes` can print them (see [querying.md](querying.md#translators-notes)).
A note's body is stripped of markup the same way the verse text is, and it stays out of the full-text index: searching verse text does not match note text.

Notes are stored by label, independently of the `<N1>` anchors in the verse text, because the two do not always pair up (the KJV's Gen 1:20 has one anchor and four notes).
The build summary reports how many notes were extracted.
Extraction is part of stripping, so a `--keep-markup` build stores no notes.

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
versiref-bible build cei_2008.cat -o cei_2008.db --versification cei --encoding cp1252 --title "CEI 2008"
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
| `-o`, `--output` | Output database path (required) |
| `--title` | Human-readable title stored in the database metadata |
| `--book-style` | Reference style whose names map the file's abbreviations (default: `en-bibleworks`) |
| `--encoding` | Text encoding of the input file (default: `utf-8`) |
| `--keep-markup` | Store verse text verbatim instead of stripping CCAT/BibleWorks markup |

## Stored Metadata

`build` records these keys in the database (view them with `versiref-bible info`):

| Key | Description |
| --- | ----------- |
| `schema_version` | Database schema version |
| `versification` | The versification the verse keys were computed against |
| `source` | The input file name |
| `verse_count` | Number of verses stored |
| `notes_count` | Number of translator's notes stored; always written, so `0` means this Bible has none, and a missing key means the database predates notes and must be rebuilt to use `show --notes` |
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

`extract_markup` is the markup handling on its own: given a line's text, it returns an `ExtractedMarkup` holding the clean text (`text`, which is all `strip_markup` returns) and what the markup carried.

```python
from versiref.bible import extract_markup

extracted = extract_markup(
    "And God <0430> made<N1> the expanse. "
    "{<p><rsup>a</rsup> Pro 8:27-29 <p><nsup>1</nsup> Or [fashioned] }"
)
extracted.text              # 'And God made the expanse.'
extracted.notes             # (Note(label='1', text='Or fashioned'),)
extracted.cross_references  # (Note(label='a', text='Pro 8:27-29'),)
extracted.anchors           # ('N1',)
extracted.strongs           # (StrongsTag(lang='H', number=430, suffix='', word_start=0, word_end=2),)
```

A `StrongsTag` locates the words it tags as a span of `text.split()`, running from the previous tag (or the start of the verse) to this one; the span is empty when a tag directly follows another.
Only the translator's notes are stored by `build` so far; cross-references and Strong's numbers are returned for callers that want them.
