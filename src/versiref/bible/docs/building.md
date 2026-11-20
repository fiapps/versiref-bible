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

The NABRE prints the Additions to Esther as chapters **A–F** of Esther rather than numbering them as verses of the surrounding Greek chapters.
The `nabre` versification has these lettered chapters, so a source file that follows that convention — `Est A:1`, `Est A:2`, … `Est F:11` — builds as it stands:

```sh
versiref-bible build nab.cat -o nabre.db --versification nabre
```

The lettered chapters belong to Esther (`EST`) and stand where the NABRE prints them: A before 1:1, B after 3:13, C after 4:17, D before 5:1, E after 8:12, and F after 10:3.
So `show nabre "Esth"` reads the book in order, and a range can pass between a numbered and a lettered chapter (`Esth 4:1-C:30`).
A numbered chapter leaves out a lettered chapter at its edge: `Esth 4` ends at 4:17.
Under a versification without lettered chapters, the lettered lines do not parse and are [skipped as malformed](#skipped-lines).

## Markup Stripping

BibleWorks CCAT exports decorate the verse text with inline markup that would break phrase search (Strong's numbers interrupt word sequences) and pollute results (footnote text matches queries).
By default, `build` strips the recognized markup so the stored text — and therefore FTS — is clean:

| Markup | Example | Handling |
| ------ | ------- | -------- |
| Footnote block | `{<p><rsup>a</rsup> Pro 8:27-29 }` | Removed (an unterminated block runs to end of line; a stray trailing `}` is also dropped); its translator's notes are [stored separately](#translators-notes) |
| Note/cross-reference anchor | `made<N1>`, `<Ra>separated`, `Habira<Na>`, `<N+>And` | Removed |
| Strong's number | `<0430>` (Hebrew), `<5547>` (Greek), `<07363b>` (homograph) | Removed |
| Tense/voice/mood code | `(08799)` | Removed |
| Formatting tag | `<i>…</i>`, `<sup>…</sup>`, `<link b="Gen 1:1">…</>`, and the rest of the documented SGML-like vocabulary, plus the HTML-ish `<a id="…">` and `<br/>` some exports emit | Removed — the text they wrap is kept |
| Translator-supplied italics | `[that]` | Unwrapped — the word is kept (unless `--literal-brackets`; see [Printed brackets](#printed-brackets)) |
| Literal bracket | `[[Jews]]` | Collapsed to `[Jews]` — the CCAT escape for a bracket that is part of the text, used for passages of doubtful authenticity (unless `--literal-brackets`) |
| Small caps | `\LORD\` | Unwrapped — the word is kept |
| Psalm superscription | `<<A Psalm of David.>>` (KJV), `<A Psalm of David.>` (NRSV) | Unwrapped — the title text is kept |

A tag between two words leaves a space behind, so that dropping it cannot weld them into a token no search would find (`31.9<br/>follows` → `31.9 follows`).

Stripping is tolerant: only these recognized shapes are removed, and anything else is stored as-is.
In particular, only the documented tag names are recognized: an unknown tag such as `<span class="q">` is left in place and reported rather than unwrapped into its attributes.
One documented notation is deliberately not handled — the two-digit codes for special Greek manuscript characters, which are bare digits inside Greek text and so cannot be told from ordinary digits.
A verse that still contains markup-like characters (`<`, `>`, `{`, `}`) after stripping is counted and reported as a warning, so a new source file's unrecognized quirks surface at build time instead of as silent search misses.
Cross-references and Strong's numbers are currently discarded, not stored; since the database is cheap to regenerate from the `.cat` file, nothing is lost if a future version learns to store them.

Pass `--keep-markup` to skip stripping entirely and store each line's text verbatim.

### Printed Brackets

Reading `[word]` as italics is an option of the BibleWorks compiler, and many texts are prepared without it: their square brackets are printed characters.
The Nestle-Aland Greek New Testament brackets words of doubtful authenticity (`[καὶ] λέγων`) and double-brackets Mark 16:9-20; the Westminster Hebrew text gives each qere in brackets.
Stripped as italics, those brackets would be lost, and a verse with two bracketed words could lose the wrong pair.

Pass `--literal-brackets` for such a text.
Every square bracket is then stored as written — `[word]` is not unwrapped, and `[[` is two brackets, not an escape for one — while the rest of the markup is stripped as usual.
The option applies to the whole file, notes included, so a text that uses brackets both ways still needs its printed brackets doubled in the source.

### Translator's Notes

A footnote block holds one note per `<p>`: `<nsup>1</nsup>` labels a translator's note, `<rsup>a</rsup>` a cross-reference.
The translator's notes are stored in a `notes` table, keyed by verse and kept in the block's order, so that `show --notes` can print them (see [querying.md](querying.md#translators-notes)).
A note's body is stripped of markup the same way the verse text is, and it stays out of the full-text index: searching verse text does not match note text.

Notes are stored by label, independently of the `<N1>` anchors in the verse text, because the two do not always pair up (the KJV's Gen 1:20 has one anchor and four notes).
A note repeated word for word under the same label in one verse is stored once: the New English Translation of the Septuagint gives a note twice when it marks both ends of a phrase.
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

### Beta Code Greek

Some Greek texts, such as the BibleWorks export of Rahlfs' Septuagint, are written in Beta Code: ASCII letters and marks standing for polytonic Greek (`e)n a)rxh^|` for ἐν ἀρχῇ).
Give `--encoding beta-code` to store such a text as Unicode Greek:

```sh
versiref-bible build lxx_rahlfs.cat -o lxx.db --versification lxx --encoding beta-code --title "Septuaginta (Rahlfs)"
```

```text
Gen 1:1	ἐν ἀρχῇ ἐποίησεν ὁ θεὸς τὸν οὐρανὸν καὶ τὴν γῆν
```

`beta-code` is handled by versiref-bible itself, not by Python's codecs.
Only the verse text is converted: the line's leading `Abbrev C:V` is read as written, and markup is stripped first, so a tag's name is not mistaken for Greek letters (with `--keep-markup` the whole text is converted, tags included).

| Beta Code | Meaning |
| --------- | ------- |
| `a b g d e z h q i k l m n c o p r s t u f x y w` | α β γ δ ε ζ η θ ι κ λ μ ν ξ ο π ρ σ τ υ φ χ ψ ω (`v` is ϝ; `j` is ς) |
| `)` `(` | Smooth and rough breathing |
| `/` `\` `^` or `=` | Acute, grave, and circumflex accent |
| `+` `\|` | Diaeresis and iota subscript |
| `A)` or `*)a` | A capital: an uppercase letter with its marks after it (BibleWorks), or an asterisk, the marks, then the letter (TLG) |
| `'` | Elision, stored as `’` |

A sigma ending its word becomes a final sigma (ς).
Digits, brackets, and other punctuation are kept, as is a mark that cannot belong to the letter before it (the `)` closing a parenthesis after a consonant).
A letter's case carries over, so a file in the all-uppercase TLG form, where `A` is a lowercase alpha, is not supported.

Without `--encoding beta-code` a Beta Code file still builds, but its text is stored as the ASCII it is.
The same conversion is available in Python as `versiref.bible.beta_to_unicode`.

Greek is searched without regard to its diacritics, however it reached the database (see [querying.md](querying.md#searching-greek)).

## Book-Name Style

`--book-style` names the reference style whose recognized names map the file's abbreviations
to book IDs. The default, `en-bibleworks`, matches the BibleWorks abbreviations used by the
sample `.cat` files. Use a different style if your source file uses different abbreviations.

This style affects only how the *input file's* book names are read; it is independent of the
`--style` used to label output when you later run `show` or `search`.

### Style Files

`--book-style` also accepts the path of a versiref style file: a value that ends in `.json` or contains a path separator is read as a file, not as a style's name.
Use one when a source file's abbreviations are almost those of a named style, but some name the wrong book for the versification.

BibleWorks' Septuagint texts are the usual case.
They call the Old Greek Daniel `Dan` and give Judges in two texts, `Jda` and `Jdg`, while the `lxx` versification files the Old Greek Daniel as `DAG` and the two Judges as `JDG` and `JDB`.
Read with `en-bibleworks`, `Dan` is skipped as a book not in the versification and one Judges text overwrites the other.
A style file that starts from `en-bibleworks` and renames those books stores them all:

```json
{
  "base": "en-bibleworks",
  "override_names": {
    "DAG": "Dan", "DAN": "DanH",
    "ESG": "Est", "EST": "EstH",
    "JDB": "Jdg", "JDG": "Jda"
  }
}
```

```sh
versiref-bible build lxx_rahlfs.cat -o lxx.db --versification lxx --encoding beta-code --book-style bibleworks-lxx.json
```

`override_names` maps a book ID to the name the file uses for it.
A name can belong to one book only, so the book that held it must be given another (`DanH` and `EstH` here, which the file never uses); `also_recognize` adds names without displacing any.
See the versiref documentation (`uv run versiref docs`) for the style file format.

A style maps names, not chapter numbers: a file that numbers a book differently from the versification (Nehemiah as its own book, where `lxx` has it as chapters 11–23 of 2 Esdras) still has to be edited.

## CLI Options Reference

```text
versiref-bible build [OPTIONS] INPUT_FILE
```

| Option | Description |
| ------ | ----------- |
| `-v`, `--versification` | Named versification of the Bible (required, e.g. `eng`, `lxx`, `cei`) |
| `-o`, `--output` | Output database path (required) |
| `--title` | Human-readable title stored in the database metadata |
| `--book-style` | Reference style whose names map the file's abbreviations: a named style (default: `en-bibleworks`) or the path of a style file (`*.json`) |
| `--encoding` | Text encoding of the input file (default: `utf-8`), or `beta-code` for Beta Code Greek |
| `--keep-markup` | Store verse text verbatim instead of stripping CCAT/BibleWorks markup |
| `--literal-brackets` | Keep square brackets as printed characters instead of reading `[word]` as italics and `[[ ]]` as escaped brackets |

## Stored Metadata

`build` records these keys in the database (view them with `versiref-bible info`):

| Key | Description |
| --- | ----------- |
| `schema_version` | Database schema version |
| `versification` | The versification the verse keys were computed against |
| `source` | The input file name |
| `verse_count` | Number of verses stored |
| `search_folding` | `greek`: the full-text index holds Greek without its diacritics, and searches fold their queries to match |
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
Translator's notes and Strong's tags are stored by `build`; cross-references are returned for callers that want them but are not yet stored.


## Stored Strong's tags

Normal builds store the extracted verse-text tags in a `strongs` table with `verse_key`, zero-based `ordinal`, `lang`, `number`, `word_start`, and `word_end` columns.
A tag's half-open word span indexes the final stripped verse text split on spaces, including an empty span when a tag immediately follows another tag.
The text and spans come from the existing `extract_markup` operation; numbers inside notes are excluded.
Tagged verse text normalizes all whitespace to spaces, so word offsets index `text.split(" ")` even when the input used a tab or a nonbreaking space.
A homograph suffix remains available from `extract_markup`, while concordance queries group tags by language and number.
Repeated source lines replace the previous verse's tags together with its text and notes.

`BuildStats.strongs` and the `strongs_count` metadata key report the number of stored tags.
The key is always present, including zero for a source without tags or a `keep_markup=True` build.
The feature adds schema minor version 3.1 without increasing the core read requirement of 3.0.
