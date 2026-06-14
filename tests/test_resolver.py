"""Tests for Bible name resolution and the ``list`` command."""

import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from versiref.bible import (
    BibleNotFoundError,
    bible_search_path,
    build_database,
    default_data_dir,
    list_bibles,
    resolve_bible,
)
from versiref.bible.cli import main
from versiref.bible.resolver import ENV_VAR

SAMPLE = """\
Gen 1:1 In the beginning God created the heaven and the earth.
Joh 3:16 For God so loved the world, that he gave his only begotten Son.
"""


def _build(dir_path: Path, name: str, title: str = "Sample") -> Path:
    """Build a tiny Bible database named ``<name>.db`` under ``dir_path``."""
    source = dir_path / f"{name}.cat"
    source.write_text(SAMPLE, encoding="utf-8")
    db_path = dir_path / f"{name}.db"
    build_database(source, db_path, versification="eng", title=title)
    return db_path


def test_default_data_dir_ends_with_package_name() -> None:
    assert default_data_dir().name == "versiref-bible"


def test_search_path_defaults_to_data_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)
    assert bible_search_path() == [default_data_dir()]


def test_search_path_reads_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    a, b = tmp_path / "a", tmp_path / "b"

    monkeypatch.setenv(ENV_VAR, os.pathsep.join([str(a), str(b)]))
    assert bible_search_path() == [a, b]


def test_resolve_existing_path_unchanged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)
    db_path = _build(tmp_path, "kjv")
    assert resolve_bible(db_path) == db_path
    assert resolve_bible(str(db_path)) == db_path


def test_resolve_by_name_on_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db_path = _build(tmp_path, "kjv")
    monkeypatch.setenv(ENV_VAR, str(tmp_path))
    assert resolve_bible("kjv") == db_path
    # A trailing .db on the name is accepted too.
    assert resolve_bible("kjv.db") == db_path


def test_resolve_respects_path_order(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    db_first = _build(first, "kjv", title="First")
    _build(second, "kjv", title="Second")
    monkeypatch.setenv(ENV_VAR, os.pathsep.join([str(first), str(second)]))
    assert resolve_bible("kjv") == db_first


def test_resolve_unknown_name_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(ENV_VAR, str(tmp_path))
    with pytest.raises(BibleNotFoundError):
        resolve_bible("nope")


def test_resolve_path_like_missing_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(ENV_VAR, str(tmp_path))
    with pytest.raises(BibleNotFoundError):
        resolve_bible("subdir/nope")


def test_list_bibles_dedups_by_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    db_first = _build(first, "kjv")
    db_second = _build(second, "nvul")
    _build(second, "kjv")  # shadowed by the one in `first`
    monkeypatch.setenv(ENV_VAR, os.pathsep.join([str(first), str(second)]))
    assert list_bibles() == [db_first, db_second]


def test_list_bibles_skips_missing_dirs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(ENV_VAR, str(tmp_path / "does-not-exist"))
    assert list_bibles() == []


def test_cli_resolves_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _build(tmp_path, "kjv")
    monkeypatch.setenv(ENV_VAR, str(tmp_path))
    result = CliRunner().invoke(main, ["show", "kjv", "John 3:16"])
    assert result.exit_code == 0
    assert "so loved the world" in result.output


def test_cli_unknown_name_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(ENV_VAR, str(tmp_path))
    result = CliRunner().invoke(main, ["info", "missing"])
    assert result.exit_code == 1
    assert "No Bible named" in result.output


def test_cli_list(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _build(tmp_path, "kjv", title="King James Version")
    monkeypatch.setenv(ENV_VAR, str(tmp_path))
    result = CliRunner().invoke(main, ["list"])
    assert result.exit_code == 0
    line = result.output.strip()
    fields = line.split("\t")
    assert fields[0] == "kjv"
    assert fields[1] == "eng"
    assert fields[2] == "2"
    assert fields[3] == "King James Version"


def test_cli_list_empty(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(ENV_VAR, str(tmp_path))
    result = CliRunner().invoke(main, ["list"])
    assert result.exit_code == 0
    assert "No Bible databases found" in result.output
