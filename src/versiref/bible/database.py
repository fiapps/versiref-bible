"""Database schema and operations for versiref-bible."""

import sqlite3
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from .greek import fold_greek
from .models import Note, Verse

# Identifies databases produced by this package, distinguishing them from
# other versiref-ecosystem SQLite files (e.g. versiref-search) that share the
# "schema_version" key. Written to the metadata "format" key at build time.
PRODUCT_NAME = "versiref-bible"

# Schema contract version (major.minor), independent of the package version.
# Minor bumps are additive (new tables/columns); a major bump signals a
# breaking change. Code requiring X.Y accepts any database whose major equals
# X and whose minor is >= Y.
#
# SCHEMA_VERSION is what a build writes. REQUIRED_SCHEMA_VERSION is what the
# core reads (show, search, info) need, and stays put when a minor bump adds a
# feature, so that an older database keeps working; the feature's own reads
# are gated separately (see FEATURES and Database.require_feature).
#
# 2.1: verses.subverse; the notes table.
# 3.0: verse keys from versiref 0.14.0, which renumbered nabre (Esther's
#      lettered chapters joined EST, so every later book moved down one) and
#      reordered Greek Esther 1:1 in lxx and cei. A 2.x database's keys no
#      longer match the references parsed against them, so it must be rebuilt.
SCHEMA_VERSION = "3.0"
REQUIRED_SCHEMA_VERSION = "3.0"

# Feature -> (description, schema version that introduced it, first package
# version to build it). Empty at a major version's start: everything 3.0 has is
# part of the baseline that REQUIRED_SCHEMA_VERSION checks.
FEATURES: dict[str, tuple[str, str, str]] = {}


# Value of the "search_folding" metadata key: the full-text index holds Greek
# folded by fold_greek, and a search folds its query to match.
SEARCH_FOLDING = "greek"


class IncompatibleDatabaseError(Exception):
    """Raised when a database is not a compatible versiref-bible Bible."""


def _parse_schema_version(value: str) -> tuple[int, int]:
    """Parse a ``"major.minor"`` schema version into an ``(int, int)`` tuple.

    Raises:
        ValueError: If the value is not two dot-separated integers.

    """
    parts = value.split(".")
    if len(parts) != 2:
        raise ValueError("expected 'major.minor'")
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        raise ValueError("major and minor must be integers") from None


SCHEMA_SQL = """
-- Key-value metadata (title, versification, source, etc.)
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- One row per Bible verse. verse_key is the BBCCCVVVSS integer computed under
-- the database's versification (the trailing SS is a subverse ordinal); it
-- doubles as the FTS5 rowid.
CREATE TABLE IF NOT EXISTS verses (
    verse_key INTEGER PRIMARY KEY,
    book_id   TEXT NOT NULL,
    chapter   INTEGER NOT NULL,
    verse     INTEGER NOT NULL,
    text      TEXT NOT NULL,
    -- Letters of an inserted verse (the "a" of ESG 4:17a); '' otherwise.
    subverse  TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_verses_bcv ON verses(book_id, chapter, verse);

-- FTS5 full-text index over verse text (external content = verses table).
-- The index holds the text with its Greek folded (see greek.py), so it is
-- filled by Database.rebuild_fts rather than by FTS5's own 'rebuild'.
CREATE VIRTUAL TABLE IF NOT EXISTS verses_fts USING fts5(
    text,
    content='verses',
    content_rowid='verse_key'
);

-- Translator's notes, in source order within each verse.
CREATE TABLE IF NOT EXISTS notes (
    verse_key INTEGER NOT NULL,   -- REFERENCES verses(verse_key)
    label     TEXT NOT NULL,      -- the note's label in the source, e.g. "1"
    text      TEXT NOT NULL       -- note body, stripped of markup
);

CREATE INDEX IF NOT EXISTS idx_notes_verse ON notes(verse_key);
"""


def _range_clause(ranges: Sequence[tuple[int, int]]) -> tuple[str, list[Any]]:
    """Build an ``OR`` of ``verse_key BETWEEN`` clauses for a set of key ranges.

    Returns the parenthesised SQL fragment and its bound parameters. An empty
    ``ranges`` yields ``("1=0", [])`` so the caller matches nothing.
    """
    if not ranges:
        return "1=0", []
    parts = ["verse_key BETWEEN ? AND ?"] * len(ranges)
    params: list[Any] = []
    for start, end in ranges:
        params.extend((start, end))
    return "(" + " OR ".join(parts) + ")", params


class Database:
    """Manages SQLite database connections and operations for a Bible."""

    def __init__(self, db_path: str | Path):
        """Initialize the database wrapper.

        Args:
            db_path: Path to the SQLite database file.

        """
        self.db_path = Path(db_path)
        self.conn: sqlite3.Connection | None = None

    def __enter__(self) -> "Database":
        """Open the connection on context entry."""
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Close the connection on context exit."""
        self.close()

    def connect(self) -> None:
        """Open the database connection."""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

    def close(self) -> None:
        """Close the database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def _require_conn(self) -> sqlite3.Connection:
        if self.conn is None:
            raise RuntimeError("Database not connected")
        return self.conn

    def create_schema(self) -> None:
        """Create the database schema if it does not exist."""
        conn = self._require_conn()
        conn.executescript(SCHEMA_SQL)
        conn.commit()

    def set_metadata(self, key: str, value: str) -> None:
        """Set a single metadata key-value pair."""
        conn = self._require_conn()
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)", (key, value)
        )
        conn.commit()

    def get_metadata(self, key: str) -> str | None:
        """Return a metadata value by key, or None if absent."""
        conn = self._require_conn()
        cursor = conn.execute("SELECT value FROM metadata WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row["value"] if row else None

    def get_all_metadata(self) -> dict[str, str]:
        """Return all metadata as a dictionary."""
        conn = self._require_conn()
        cursor = conn.execute("SELECT key, value FROM metadata ORDER BY key")
        return {row["key"]: row["value"] for row in cursor.fetchall()}

    def validate_schema(self) -> None:
        """Verify this database is a compatible versiref-bible Bible.

        Checks the product identity marker first (so that another
        versiref-ecosystem database is rejected cleanly rather than failing
        later on a missing table), then the schema version using the additive
        rule: the database's major version must equal this code's major
        version, and its minor version must be >= the minor version the core
        reads require (:data:`REQUIRED_SCHEMA_VERSION`). A feature added by a
        later minor version is checked by :meth:`require_feature`.

        Raises:
            IncompatibleDatabaseError: If the file is not an SQLite database
                or has no metadata table, lacks the product marker
                (legacy/unmarked — rebuild to fix), declares a different
                product, or has an incompatible schema version.

        """
        try:
            product = self.get_metadata("format")
        except sqlite3.DatabaseError as exc:
            # Not an SQLite file at all, or one with no metadata table.
            raise IncompatibleDatabaseError(
                f"{self.db_path}: not a versiref-bible database ({exc})"
            ) from exc
        if product is None:
            raise IncompatibleDatabaseError(
                f"{self.db_path}: not a versiref-bible database "
                "(missing 'format' marker); rebuild the Bible"
            )
        if product != PRODUCT_NAME:
            raise IncompatibleDatabaseError(
                f"{self.db_path}: database format is '{product}', not '{PRODUCT_NAME}'"
            )

        version, (db_major, db_minor) = self._schema_version()
        req_major, req_minor = _parse_schema_version(REQUIRED_SCHEMA_VERSION)
        if db_major != req_major or db_minor < req_minor:
            # An older schema is cured by rebuilding; a newer one is not.
            advice = (
                "; rebuild the Bible"
                if (db_major, db_minor) < (req_major, req_minor)
                else ""
            )
            raise IncompatibleDatabaseError(
                f"{self.db_path}: schema version {version} is incompatible with "
                f"this code (requires {REQUIRED_SCHEMA_VERSION}){advice}"
            )

    def _schema_version(self) -> tuple[str, tuple[int, int]]:
        """Return the database's schema version, as written and parsed."""
        version = self.get_metadata("schema_version")
        if version is None:
            raise IncompatibleDatabaseError(
                f"{self.db_path}: missing schema_version metadata"
            )
        try:
            return version, _parse_schema_version(version)
        except ValueError as exc:
            raise IncompatibleDatabaseError(
                f"{self.db_path}: unparseable schema_version '{version}': {exc}"
            ) from exc

    def require_feature(self, feature: str) -> None:
        """Verify this database was built with a feature of :data:`FEATURES`.

        Call after :meth:`validate_schema`, before reading the feature's data.

        Raises:
            IncompatibleDatabaseError: If the database's schema predates the
                feature; the message says which package version to rebuild
                the Bible with.

        """
        description, schema, package = FEATURES[feature]
        version, parsed = self._schema_version()
        if parsed < _parse_schema_version(schema):
            raise IncompatibleDatabaseError(
                f"{self.db_path}: this database was built without {description} "
                f"(schema version {version}; they need {schema}); rebuild the "
                f"Bible with versiref-bible >= {package}"
            )

    @staticmethod
    def _verse_columns() -> str:
        """Return the verse columns to select, aliased ``v``."""
        return "v.verse_key, v.book_id, v.chapter, v.verse, v.text, v.subverse"

    def insert_verses(self, verses: Iterable[Verse]) -> None:
        """Bulk-insert verses in a single transaction.

        Does not rebuild the FTS index; call :meth:`rebuild_fts` afterwards.
        """
        conn = self._require_conn()
        conn.executemany(
            "INSERT OR REPLACE INTO verses"
            " (verse_key, book_id, chapter, verse, text, subverse)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            [
                (v.key, v.book_id, v.chapter, v.verse, v.text, v.subverse)
                for v in verses
            ],
        )
        conn.commit()

    def insert_notes(self, notes: Iterable[tuple[int, Note]]) -> None:
        """Bulk-insert ``(verse_key, note)`` pairs in a single transaction.

        Notes read back in insertion order within a verse.
        """
        conn = self._require_conn()
        conn.executemany(
            "INSERT INTO notes (verse_key, label, text) VALUES (?, ?, ?)",
            [(key, note.label, note.text) for key, note in notes],
        )
        conn.commit()

    def notes_in_ranges(
        self, ranges: Sequence[tuple[int, int]]
    ) -> dict[int, tuple[Note, ...]]:
        """Return the notes of verses in the given key ranges, by verse key.

        A verse with no notes has no entry.
        """
        conn = self._require_conn()
        clause, params = _range_clause(ranges)
        cursor = conn.execute(
            f"SELECT verse_key, label, text FROM notes WHERE {clause}"
            " ORDER BY verse_key, rowid",
            params,
        )
        notes: dict[int, tuple[Note, ...]] = {}
        for row in cursor.fetchall():
            key = row["verse_key"]
            notes[key] = (*notes.get(key, ()), Note(row["label"], row["text"]))
        return notes

    def rebuild_fts(self) -> None:
        """Rebuild the FTS5 index from the external-content verses table.

        The text is indexed with its Greek folded (:func:`fold_greek`), so a
        search must fold its query likewise; the stored text is untouched.
        FTS5's own ``'rebuild'`` command would index the text as stored.
        """
        conn = self._require_conn()
        conn.create_function("fold_greek", 1, fold_greek, deterministic=True)
        conn.execute("INSERT INTO verses_fts(verses_fts) VALUES('delete-all')")
        conn.execute(
            "INSERT INTO verses_fts(rowid, text)"
            " SELECT verse_key, fold_greek(text) FROM verses"
        )
        conn.commit()

    def count_verses(self) -> int:
        """Return the total number of stored verses."""
        conn = self._require_conn()
        cursor = conn.execute("SELECT COUNT(*) AS n FROM verses")
        return int(cursor.fetchone()["n"])

    def verses_in_ranges(self, ranges: Sequence[tuple[int, int]]) -> list[Verse]:
        """Return verses whose key falls in any of the given key ranges.

        Args:
            ranges: ``(start_key, end_key)`` pairs (inclusive).

        Returns:
            Matching verses ordered by verse key (i.e. canonical order).

        """
        conn = self._require_conn()
        clause, params = _range_clause(ranges)
        cursor = conn.execute(
            f"SELECT {self._verse_columns()} FROM verses v"
            f" WHERE {clause} ORDER BY verse_key",
            params,
        )
        return [_row_to_verse(row) for row in cursor.fetchall()]

    def search(
        self,
        query: str,
        limit: int,
        ranges: Sequence[tuple[int, int]] | None = None,
        order: str = "canonical",
    ) -> list[Verse]:
        """Full-text search verse text.

        Args:
            query: FTS5 MATCH query.
            limit: Maximum number of verses to return.
            ranges: Optional key ranges to restrict the search to.
            order: ``"canonical"`` for verse-key (Bible) order, or
                ``"relevance"`` for FTS5 bm25 rank (best first), tie-broken by
                verse key.

        Returns:
            Matching verses in the requested order, capped at ``limit``.

        """
        if order not in ("canonical", "relevance"):
            raise ValueError(
                f"Invalid order {order!r}: use 'canonical' or 'relevance'."
            )
        conn = self._require_conn()
        sql = [
            f"SELECT {self._verse_columns()}",
            "FROM verses_fts f JOIN verses v ON v.verse_key = f.rowid",
            "WHERE f.text MATCH ?",
        ]
        params: list[Any] = [query]
        if ranges is not None:
            clause, range_params = _range_clause(ranges)
            sql.append(f"AND {clause}")
            params.extend(range_params)
        if order == "relevance":
            sql.append("ORDER BY f.rank, v.verse_key")
        else:
            sql.append("ORDER BY v.verse_key")
        sql.append("LIMIT ?")
        params.append(limit)
        cursor = conn.execute("\n".join(sql), params)
        return [_row_to_verse(row) for row in cursor.fetchall()]

    def count_matches(
        self, query: str, ranges: Sequence[tuple[int, int]] | None = None
    ) -> int:
        """Count verses matching an FTS5 query (ignoring any limit)."""
        conn = self._require_conn()
        sql = ["SELECT COUNT(*) AS n FROM verses_fts f WHERE f.text MATCH ?"]
        params: list[Any] = [query]
        if ranges is not None:
            clause, range_params = _range_clause(ranges)
            # f.rowid is the verse_key; reuse the same clause column name.
            sql.append("AND " + clause.replace("verse_key", "f.rowid"))
            params.extend(range_params)
        cursor = conn.execute("\n".join(sql), params)
        return int(cursor.fetchone()["n"])


def _row_to_verse(row: sqlite3.Row) -> Verse:
    return Verse(
        key=row["verse_key"],
        book_id=row["book_id"],
        chapter=row["chapter"],
        verse=row["verse"],
        text=row["text"],
        subverse=row["subverse"],
    )
