---
name: versiref-bible
description: >-
  Look up and full-text search Bibles stored as SQLite (versiref-bible), and find or fix
  invalid or mistaken Scripture references in Markdown documents. Use when asked to retrieve
  verses by reference, search a Bible for a phrase, identify what a wrong reference should be,
  or validate/correct Scripture citations in a manuscript.
---

# versiref-bible

This skill gives you two capabilities built on the [versiref](https://github.com/fiapps/versiref)
ecosystem:

1. **Read and search Bibles** stored as SQLite databases, by reference or full-text search.
2. **Find and fix invalid Scripture references** in a Markdown document, with exact source
   locations so you can edit the original file.

## Reading and searching Bibles

Run the CLI with `uvx` — no install step:

```sh
uvx versiref-bible --help
```

If the package is not on PyPI in this environment, run it from the repository instead:

```sh
uvx --from git+https://github.com/fiapps/versiref-bible versiref-bible --help
```

### Naming a Bible

Commands take a Bible as their first argument, either as a path to a `.db` file or as a bare
**name** looked up on a search path.
A name resolves to `<name>.db` across the directories in the `VERSIREF_BIBLE_PATH` environment
variable (`:`-separated, like `PATH`); when it is unset, a per-user data directory is searched
(`~/Library/Application Support/versiref-bible` on macOS, `~/.local/share/versiref-bible` on
Linux).

Start by listing what is available:

```sh
uvx versiref-bible list
```

Each line is `name⇥versification⇥verses⇥title`.
The first column is the name you pass to the commands below.

### Commands

```sh
# Print the verses a reference covers (one per line as `reference<TAB>text`)
uvx versiref-bible show kjv "John 3:16-18"

# Full-text search verse text (SQLite FTS5 syntax)
uvx versiref-bible search kjv '"living water"' --limit 10
uvx versiref-bible search kjv "faith" --in "Romans"      # scope to a book/range

# Metadata and verse count for one Bible
uvx versiref-bible info kjv
```

`show` and `search` take `--style` (reference style for input and output labels, default
`en-sbl`) and, for `show`, `--from-versification` to map a reference in from another scheme.
Search defaults to canonical verse order; add `--order relevance` for bm25 ranking.

## Working with references directly: the `versiref` CLI

The `versiref` package installs a `versiref` command for reference operations that need no Bible
database — listing the bundled schemes, parsing, validating, and converting a reference between
versifications.
Every operation command takes `--style` (default `en-cmos_short`; pass `en-sbl` to match this
skill's Bibles), `-v/--versification` (default `eng`), and `--json` for structured output.

```sh
# Discover the valid scheme names to pass elsewhere
uvx versiref list versifications              # cei, eng, lxx, nabre, nova_vulgata, org, vulgata, ...
uvx versiref list styles --pattern 'en-*'

# Normalize or inspect a single reference
uvx versiref parse "Jn 3:16-18" --style en-sbl
uvx versiref parse "Ps 119:1ff" --json        # structured book/chapter/verse breakdown

# Check one reference without writing a config file
uvx versiref validate "Phil 5:1" --style en-sbl -v eng   # exit 0 valid, 1 out of range, 2 unparseable

# Map a reference between versifications (Psalm numbering, deuterocanon)
uvx versiref convert "Ps 50:3" --style en-sbl --from lxx --to eng   # -> Ps 51:1
```

`validate` is the quick, single-reference counterpart to `scripts/scan_refs.py`: use it to
spot-check one citation, and the scanner to sweep a whole document.
`convert` resolves the most common "looks invalid but isn't" case — a reference that is correct
under a different Psalm or deuterocanon numbering (see the checking-references procedure below).

## Bundled documentation

Each sibling package ships its own Markdown docs and prints the containing directory with a `docs`
subcommand — read these when you need behavior this skill does not spell out:

```sh
uvx versiref docs           # reference parsing, versifications, and the full versiref CLI (cli.md, api.md)
uvx versiref-search docs    # analyze/index/search a corpus (indexing.md, searching.md)
uvx versiref-bible docs     # building and querying Bible databases (building.md, querying.md)
```

Pass a filename to get the path to one file, e.g. `uvx versiref docs cli.md`.

## Finding and fixing invalid Scripture references

When the task is to validate the Scripture references in a document — or to work out what a
mistaken reference should be — follow the procedure in
[references/checking-references.md](references/checking-references.md).
In short:

1. Pick the right style and versification with `versiref-search analyze` (an invalid-looking
   reference is often just a versification mismatch — e.g. Psalm numbering).
2. Run the bundled `scripts/scan_refs.py` to list every structurally invalid reference with its
   **source file, line, and column** and a reason.
3. For each one, use `versiref-bible show`/`search` to determine the correct reference, then
   edit the original Markdown.

```sh
uv run scripts/scan_refs.py -c config.yaml -m metadata.yaml chapter1.md
```

The script reuses the same style/versification settings as `versiref-search index`, so it flags
the same references the indexer would, and it scans the original Markdown so positions map to
the file you edit.
Read the method doc before starting — it covers the part the script cannot catch: a reference
that is structurally valid but cites the *wrong* verse.
