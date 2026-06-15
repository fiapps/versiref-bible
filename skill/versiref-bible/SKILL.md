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
