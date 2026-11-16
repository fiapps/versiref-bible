"""Build a SQLite Bible database from a CCAT-format text file."""

import datetime
from pathlib import Path

from versiref import RefParser, RefStyle, Versification

from .beta_code import beta_to_unicode, is_beta_code
from .ccat_markup import extract_markup, has_markup_residue
from .database import PRODUCT_NAME, SCHEMA_VERSION, SEARCH_FOLDING, Database
from .models import BuildStats, Note, Verse

# Bundled style that defines the NABRE's Esther chapter letters (ESG A–F). When
# ``chapter_letters=True``, the build overlays this style's ``chapter_letters``
# onto the chosen book style so a lettered chapter parses; the letter table
# itself lives in versiref, not here (see :func:`build_database`).
_CHAPTER_LETTER_STYLE = "en-nabre"

# A CCAT file numbers every verse explicitly, so the SBL-style "and following"
# notation (``f``/``ff``) never appears in one. Left enabled, versiref reads a
# trailing ``f``/``ff`` on a reference as that notation, which shadows the verse
# *letters* ``f``/``ff`` that the Greek additions to Esther use (Est 1:1f,
# 4:17f, …), folding those sub-verses onto their base verse. The build disables
# the notation by pointing its markers at tokens no reference can equal (a
# sub-verse is one or two lowercase letters, never containing a NUL).
_DISABLED_FOLLOWING_VERSE = "\x00f"
_DISABLED_FOLLOWING_VERSES = "\x00ff"


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
    literal_brackets: bool = False,
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

    The "and following" notation (``f``/``ff``) is disabled while parsing, since
    a CCAT file spells out every verse and never uses it; this frees the verse
    letters ``f``/``ff`` for the Greek additions to Esther (see
    :data:`_DISABLED_FOLLOWING_VERSE`).

    Recognized CCAT/BibleWorks markup (footnote blocks, note anchors, Strong's
    numbers, italics brackets) is stripped from the verse text before storage
    so full-text search sees clean text; pass ``keep_markup=True`` to store
    lines verbatim instead. Stripping is tolerant: unrecognized markup is kept
    and tallied (``BuildStats.suspect_markup``), never fatal.

    The translator's notes of the footnote blocks are stored in the ``notes``
    table (``BuildStats.notes``) rather than discarded. Extraction is part of
    stripping, so a ``keep_markup=True`` build stores none.

    Args:
        input_path: Source ``.cat`` file.
        output_path: Destination database (overwritten if it exists).
        versification: Named versification for the Bible (e.g. ``eng``).
        title: Human-readable title stored in metadata.
        book_style: Named reference style whose recognized names map the
            file's book abbreviations (default ``en-bibleworks``).
        encoding: Text encoding of the input file (e.g., ``cp1252``;
            default ``utf-8``), or ``beta-code`` for a Greek text in Beta
            Code, whose verse text is converted to Unicode (see
            :mod:`versiref.bible.beta_code`).
        keep_markup: Store verse text verbatim instead of stripping
            recognized markup (default ``False``).
        literal_brackets: Leave square brackets as written instead of
            reading ``[word]`` as italics and ``[[``/``]]`` as escapes for a
            printed bracket, for a text whose brackets are all printed ones;
            the rest of the markup is still stripped (default ``False``).
        chapter_letters: Overlay the NABRE Esther chapter letters (ESG A–F,
            from the ``en-nabre`` style) onto ``book_style`` so a lettered
            chapter such as ``Est A:1`` parses (default ``False``).

    Returns:
        A :class:`BuildStats` summary of what was stored and skipped.

    Raises:
        ValueError: If ``output_path`` is the input file.

    """
    input_path = Path(input_path)
    output_path = Path(output_path)
    if output_path.resolve() == input_path.resolve():
        # The output is unlinked and rewritten, which would destroy the source.
        raise ValueError(f"Output path is the input file: {output_path}")

    vers = Versification.named(versification)
    style = RefStyle.named(book_style)
    # Mutate the freshly loaded style in place (named() returns a new instance
    # each call, so this affects no one else). See _DISABLED_FOLLOWING_VERSE.
    style.following_verse = _DISABLED_FOLLOWING_VERSE
    style.following_verses = _DISABLED_FOLLOWING_VERSES
    if chapter_letters:
        # Mutate the freshly loaded style in place (named() returns a new
        # instance each call, so this affects no one else): the switch is just
        # sugar for building with a style that carries the letters.
        style.chapter_letters = RefStyle.named(_CHAPTER_LETTER_STYLE).chapter_letters
    parser = RefParser(style, vers)
    recognized = style.recognized_names

    # Beta Code is ASCII, so the file itself reads as UTF-8; the conversion
    # applies to each line's text, never to its leading reference.
    beta_code = is_beta_code(encoding)
    if beta_code:
        encoding = "utf-8"

    stats = BuildStats()
    verses: dict[int, Verse] = {}
    notes: dict[int, tuple[Note, ...]] = {}

    with input_path.open(encoding=encoding) as handle:
        for raw in handle:
            # A UTF-8 byte-order mark would otherwise be read as part of the
            # first line's book abbreviation, dropping that verse.
            line = raw.rstrip("\n").lstrip("\ufeff")
            if not line.strip():
                continue
            split = _split_reference(line)
            if split is None:
                stats.malformed += 1
                continue
            abbrev, reference, text = split

            # parse fails only on grammar (an unrecognized book or a
            # malformed chapter/verse), never on a verse number that exceeds the
            # versification's chapter length, so off-scheme verses survive to be
            # gated on range_keys below.
            ref = parser.parse(reference, silent=True)
            start = ref.ranges[0].start if ref is not None and ref.ranges else None
            if (
                ref is None
                or start is None
                or start.chapter is None
                or start.verse is None
                # A line holds one verse: a range or list ("Gen 1:4-6") is
                # malformed rather than stored under its first verse.
                or len(ref.ranges) != 1
                or ref.ranges[0].end != start
            ):
                if abbrev in recognized:
                    stats.malformed += 1
                else:
                    stats.unknown_books[abbrev] = stats.unknown_books.get(abbrev, 0) + 1
                continue

            # range_keys yields nothing when the book is not in this
            # versification; that is the off-scheme, warn-and-skip case.
            ranges = list(ref.range_keys())
            if not ranges:
                stats.off_scheme_books[abbrev] = (
                    stats.off_scheme_books.get(abbrev, 0) + 1
                )
                continue

            key = ranges[0][0]
            if key in verses:
                stats.duplicates += 1

            # Keyed like the verse, so a duplicate line replaces the earlier
            # line's notes along with its text.
            notes.pop(key, None)
            if not keep_markup:
                extracted = extract_markup(text, literal_brackets=literal_brackets)
                if extracted.text != text:
                    stats.stripped_markup += 1
                    text = extracted.text
                if has_markup_residue(text):
                    stats.suspect_markup += 1
                if extracted.notes:
                    notes[key] = extracted.notes

            if beta_code:
                # After stripping, so that markup is recognized as written
                # and its tag names are not read as Greek letters.
                text = beta_to_unicode(text)

            verses[key] = Verse(
                key, start.book, start.chapter, start.verse, text, start.subverse
            )

    stats.stored = len(verses)
    stats.notes = sum(len(verse_notes) for verse_notes in notes.values())

    output_path.unlink(missing_ok=True)
    with Database(output_path) as db:
        db.create_schema()
        db.insert_verses(verses.values())
        db.insert_notes(
            (key, note) for key, verse_notes in notes.items() for note in verse_notes
        )
        db.rebuild_fts()
        db.set_metadata("format", PRODUCT_NAME)
        db.set_metadata("schema_version", SCHEMA_VERSION)
        db.set_metadata("versification", versification)
        db.set_metadata("source", input_path.name)
        db.set_metadata("verse_count", str(stats.stored))
        # Tells a search to fold its query the way rebuild_fts folded the
        # index; a database without the key was indexed as written.
        db.set_metadata("search_folding", SEARCH_FOLDING)
        # Always written, zero included: the key's presence says the database
        # has the feature, its value whether this Bible has any such data.
        db.set_metadata("notes_count", str(stats.notes))
        db.set_metadata(
            "built_at", datetime.datetime.now().isoformat(timespec="seconds")
        )
        if title is not None:
            db.set_metadata("title", title)

    return stats
