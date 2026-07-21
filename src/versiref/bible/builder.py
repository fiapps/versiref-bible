"""Build a SQLite Bible database from a CCAT-format text file."""

import datetime
from pathlib import Path

from versiref import RefParser, RefStyle, Versification

from .database import PRODUCT_NAME, SCHEMA_VERSION, Database
from .ccat_markup import has_markup_residue, strip_markup
from .models import BuildStats, Verse

# Bundled style that defines the NABRE's Esther chapter letters (ESG A–F). When
# ``chapter_letters=True``, the build overlays this style's ``chapter_letters``
# onto the chosen book style so a lettered chapter parses; the letter table
# itself lives in versiref, not here (see :func:`build_database`).
_CHAPTER_LETTER_STYLE = "en-nabre"


def _split_reference(line: str) -> tuple[str, str, str] | None:
    """Split a CCAT line ``Abbrev C:V text`` into ``(abbrev, reference, text)``.

    ``reference`` is ``"Abbrev C:V"`` for the parser; ``text`` is the rest of
    the line verbatim (markup handling happens later, see
    :func:`build_database`). Returns ``None`` if the line lacks the ``Abbrev
    C:V`` shape (no book token, or no ``:`` in the chapter/verse token).
    """
    abbrev, _, rest = line.partition(" ")
    cv, _, text = rest.partition(" ")
    if not abbrev or ":" not in cv:
        return None
    return abbrev, f"{abbrev} {cv}", text


def build_database(
    input_path: str | Path,
    output_path: str | Path,
    *,
    versification: str,
    title: str | None = None,
    book_style: str = "en-bibleworks",
    encoding: str = "utf-8",
    keep_markup: bool = False,
    chapter_letters: bool = False,
) -> BuildStats:
    """Build a Bible database from a CCAT-format ``.cat`` file.

    Each non-blank line is read as ``Abbrev C:V text``. The leading
    ``Abbrev C:V`` is resolved to a book ID, chapter, and verse by parsing it
    with ``book_style`` (via :class:`~versiref.RefParser`), and a verse key is
    computed under ``versification``. Lines whose abbreviation is unrecognized
    (e.g. the Sirach prologue ``Sip``) or whose book is absent from the
    versification are warned-and-skipped — see :class:`BuildStats`.

    Parsing (rather than a bare abbreviation lookup) lets the file use the
    book's own chapter styling, including the NABRE-style chapter letters for
    the Additions to Esther (``Est A:1`` → ESG). Those letters are not in the
    default ``en-bibleworks`` style, so pass ``chapter_letters=True`` to overlay
    them (sourced from the bundled ``en-nabre`` style) onto ``book_style``.

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
        chapter_letters: Overlay the NABRE Esther chapter letters (ESG A–F,
            from the ``en-nabre`` style) onto ``book_style`` so a lettered
            chapter such as ``Est A:1`` parses (default ``False``).

    Returns:
        A :class:`BuildStats` summary of what was stored and skipped.

    """
    input_path = Path(input_path)
    output_path = Path(output_path)

    vers = Versification.named(versification)
    style = RefStyle.named(book_style)
    if chapter_letters:
        # Mutate the freshly loaded style in place (named() returns a new
        # instance each call, so this affects no one else): the switch is just
        # sugar for building with a style that carries the letters.
        style.chapter_letters = RefStyle.named(_CHAPTER_LETTER_STYLE).chapter_letters
    parser = RefParser(style, vers)
    recognized = style.recognized_names

    stats = BuildStats()
    verses: dict[int, Verse] = {}

    with input_path.open(encoding=encoding) as handle:
        for raw in handle:
            line = raw.rstrip("\n")
            if not line.strip():
                continue
            split = _split_reference(line)
            if split is None:
                stats.malformed += 1
                continue
            abbrev, reference, text = split

            # parse_simple fails only on grammar (an unrecognized book or a
            # malformed chapter/verse), never on a verse number that exceeds the
            # versification's chapter length, so off-scheme verses survive to be
            # gated on range_keys below.
            ref = parser.parse_simple(reference, silent=True)
            if ref is None:
                if abbrev in recognized:
                    stats.malformed += 1
                else:
                    stats.unknown_books[abbrev] = stats.unknown_books.get(abbrev, 0) + 1
                continue

            # range_keys yields nothing when the book is not in this
            # versification; that is the off-scheme, warn-and-skip case.
            ranges = list(ref.range_keys(vers))
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
            range_ref = ref.ranges[0]
            if key in verses:
                stats.duplicates += 1
            verses[key] = Verse(
                key, ref.book_id, range_ref.start_chapter, range_ref.start_verse, text
            )

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
