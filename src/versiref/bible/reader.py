"""Query a Bible database: show verses by reference and full-text search."""

import sqlite3
from dataclasses import replace
from pathlib import Path

from versiref import BibleRef, RefParser, RefStyle, Versification

from .database import SEARCH_FOLDING, Database
from .greek import fold_greek
from .models import Note, Verse


def _db_versification(db: Database) -> Versification:
    """Return the versification a database was built with."""
    name = db.get_metadata("versification")
    if name is None:
        raise ValueError("Database has no 'versification' metadata; rebuild it.")
    return Versification.named(name)


def format_verse(verse: Verse, style: RefStyle, versification: Versification) -> str:
    """Format a verse as ``reference<TAB>text`` for plain-text output.

    The reference label is formatted with ``style`` under ``versification``;
    verse text is single-line in CCAT, so the tab keeps the line unambiguous.
    """
    return f"{_verse_label(verse, style, versification)}\t{verse.text}"


def format_note(
    verse: Verse, note: Note, style: RefStyle, versification: Versification
) -> str:
    """Format a verse's note as ``reference note label<TAB>text``.

    The note's label is folded into the first field, so the line keeps the
    two-field shape of a verse line and still says which verse it belongs to.
    """
    label = _verse_label(verse, style, versification)
    return f"{label} note {note.label}\t{note.text}"


def _verse_label(verse: Verse, style: RefStyle, versification: Versification) -> str:
    """Format a verse's reference with ``style`` under ``versification``."""
    return BibleRef.for_range(
        verse.book_id,
        verse.chapter,
        verse.verse,
        start_subverse=verse.subverse,
        versification=versification,
    ).format(style)


def show_verses(
    db_path: str | Path,
    reference: str,
    *,
    style_name: str = "en-sbl",
    from_versification: str | None = None,
    notes: bool = False,
) -> tuple[list[Verse], Versification]:
    """Return the verses covered by a Bible reference.

    Args:
        db_path: Path to the Bible database.
        reference: A Bible reference string (parsed by versiref).
        style_name: Reference style used to parse ``reference`` and to label
            output (default ``en-sbl``).
        from_versification: If given, interpret ``reference`` in this
            versification and map it to the database's versification.
        notes: Fill in each verse's translator's notes (``Verse.notes``).

    Returns:
        ``(verses, db_versification)`` — verses in canonical order plus the
        database's versification (for labelling).

    Raises:
        ValueError: If the reference cannot be parsed.

    """
    with Database(db_path) as db:
        db.validate_schema()
        db_vers = _db_versification(db)
        source_vers = (
            Versification.named(from_versification)
            if from_versification is not None
            else db_vers
        )
        parser = RefParser(RefStyle.named(style_name), source_vers)
        ref = parser.parse(reference, silent=True)
        if ref is None:
            raise ValueError(f"Could not parse reference: {reference!r}")
        if from_versification is not None:
            mapped = ref.map_to(db_vers)
            if mapped is None:
                raise ValueError(
                    f"Could not map {reference!r} from {from_versification} to "
                    f"the database's versification."
                )
            ref = mapped
        ranges = list(ref.range_keys())
        verses = db.verses_in_ranges(ranges)
        if notes:
            by_key = db.notes_in_ranges(ranges)
            verses = [replace(v, notes=by_key.get(v.key, ())) for v in verses]
        return verses, db_vers


def _fts_phrase(text: str) -> str:
    """Quote text as an FTS5 phrase, so none of it is read as query syntax.

    The phrase matches the words of ``text`` in sequence; punctuation between
    them is ignored, as it is when the text is indexed.
    """
    return '"' + text.replace('"', '""') + '"'


def search_verses(
    db_path: str | Path,
    query: str | None = None,
    *,
    phrase: str | None = None,
    limit: int = 20,
    scope: str | None = None,
    order: str = "canonical",
    style_name: str = "en-sbl",
) -> tuple[list[Verse], int, Versification]:
    """Full-text search verse text.

    Args:
        db_path: Path to the Bible database.
        query: FTS5 search expression (punctuation and words such as
            ``AND``, ``OR``, and ``NOT`` are query syntax); use ``phrase`` for
            text to be matched as written.
        phrase: Literal text to search for: matches its words in sequence and
            reads nothing as query syntax. Exactly one of ``query`` and
            ``phrase`` must be given.
        limit: Maximum number of verses to return.
        scope: Optional Bible reference restricting the search (parsed in the
            database's versification).
        order: ``"canonical"`` for verse (Bible) order, or ``"relevance"`` for
            bm25 rank (best first, tie-broken by verse order).
        style_name: Reference style used to parse ``scope`` and to label output.

    Returns:
        ``(verses, total_matches, db_versification)`` where ``total_matches``
        is the match count before ``limit`` was applied.

    Raises:
        ValueError: If the scope reference or the FTS query is invalid, or if
            not exactly one of ``query`` and ``phrase`` is given.

    """
    if (query is None) == (phrase is None):
        raise ValueError("Exactly one of query and phrase must be provided")
    match = query if query is not None else _fts_phrase(phrase or "")
    with Database(db_path) as db:
        db.validate_schema()
        db_vers = _db_versification(db)
        if db.get_metadata("search_folding") == SEARCH_FOLDING:
            # The index holds Greek stripped of its diacritics; a database
            # built before that was indexed as written, and is searched so.
            match = fold_greek(match)
        ranges: list[tuple[int, int]] | None = None
        if scope is not None:
            parser = RefParser(RefStyle.named(style_name), db_vers)
            scope_ref = parser.parse(scope, silent=True)
            if scope_ref is None:
                raise ValueError(f"Could not parse scope reference: {scope!r}")
            ranges = list(scope_ref.range_keys())
        try:
            results = db.search(match, limit, ranges, order)
            total = db.count_matches(match, ranges)
        except sqlite3.OperationalError as exc:
            raise ValueError(
                f"Invalid search query {match!r} ({exc}); to search for the "
                "text as written, use a phrase search (--phrase) instead"
            ) from exc
        return results, total, db_vers
