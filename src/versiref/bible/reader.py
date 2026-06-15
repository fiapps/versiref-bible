"""Query a Bible database: show verses by reference and full-text search."""

import sqlite3
from pathlib import Path

from versiref import RefParser, RefStyle, SimpleBibleRef, Versification

from .database import Database
from .models import Verse


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
    label = SimpleBibleRef.for_range(
        verse.book_id, verse.chapter, verse.verse
    ).format(style, versification)
    return f"{label}\t{verse.text}"


def show_verses(
    db_path: str | Path,
    reference: str,
    *,
    style_name: str = "en-sbl",
    from_versification: str | None = None,
) -> tuple[list[Verse], Versification]:
    """Return the verses covered by a Bible reference.

    Args:
        db_path: Path to the Bible database.
        reference: A Bible reference string (parsed by versiref).
        style_name: Reference style used to parse ``reference`` and to label
            output (default ``en-sbl``).
        from_versification: If given, interpret ``reference`` in this
            versification and map it to the database's versification.

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
        verses = db.verses_in_ranges(list(ref.range_keys()))
        return verses, db_vers


def search_verses(
    db_path: str | Path,
    query: str,
    *,
    limit: int = 20,
    scope: str | None = None,
    order: str = "canonical",
    style_name: str = "en-sbl",
) -> tuple[list[Verse], int, Versification]:
    """Full-text search verse text.

    Args:
        db_path: Path to the Bible database.
        query: FTS5 MATCH query.
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
        ValueError: If the scope reference or the FTS query is invalid.

    """
    with Database(db_path) as db:
        db.validate_schema()
        db_vers = _db_versification(db)
        ranges: list[tuple[int, int]] | None = None
        if scope is not None:
            parser = RefParser(RefStyle.named(style_name), db_vers)
            scope_ref = parser.parse(scope, silent=True)
            if scope_ref is None:
                raise ValueError(f"Could not parse scope reference: {scope!r}")
            ranges = list(scope_ref.range_keys())
        try:
            results = db.search(query, limit, ranges, order)
            total = db.count_matches(query, ranges)
        except sqlite3.OperationalError as exc:
            raise ValueError(f"Invalid search query {query!r}: {exc}") from exc
        return results, total, db_vers
