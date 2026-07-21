"""Tests for the product-identity marker and consumer-side schema check."""

import sqlite3
from pathlib import Path

import pytest
from click.testing import CliRunner

from versiref.bible import (
    Database,
    IncompatibleDatabaseError,
    build_database,
    search_verses,
    show_verses,
)
from versiref.bible.cli import main

SAMPLE = "Joh 3:16 For God so loved the world, that he gave his only begotten Son.\n"


@pytest.fixture
def bible_db(tmp_path: Path) -> Path:
    source = tmp_path / "sample.cat"
    source.write_text(SAMPLE, encoding="utf-8")
    db_path = tmp_path / "sample.db"
    build_database(source, db_path, versification="eng", title="Sample")
    return db_path


def _set_meta(db_path: Path, key: str, value: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)", (key, value)
    )
    conn.commit()
    conn.close()


def _del_meta(db_path: Path, key: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM metadata WHERE key = ?", (key,))
    conn.commit()
    conn.close()


def test_build_writes_format_marker(bible_db: Path) -> None:
    with Database(bible_db) as db:
        assert db.get_metadata("format") == "versiref-bible"
        db.validate_schema()  # does not raise


def test_validate_rejects_unmarked_legacy(bible_db: Path) -> None:
    _del_meta(bible_db, "format")
    with Database(bible_db) as db, pytest.raises(IncompatibleDatabaseError, match="rebuild"):
        db.validate_schema()


def test_validate_rejects_foreign_product(bible_db: Path) -> None:
    _set_meta(bible_db, "format", "versiref-search")
    with Database(bible_db) as db, pytest.raises(
        IncompatibleDatabaseError, match="versiref-search"
    ):
        db.validate_schema()


def test_validate_rejects_incompatible_major(bible_db: Path) -> None:
    # A schema 1.x database is the pre-0.10 format with 8-digit verse keys;
    # under the current major (2) it is rejected so it gets rebuilt rather than
    # silently returning no matches against 10-digit keys.
    _set_meta(bible_db, "schema_version", "1.0")
    with Database(bible_db) as db, pytest.raises(IncompatibleDatabaseError, match="incompatible"):
        db.validate_schema()


def test_validate_rejects_unparseable_version(bible_db: Path) -> None:
    _set_meta(bible_db, "schema_version", "abc")
    with Database(bible_db) as db, pytest.raises(IncompatibleDatabaseError, match="unparseable"):
        db.validate_schema()


def test_validate_accepts_higher_minor(bible_db: Path) -> None:
    # Same major, higher minor is forward-compatible (additive schema rule).
    _set_meta(bible_db, "schema_version", "2.9")
    with Database(bible_db) as db:
        db.validate_schema()  # does not raise


def test_show_rejects_foreign_db(bible_db: Path) -> None:
    _set_meta(bible_db, "format", "versiref-search")
    with pytest.raises(IncompatibleDatabaseError):
        show_verses(bible_db, "John 3:16")


def test_search_rejects_unmarked_db(bible_db: Path) -> None:
    _del_meta(bible_db, "format")
    with pytest.raises(IncompatibleDatabaseError):
        search_verses(bible_db, "loved")


def test_cli_info_rejects_foreign_db(bible_db: Path) -> None:
    _set_meta(bible_db, "format", "versiref-search")
    result = CliRunner().invoke(main, ["info", str(bible_db)])
    assert result.exit_code == 1
    assert "versiref-search" in result.output


def test_cli_show_rejects_unmarked_db(bible_db: Path) -> None:
    _del_meta(bible_db, "format")
    result = CliRunner().invoke(main, ["show", str(bible_db), "John 3:16"])
    assert result.exit_code == 1
    assert "rebuild the Bible" in result.output
