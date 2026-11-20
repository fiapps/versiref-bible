"""Build and query the Strong's concordance independently of verse text."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from versiref.bible import build_database, search_verses, show_verses
from versiref.bible.cli import main
from versiref.bible.database import Database, IncompatibleDatabaseError

SOURCE = """Gen 1:1 In the [beginning] <07225> God <0430> <0853> created <01254>. {<nsup>1</nsup> note <0999>}
Gen 1:2 darkness <02822>
Gen 1:3 light <0216>
Gen 1:4 light <0216> night <03915>
Gen 1:5 light <0216><0216>
Mat 1:1 book <976> generation <1078a>
"""


@pytest.fixture
def concordance(tmp_path: Path) -> Path:
    source = tmp_path / "source.cat"
    source.write_text(SOURCE, encoding="utf-8")
    path = tmp_path / "bible.db"
    build_database(source, path, versification="eng")
    return path


def test_build_stores_strongs_and_final_word_offsets(concordance: Path) -> None:
    with Database(concordance) as db:
        assert db.get_metadata("strongs_count") == "12"
        assert db.get_metadata("schema_version") == "3.1"
        rows = (
            db._require_conn()
            .execute(
                "SELECT s.lang, s.number, s.ordinal, s.word_start, s.word_end, v.text "
                "FROM strongs s JOIN verses v ON s.verse_key = v.verse_key "
                "WHERE v.book_id = 'GEN' AND v.verse = 1 ORDER BY s.ordinal"
            )
            .fetchall()
        )
    assert [(r["lang"], r["number"], r["ordinal"]) for r in rows] == [
        ("H", 7225, 0),
        ("H", 430, 1),
        ("H", 853, 2),
        ("H", 1254, 3),
    ]
    assert [r["text"].split(" ")[r["word_start"] : r["word_end"]] for r in rows] == [
        ["In", "the", "beginning"],
        ["God"],
        [],
        ["created."],
    ]


@pytest.mark.parametrize(
    ("query", "strongs", "match_all", "expected"),
    [
        (None, ["h216"], False, [3, 4, 5]),
        (None, ["H00000000000000000000000216"], False, [3, 4, 5]),
        (None, ["H216", "H3915"], False, [3, 4, 5]),
        (None, ["H216", "H3915"], True, [4]),
        ("darkness", ["H216"], False, [2, 3, 4, 5]),
        ("night", ["H216"], True, [4]),
        (None, ["H216", "H216"], True, [3, 4, 5]),
        (None, ["H999"], False, []),
    ],
)
def test_combines_complete_query_sets(
    concordance: Path,
    query: str | None,
    strongs: list[str],
    match_all: bool,
    expected: list[int],
) -> None:
    verses, total, _ = search_verses(
        concordance, query, strongs=strongs, match_all=match_all
    )
    assert [v.verse for v in verses] == expected
    assert total == len(expected)


def test_greek_numbers_and_homograph_suffix(concordance: Path) -> None:
    verses, total, _ = search_verses(concordance, strongs=["g1078"])
    assert total == 1
    assert verses[0].book_id == "MAT"


def test_limit_scope_and_relevance(concordance: Path) -> None:
    verses, total, _ = search_verses(
        concordance, strongs=["H216"], scope="Gen 1:3–4", limit=1
    )
    assert total == 2
    assert [v.verse for v in verses] == [3]
    verses, total, _ = search_verses(
        concordance, "night", strongs=["H216"], order="relevance"
    )
    assert total == 3
    assert [v.verse for v in verses] == [4, 3, 5]


def test_literal_text_combines_with_tags(concordance: Path) -> None:
    verses, total, _ = search_verses(
        concordance, phrase="night", strongs=["H216"], match_all=True
    )
    assert total == 1
    assert verses[0].verse == 4


@pytest.mark.parametrize(
    "number",
    [
        "216",
        "H",
        "X216",
        "H-1",
        "H21.6",
        "H216 OR 1=1",
        "H9223372036854775808",
        "H" + "9" * 5000,
    ],
)
def test_rejects_malformed_numbers(concordance: Path, number: str) -> None:
    with pytest.raises(ValueError, match="Strong"):
        search_verses(concordance, strongs=[number])


def test_cli_pure_and_combined_queries(concordance: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["search", str(concordance), "--strongs", "g976"])
    assert result.exit_code == 0, result.output
    assert result.output == "Matt 1:1\tbook generation\n"
    result = runner.invoke(
        main, ["search", str(concordance), "night", "--strongs", "H216", "--and"]
    )
    assert result.exit_code == 0, result.output
    assert result.output == "Gen 1:4\tlight night\n"
    result = runner.invoke(main, ["search", str(concordance), "--strongs", "invalid"])
    assert result.exit_code == 1
    assert "Strong" in result.output


def test_legacy_database_keeps_plain_reads(concordance: Path) -> None:
    with Database(concordance) as db:
        db._require_conn().execute("DROP TABLE strongs")
        db.set_metadata("schema_version", "3.0")
    assert show_verses(concordance, "Gen 1:3")[0][0].text == "light"
    assert search_verses(concordance, "light")[1] == 3
    with pytest.raises(IncompatibleDatabaseError, match="rebuild the Bible"):
        search_verses(concordance, strongs=["H216"])


def test_duplicate_lines_replace_strongs_and_keep_zero_count(tmp_path: Path) -> None:
    source = tmp_path / "source.cat"
    source.write_text("Gen 1:1 old <0430>\nGen 1:1 new <0216>\n", encoding="utf-8")
    path = tmp_path / "bible.db"
    stats = build_database(source, path, versification="eng")
    assert stats.strongs == 1
    assert search_verses(path, strongs=["H430"])[1] == 0
    assert search_verses(path, strongs=["H216"])[1] == 1
    stats = build_database(source, path, versification="eng", keep_markup=True)
    assert stats.strongs == 0
    with Database(path) as db:
        assert db.get_metadata("strongs_count") == "0"
    assert search_verses(path, strongs=["H216"])[1] == 0


def test_duplicate_query_terms_do_not_hit_sql_compound_limit(concordance: Path) -> None:
    verses, total, _ = search_verses(
        concordance, strongs=["H216"] * 600, match_all=True
    )
    assert total == 3
    assert [v.verse for v in verses] == [3, 4, 5]


def test_combined_query_rejects_two_text_forms(concordance: Path) -> None:
    with pytest.raises(ValueError, match="Exactly one"):
        search_verses(concordance, "light", phrase="night", strongs=["H216"])
    with pytest.raises(ValueError, match="Invalid order"):
        search_verses(concordance, strongs=["H216"], order="invalid")


@pytest.mark.parametrize("separator", ["\t", "\u00a0", "\v"])
def test_tagged_word_offsets_use_final_space_normalized_text(
    tmp_path: Path, separator: str
) -> None:
    source = tmp_path / "source.cat"
    source.write_text(f"Gen 1:1 the{separator}light <0216>\n", encoding="utf-8")
    path = tmp_path / "bible.db"
    build_database(source, path, versification="eng")
    with Database(path) as db:
        row = (
            db._require_conn()
            .execute(
                "SELECT word_start, word_end, text FROM strongs JOIN verses USING (verse_key)"
            )
            .fetchone()
        )
    assert row["text"].split(" ")[row["word_start"] : row["word_end"]] == [
        "the",
        "light",
    ]


def test_beta_code_conversion_keeps_final_word_offsets(tmp_path: Path) -> None:
    source = tmp_path / "source.cat"
    source.write_text("Joh 1:1 O( LO/GOS <3056>\n", encoding="utf-8")
    path = tmp_path / "bible.db"
    build_database(source, path, versification="eng", encoding="beta-code")
    with Database(path) as db:
        row = (
            db._require_conn()
            .execute(
                "SELECT word_start, word_end, text FROM strongs JOIN verses USING (verse_key)"
            )
            .fetchone()
        )
    assert (row["word_start"], row["word_end"]) == (0, 2)
    assert len(row["text"].split(" ")) == 2
    assert "LO/GOS" not in row["text"]
    assert search_verses(path, strongs=["G3056"])[1] == 1
