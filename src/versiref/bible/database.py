"""Database schema and operations for versiref-bible."""

import sqlite3
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from .models import Verse

SCHEMA_VERSION = "1.0"

SCHEMA_SQL = """
-- Key-value metadata (title, versification, source, etc.)
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- One row per Bible verse. verse_key is the BBCCCVVV integer computed under
-- the database's versification; it doubles as the FTS5 rowid.
CREATE TABLE IF NOT EXISTS verses (
    verse_key INTEGER PRIMARY KEY,
    book_id   TEXT NOT NULL,
    chapter   INTEGER NOT NULL,
    verse     INTEGER NOT NULL,
    text      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_verses_bcv ON verses(book_id, chapter, verse);

-- FTS5 full-text index over verse text (external content = verses table)
CREATE VIRTUAL TABLE IF NOT EXISTS verses_fts USING fts5(
    text,
    content='verses',
    content_rowid='verse_key'
);
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

    def insert_verses(self, verses: Iterable[Verse]) -> None:
        """Bulk-insert verses in a single transaction.

        Does not rebuild the FTS index; call :meth:`rebuild_fts` afterwards.
        """
        conn = self._require_conn()
        conn.executemany(
            "INSERT OR REPLACE INTO verses (verse_key, book_id, chapter, verse, text)"
            " VALUES (?, ?, ?, ?, ?)",
            [(v.key, v.book_id, v.chapter, v.verse, v.text) for v in verses],
        )
        conn.commit()

    def rebuild_fts(self) -> None:
        """Rebuild the FTS5 index from the external-content verses table."""
        conn = self._require_conn()
        conn.execute("INSERT INTO verses_fts(verses_fts) VALUES('rebuild')")
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
            "SELECT verse_key, book_id, chapter, verse, text FROM verses"
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
            raise ValueError(f"Invalid order {order!r}: use 'canonical' or 'relevance'.")
        conn = self._require_conn()
        sql = [
            "SELECT v.verse_key, v.book_id, v.chapter, v.verse, v.text",
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
    )
