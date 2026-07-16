"""Build a SQLite Bible database from a CCAT-format text file."""

import datetime
from pathlib import Path

from versiref import RefStyle, SimpleBibleRef, Versification

from .database import PRODUCT_NAME, SCHEMA_VERSION, Database
from .ccat_markup import has_markup_residue, strip_markup
from .models import BuildStats, Verse


def _parse_line(line: str) -> tuple[str, int, int, str] | None:
    """Parse one CCAT line ``Abbrev C:V text`` into its components.

    Returns ``(abbrev, chapter, verse, text)`` or ``None`` if the line does not
    match the expected shape. ``text`` is the rest of the line verbatim; any
    markup handling happens later (see :func:`build_database`).
    """
    abbrev, _, rest = line.partition(" ")
    cv, _, text = rest.partition(" ")
    if not abbrev or ":" not in cv:
        return None
    chapter_s, _, verse_s = cv.partition(":")
    try:
        return abbrev, int(chapter_s), int(verse_s), text
    except ValueError:
        return None


def build_database(
    input_path: str | Path,
    output_path: str | Path,
    *,
    versification: str,
    title: str | None = None,
    book_style: str = "en-bibleworks",
    encoding: str = "utf-8",
    keep_markup: bool = False,
) -> BuildStats:
    """Build a Bible database from a CCAT-format ``.cat`` file.

    Each non-blank line is read as ``Abbrev C:V text``. The abbreviation is
    mapped to a Paratext book ID via the ``book_style`` recognized names, and a
    verse key is computed under ``versification``. Lines whose abbreviation is
    unrecognized (e.g. the Sirach prologue ``Sip``) or whose book is absent from
    the versification are warned-and-skipped — see :class:`BuildStats`.

    Recognized CCAT/BibleWorks markup (footnote blocks, note anchors, Strong's
    numbers, italics brackets) is stripped from the verse text before storage
    so full-text search sees clean text; pass ``keep_markup=True`` to store
    lines verbatim instead. Stripping is tolerant: unrecognized markup is kept
    and tallied (``BuildStats.suspect_markup``), never fatal.

    Args:
        input_path: Source ``.cat`` file.
        output_path: Destination database (overwritten if it exists).
        versification: Named versification for the Bible (e.g. ``eng``).
        title: Human-readable title stored in metadata.
        book_style: Named reference style whose recognized names map the
            file's book abbreviations (default ``en-bibleworks``).
        encoding: Text encoding of the input file (e.g., ``cp1252``;
            default ``utf-8``).
        keep_markup: Store verse text verbatim instead of stripping
            recognized markup (default ``False``).

    Returns:
        A :class:`BuildStats` summary of what was stored and skipped.

    """
    input_path = Path(input_path)
    output_path = Path(output_path)

    vers = Versification.named(versification)
    recognized = RefStyle.named(book_style).recognized_names

    stats = BuildStats()
    verses: dict[int, Verse] = {}

    with input_path.open(encoding=encoding) as handle:
        for raw in handle:
            line = raw.rstrip("\n")
            if not line.strip():
                continue
            parsed = _parse_line(line)
            if parsed is None:
                stats.malformed += 1
                continue
            abbrev, chapter, verse, text = parsed

            book_id = recognized.get(abbrev)
            if book_id is None:
                stats.unknown_books[abbrev] = stats.unknown_books.get(abbrev, 0) + 1
                continue

            # range_keys yields nothing when the book is not in this
            # versification; that is the off-scheme, warn-and-skip case.
            ranges = list(SimpleBibleRef.for_range(book_id, chapter, verse).range_keys(vers))
            if not ranges:
                stats.off_scheme_books[abbrev] = (
                    stats.off_scheme_books.get(abbrev, 0) + 1
                )
                continue

            if not keep_markup:
                cleaned = strip_markup(text)
                if cleaned != text:
                    stats.stripped_markup += 1
                    text = cleaned
                if has_markup_residue(text):
                    stats.suspect_markup += 1

            key = ranges[0][0]
            if key in verses:
                stats.duplicates += 1
            verses[key] = Verse(key, book_id, chapter, verse, text)

    stats.stored = len(verses)

    output_path.unlink(missing_ok=True)
    with Database(output_path) as db:
        db.create_schema()
        db.insert_verses(verses.values())
        db.rebuild_fts()
        db.set_metadata("format", PRODUCT_NAME)
        db.set_metadata("schema_version", SCHEMA_VERSION)
        db.set_metadata("versification", versification)
        db.set_metadata("source", input_path.name)
        db.set_metadata("verse_count", str(stats.stored))
        db.set_metadata("built_at", datetime.datetime.now().isoformat(timespec="seconds"))
        if title is not None:
            db.set_metadata("title", title)

    return stats
