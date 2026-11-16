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
from versiref.bible.database import SCHEMA_VERSION

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
    with (
        Database(bible_db) as db,
        pytest.raises(IncompatibleDatabaseError, match="rebuild"),
    ):
        db.validate_schema()


def test_validate_rejects_foreign_product(bible_db: Path) -> None:
    _set_meta(bible_db, "format", "versiref-search")
    with (
        Database(bible_db) as db,
        pytest.raises(IncompatibleDatabaseError, match="versiref-search"),
    ):
        db.validate_schema()


def test_validate_rejects_incompatible_major(bible_db: Path) -> None:
    # A schema 1.x database is the pre-0.10 format with 8-digit verse keys;
    # under the current major (2) it is rejected so it gets rebuilt rather than
    # silently returning no matches against 10-digit keys.
    _set_meta(bible_db, "schema_version", "1.0")
    with (
        Database(bible_db) as db,
        pytest.raises(IncompatibleDatabaseError, match="incompatible"),
    ):
        db.validate_schema()


def test_validate_rejects_unparseable_version(bible_db: Path) -> None:
    _set_meta(bible_db, "schema_version", "abc")
    with (
        Database(bible_db) as db,
        pytest.raises(IncompatibleDatabaseError, match="unparseable"),
    ):
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


def test_validate_rejects_non_sqlite_file(tmp_path: Path) -> None:
    junk = tmp_path / "junk.db"
    junk.write_text("not a database")
    with Database(junk) as db, pytest.raises(IncompatibleDatabaseError):
        db.validate_schema()


def test_cli_rejects_sqlite_without_metadata(tmp_path: Path) -> None:
    foreign = tmp_path / "foreign.db"
    conn = sqlite3.connect(foreign)
    conn.execute("CREATE TABLE x (a)")
    conn.commit()
    conn.close()
    for args in (["info", str(foreign)], ["show", str(foreign), "John 3:16"]):
        result = CliRunner().invoke(main, args)
        assert result.exit_code == 1
        assert "not a versiref-bible database" in result.output


def test_cli_unknown_style_is_reported(bible_db: Path) -> None:
    result = CliRunner().invoke(
        main, ["show", str(bible_db), "John 3:16", "--style", "bogus"]
    )
    assert result.exit_code == 1
    assert result.output.startswith("Error:")


def _downgrade_to_2_0(db_path: Path) -> None:
    """Reshape a database into what a pre-0.5.0 build (schema 2.0) wrote."""
    conn = sqlite3.connect(db_path)
    conn.executescript(
        "ALTER TABLE verses DROP COLUMN subverse;"
        "DROP TABLE notes;"
        "DELETE FROM metadata WHERE key = 'notes_count';"
        "UPDATE metadata SET value = '2.0' WHERE key = 'schema_version';"
    )
    conn.commit()
    conn.close()


def test_build_writes_current_schema_version(bible_db: Path) -> None:
    with Database(bible_db) as db:
        assert db.get_metadata("schema_version") == SCHEMA_VERSION
        db.require_feature("notes")  # does not raise


def test_core_reads_accept_schema_2_0(bible_db: Path) -> None:
    # A feature's minor bump must not lock older databases out of show/search.
    _downgrade_to_2_0(bible_db)
    verses, _ = show_verses(bible_db, "John 3:16")
    assert [v.subverse for v in verses] == [""]
    _, total, _ = search_verses(bible_db, "loved")
    assert total == 1
    result = CliRunner().invoke(main, ["info", str(bible_db)])
    assert result.exit_code == 0
    assert "notes_count" not in result.output


def test_notes_on_schema_2_0_says_rebuild(bible_db: Path) -> None:
    _downgrade_to_2_0(bible_db)
    with pytest.raises(IncompatibleDatabaseError, match=r"rebuild.*>= 0\.5\.0"):
        show_verses(bible_db, "John 3:16", notes=True)
    result = CliRunner().invoke(main, ["show", str(bible_db), "John 3:16", "--notes"])
    assert result.exit_code == 1
    assert "translator's notes" in result.output
    assert "rebuild the Bible" in result.output
