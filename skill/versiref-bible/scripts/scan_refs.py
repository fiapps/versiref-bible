#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["versiref>=0.8.1", "pyyaml>=6"]
# ///
"""Scan Markdown for invalid Bible references, reporting source-file locations.

versiref-search's ``index`` already detects out-of-range references while
building a database, but its warnings do not say *where* in the source the
reference is, and the positions it stores point into reconstructed Markdown
blocks, not the original file. This script closes that gap: it scans the
**original** Markdown with versiref so every reported position maps to the file
you edit.

It resolves style and versification the same way ``versiref-search index`` does,
so point it at the same config/metadata you already use:

    uv run scan_refs.py -c config.yaml -m metadata.yaml chapter1.md

Each invalid reference is printed as a single tab-separated record::

    chapter1.md:142:18	Phil 5:1	Phil has no chapter 5 (only 4 chapters)
        | As Paul writes in Phil 5:1, and again in ...

A reference is invalid if *any* of its verse ranges is; when more than one
range is invalid, each reason is reported, joined by "; ", so every bad part
stands out::

    psalter.md:7:5	Ps 1:1; 2:99; 200:1	Ps 2 has no verse 99 (only 12 verses); Ps has no chapter 200 (only 150 chapters)
        | See Ps 1:1; 2:99; 200:1 for the theme.

Validity is structural only — a reference that names a chapter or verse outside
the versification, or a book outside its canon. A reference that is structurally
valid but cites the *wrong* verse (e.g. transposed digits that still land on a
real verse) cannot be caught here; compare the quoted text against the verse
with ``versiref-bible search``/``show`` to find those.

Exit status: 0 if no invalid references were found, 1 if any were found
(linter-style), 2 on a usage or configuration error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml
from versiref import RefParser, RefStyle, Sensitivity, Versification


class ConfigError(Exception):
    """A style/versification could not be resolved from the inputs."""


def _front_matter(text: str) -> str:
    """Return the YAML front-matter block if ``text`` opens with one.

    A Markdown file may carry its settings in a ``---``-delimited front-matter
    block followed by prose; bare YAML has no such delimiters. If the text
    starts with a ``---`` line, return only the block up to the closing ``---``
    (or ``...``); otherwise return the text unchanged so plain YAML still loads.
    """
    lines = text.splitlines(keepends=True)
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() in ("---", "..."):
                return "".join(lines[1:i])
    return text


def _load_yaml(path: Path) -> dict:
    """Load a YAML mapping from a bare-YAML or Markdown-front-matter file."""
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(_front_matter(text))
    if not isinstance(data, dict):
        raise ConfigError(f"{path} does not contain a YAML mapping.")
    return data


def resolve_settings(
    config_file: Path | None,
    metadata_file: Path | None,
    style_override: str | None,
    versification_override: str | None,
    sensitivity_override: str | None,
) -> tuple[RefStyle, Versification, str, Sensitivity]:
    """Resolve (style, versification, versification_name, sensitivity).

    Mirrors how ``versiref-search index`` resolves these so this scan flags the
    same references the indexer would: CLI overrides win, then the config file,
    then the metadata file; style defaults to ``en-cmos_short`` and sensitivity
    to ``verse``.
    """
    config: dict = _load_yaml(config_file) if config_file else {}

    # Metadata: --metadata wins, else config's `metadata` (relative to config).
    meta: dict = {}
    meta_path = metadata_file
    if meta_path is None and config.get("metadata"):
        base = config_file.parent if config_file else Path.cwd()
        meta_path = base / str(config["metadata"])
    if meta_path is not None:
        meta = _load_yaml(meta_path)

    # Versification: override, else config, else metadata.
    vers_name = versification_override or config.get("versification") or meta.get(
        "versification"
    )
    if not vers_name:
        raise ConfigError(
            "No versification given. Supply --versification, or a config/metadata "
            "file with a 'versification' key."
        )
    versification = Versification.named(str(vers_name))

    # Style: override (named only), else config (named or inline dict), else default.
    if style_override is not None:
        ref_style = RefStyle.named(style_override)
    else:
        style_value = config.get("style", "en-cmos_short")
        if isinstance(style_value, dict):
            ref_style = RefStyle.from_dict(style_value)
        else:
            ref_style = RefStyle.named(str(style_value))

    # Sensitivity: override, else config, else verse.
    sens_value = sensitivity_override or config.get("parser_sensitivity", "verse")
    try:
        sensitivity = Sensitivity[str(sens_value).upper()]
    except KeyError as exc:
        raise ConfigError(
            f"Invalid sensitivity {sens_value!r}: use verse, chapter, or book."
        ) from exc

    return ref_style, versification, str(vers_name), sensitivity


def _line_col(text: str, pos: int) -> tuple[int, int, str]:
    """Return (1-based line, 1-based column, full line text) for an offset."""
    line_start = text.rfind("\n", 0, pos) + 1
    line_end = text.find("\n", pos)
    if line_end == -1:
        line_end = len(text)
    line_no = text.count("\n", 0, pos) + 1
    return line_no, pos - line_start + 1, text[line_start:line_end]


def scan_text(
    text: str,
    parser: RefParser,
    ref_style: RefStyle,
    sensitivity: Sensitivity,
) -> list[tuple[int, int, str, str, str]]:
    """Find invalid references in ``text``.

    Returns ``(line, col, reference_text, reason, line_text)`` for each invalid
    reference, in document order. Validity — and the explanatory reason — comes
    from ``BibleRef.invalid_reason``: a reference is invalid if *any* of its
    verse ranges is, and when more than one range is invalid each reason is
    reported, joined by "; ", so every bad part stands out. ``ref_style`` is
    passed so books are named in the document's style (e.g. ``Ps``).
    """
    findings: list[tuple[int, int, str, str, str]] = []
    for ref, start, end in parser.scan_string(text, sensitivity=sensitivity):
        reason = ref.invalid_reason(ref_style)
        if reason is None:
            continue
        line_no, col, line_text = _line_col(text, start)
        findings.append((line_no, col, text[start:end], reason, line_text))
    return findings


def main(argv: list[str] | None = None) -> int:
    """Entry point: scan the given Markdown files and report invalid references."""
    ap = argparse.ArgumentParser(
        description="Report invalid Bible references in Markdown, with source locations."
    )
    ap.add_argument("files", nargs="+", type=Path, help="Markdown files to scan.")
    ap.add_argument("-c", "--config", type=Path, help="versiref-search YAML config.")
    ap.add_argument("-m", "--metadata", type=Path, help="versiref-search YAML metadata.")
    ap.add_argument("--style", help="Named reference style (overrides config).")
    ap.add_argument(
        "--versification", help="Versification name (overrides config/metadata)."
    )
    ap.add_argument(
        "--sensitivity",
        choices=["verse", "chapter", "book"],
        help="Scanner sensitivity (overrides config; default verse).",
    )
    args = ap.parse_args(argv)

    try:
        ref_style, versification, vers_name, sensitivity = resolve_settings(
            args.config, args.metadata, args.style, args.versification, args.sensitivity
        )
    except (ConfigError, LookupError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    parser = RefParser(ref_style, versification)
    total = 0
    for path in args.files:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
        for line_no, col, snippet, reason, line_text in scan_text(
            text, parser, ref_style, sensitivity
        ):
            total += 1
            print(f"{path}:{line_no}:{col}\t{snippet}\t{reason}")
            print(f"    | {line_text.strip()}")

    plural = "" if total == 1 else "s"
    print(
        f"{total} invalid reference{plural} in {len(args.files)} file(s) "
        f"(versification: {vers_name}).",
        file=sys.stderr,
    )
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
