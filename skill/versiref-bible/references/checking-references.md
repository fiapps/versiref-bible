# Finding and Fixing Invalid Scripture References

This is the procedure for validating the Bible references in a Markdown document and correcting
the wrong ones.
It uses three sibling tools: `versiref-search` to choose the scheme and (optionally) build an
index, the bundled `scan_refs.py` to locate invalid references in the source, and
`versiref-bible` to determine the correct reference.

## Two kinds of error

Distinguish them, because only the first can be detected mechanically:

1. **Structurally invalid** — the reference names a chapter or verse that does not exist
   (`Phil 5:1`; Philippians has four chapters), or a book outside the versification's canon.
   `scan_refs.py` finds these deterministically.
2. **Valid but mismatched** — the reference parses and exists, but it cites the *wrong* verse:
   transposed digits that still land on a real verse (`3:16` written as `3:6`), or the wrong
   book entirely.
   No tool can flag these; you catch them by comparing the quoted text to the cited verse
   (Step 4).

## Step 1 — Pick the style and versification

A reference that looks invalid is often correct under a different versification — Psalm
numbering and the deuterocanon are the usual culprits.
Lock the scheme first, or you will chase false positives.

Run `versiref-search analyze` on the document:

```sh
versiref-search analyze chapter1.md
```

It reports which book-name abbreviation sets the text needs and ranks named versifications by
how many references are valid in each.
Use the result to write (or confirm) the `config.yaml` and `metadata.yaml` you would pass to
`versiref-search index` — the same files drive the scan in Step 2.
A minimal pair:

```yaml
# metadata.yaml
title: Commentary on Romans
versification: eng
```

```yaml
# config.yaml
metadata: metadata.yaml
style: en-sbl
parser_sensitivity: verse
```

## Step 2 — Locate the invalid references

Run the bundled scanner with the same config/metadata:

```sh
uv run scripts/scan_refs.py -c config.yaml -m metadata.yaml chapter1.md
```

You can scan several files at once, and override settings without a config file:

```sh
uv run scripts/scan_refs.py --style en-sbl --versification eng ch1.md ch2.md ch3.md
```

Each invalid reference prints as a tab-separated record plus the source line:

```text
chapter1.md:142:18	Phil 5:1	no such chapter (PHP has 4 chapters)
    | As Paul writes in Phil 5:1, the believer presses on.
```

The fields are `file:line:column`, the reference text, and the reason.
The position is into the **original Markdown**, so it is exactly where you will edit.
Exit status is 1 when any invalid reference is found, 0 when the file is clean, and 2 on a
configuration error.

Why a separate scanner: `versiref-search index` already detects these references, but its
warnings do not give locations, and the positions it stores in the database point into
reconstructed Markdown blocks rather than the source file.
`scan_refs.py` resolves style and versification the same way the indexer does, so it flags the
same references — it only adds the source location the indexer omits.

## Step 3 — Determine the correct reference

For each flagged reference, read the surrounding context (the printed line, and more of the file
if needed) and work out what was intended.
Two complementary moves, using whichever Bible fits the document:

**Confirm a guess.**
If the context makes the intended reference obvious (a typo'd chapter, a digit dropped), fetch
your candidate and check that its text fits:

```sh
uvx versiref-bible show kjv "Phil 4:1"
```

**Search for the wording.**
If the document quotes or paraphrases the verse, search the quoted phrase to find where it
actually comes from:

```sh
uvx versiref-bible search kjv '"I press toward the mark"'
```

The matching verse's reference is the correction.
Prefer a distinctive phrase; use `--order relevance` for multi-word queries.

Then edit the original Markdown at the reported `file:line`, replacing only the reference.

## Step 4 — Spot-check for mismatched references (optional but valuable)

Step 2 cannot catch a reference that is structurally valid but wrong.
To find these, sample references whose context includes a quotation and verify the quotation
against the cited verse:

```sh
uvx versiref-bible show kjv "Romans 8:28"      # does the verse match the quoted text?
```

If the quoted wording belongs to a different verse, search for it as in Step 3 and correct the
reference.
This pass is judgment-driven; focus on references attached to direct quotations, where a
mismatch is both most likely and most consequential.

## Notes

- **Sensitivity.**
  The scanner defaults to verse-level references.
  Set `parser_sensitivity: chapter` (or `--sensitivity chapter`) to also check whole-chapter
  references like `Romans 17`.
- **False positives.**
  Scanning raw Markdown is not syntax-aware, so a reference-like string inside a code block or a
  URL can appear.
  These are rare for Scripture references; just skip any that are not real citations.
- **Choosing the Bible.**
  Use `uvx versiref-bible list` to see which Bibles are available and in which versification, and
  prefer one whose versification matches the document.
