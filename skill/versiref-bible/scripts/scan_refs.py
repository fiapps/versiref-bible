#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["versiref>=0.5.1", "pyyaml>=6"]
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

    chapter1.md:142:18	Phil 5:1	no such chapter (Phil has 4 chapters)
        | As Paul writes in Phil 5:1, and again in ...

A reference is invalid if *any* of its verse ranges is; when it has more than
one range, the reason names each offending range so the bad part stands out::

    psalter.md:7:5	Ps 1:1; 2:12; 119:1	Ps 2:12: no such verse (Ps 2 has 11 verses)
        | See Ps 1:1; 2:12; 119:1 for the theme.

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


def _start_key(sub_ref, versification: Versification) -> int | None:
    """Return the BBCCCVVV key of a simple reference's first verse."""
    try:
        keys = list(sub_ref.range_keys(versification))
    except TypeError:
        keys = list(sub_ref.range_keys())
    if not keys:
        return None
    first = keys[0]
    return first[0] if isinstance(first, tuple) else first


def invalid_reason(
    versification: Versification,
    vers_name: str,
    book_id: str,
    book_label: str,
    chapter: int,
    verse: int,
) -> str:
    """Explain why a (book, chapter, verse) is invalid under the versification.

    ``book_id`` is the Paratext code used to look up the versification;
    ``book_label`` is the reader-facing name to show (the document's style,
    e.g. ``Ps``), since the output is meant to be read by an LLM.
    """
    if not versification.includes(book_id):
        return f"book not in versification '{vers_name}'"
    chapters = versification.max_verses.get(book_id, [])
    if chapter < 1 or chapter > len(chapters):
        return f"no such chapter ({book_label} has {len(chapters)} chapters)"
    max_verse = chapters[chapter - 1]
    if verse < 1 or verse > max_verse:
        return f"no such verse ({book_label} {chapter} has {max_verse} verses)"
    return "out of range"


def _sub_reason(
    ref_style: RefStyle, versification: Versification, vers_name: str, sub
) -> str | None:
    """Explain why a single-book sub-ref is invalid, or None if it is valid."""
    label = ref_style.names.get(sub.book_id, sub.book_id)
    if not versification.includes(sub.book_id):
        return invalid_reason(versification, vers_name, sub.book_id, label, 0, 0)
    if sub.is_valid(versification):
        return None
    key = _start_key(sub, versification)
    if key is None:
        return "out of range"
    chapter, verse = (key // 1000) % 1000, key % 1000
    return invalid_reason(
        versification, vers_name, sub.book_id, label, chapter, verse
    )


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
    versification: Versification,
    vers_name: str,
    sensitivity: Sensitivity,
) -> list[tuple[int, int, str, str, str]]:
    """Find invalid references in ``text``.

    Returns ``(line, col, reference_text, reason, line_text)`` for each invalid
    reference, in document order. A reference is invalid if *any* of its verse
    ranges is invalid; when it has more than one range, the reason names each
    offending range (e.g. ``Ps 2:12``) so the bad part is easy to spot.
    """
    findings: list[tuple[int, int, str, str, str]] = []
    for ref, start, end in parser.scan_string(text, sensitivity=sensitivity):
        ranges = list(ref.range_refs())
        reasons: list[str] = []
        for range_ref in ranges:
            reason = _sub_reason(
                ref_style, versification, vers_name, range_ref.simple_refs[0]
            )
            if reason is None:
                continue
            if len(ranges) > 1:
                reason = f"{range_ref.format(ref_style)}: {reason}"
            reasons.append(reason)
        if not reasons:
            continue
        line_no, col, line_text = _line_col(text, start)
        findings.append((line_no, col, text[start:end], "; ".join(reasons), line_text))
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
            text, parser, ref_style, versification, vers_name, sensitivity
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
