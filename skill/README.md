# Skill: versiref-bible

A Claude Code skill that gives an agent access to versiref-bible (read and search Bibles) and a
procedure plus helper script for finding and fixing invalid Scripture references in Markdown.

The skill is maintained here, alongside the package it documents.
To use it, install it into your skills directory.

## Install (personal skill, available in every repo)

Symlink it so edits here stay live:

```sh
ln -s "$(pwd)/skill/versiref-bible" ~/.claude/skills/versiref-bible
```

Or copy it if you prefer a snapshot:

```sh
cp -R skill/versiref-bible ~/.claude/skills/versiref-bible
```

For a single project instead, link it into that project's `.claude/skills/` rather than
`~/.claude/skills/`.

## Layout

```text
versiref-bible/
  SKILL.md                       # overview + commands; loaded when the skill triggers
  references/
    checking-references.md       # full invalid-reference procedure (progressive disclosure)
  scripts/
    scan_refs.py                 # scan Markdown for invalid refs with source locations
```

## Requirements

- [`uv`](https://docs.astral.sh/uv/) on `PATH`.
  `scan_refs.py` carries PEP 723 inline metadata, so `uv run scripts/scan_refs.py …` fetches its
  dependencies (`versiref`, `pyyaml`) automatically.
- `versiref-bible` reachable via `uvx versiref-bible` (from PyPI, or
  `uvx --from git+https://github.com/fiapps/versiref-bible versiref-bible`).
- `versiref-search` for the `analyze` step, if you use it.
