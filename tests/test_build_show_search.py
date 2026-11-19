"""End-to-end tests for build, show, and search."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from versiref import RefStyle
from versiref.bible import (
    Database,
    build_database,
    format_verse,
    search_verses,
    show_verses,
)
from versiref.bible.cli import main

SAMPLE = """\
Gen 1:1 In the beginning God created the heaven and the earth.
Gen 1:2 And the earth was without form, and void; and darkness was upon the deep.
Gen 2:1 Thus the heavens and the earth were finished.
Joh 3:16 For God so loved the world, that he gave his only begotten Son.
Joh 3:17 For God sent not his Son into the world to condemn the world.
Joh 3:18 He that believeth on him is not condemned.
Sip 1:1 Whereas many and great things have been delivered unto us.
"""


@pytest.fixture
def bible_db(tmp_path: Path) -> Path:
    source = tmp_path / "sample.cat"
    source.write_text(SAMPLE, encoding="utf-8")
    db_path = tmp_path / "sample.db"
    stats = build_database(source, db_path, versification="eng", title="Sample")
    # Sip is an unrecognized abbreviation (Sirach prologue): warned and skipped.
    assert stats.stored == 6
    assert "Sip" in stats.unknown_books
    assert not stats.off_scheme_books
    return db_path


def _labels(db_path: Path, reference: str, style: str = "en-sbl") -> list[str]:
    verses, db_vers = show_verses(db_path, reference, style_name=style)
    ref_style = RefStyle.named(style)
    return [format_verse(v, ref_style, db_vers) for v in verses]


def test_show_verse_range(bible_db: Path) -> None:
    lines = _labels(bible_db, "John 3:16-17")
    assert len(lines) == 2
    assert lines[0].startswith("John 3:16\t")
    assert "so loved the world" in lines[0]
    assert lines[1].startswith("John 3:17\t")


def test_show_crosses_chapter_boundary(bible_db: Path) -> None:
    # Gen 1:2 through Gen 2:1 spans a chapter boundary within one book.
    lines = _labels(bible_db, "Gen 1:2-2:1")
    assert [line.split("\t", 1)[0] for line in lines] == [
        "Gen 1:2",
        "Gen 2:1",
    ]


def test_show_style_changes_label(bible_db: Path) -> None:
    lines = _labels(bible_db, "John 3:16", style="en-bibleworks")
    assert lines[0].startswith("Joh 3:16\t")


def test_show_unknown_reference_errors(bible_db: Path) -> None:
    with pytest.raises(ValueError, match="Could not parse reference"):
        show_verses(bible_db, "not a reference")


def test_search_matches(bible_db: Path) -> None:
    verses, total, _ = search_verses(bible_db, "loved")
    assert total == 1
    assert verses[0].book_id == "JHN"


def test_search_scope_restricts(bible_db: Path) -> None:
    # "earth" appears in Genesis and (not) in John; scope to Genesis 1.
    verses, total, _ = search_verses(bible_db, "earth", scope="Gen 1")
    assert total == 2
    assert {v.chapter for v in verses} == {1}
    assert all(v.book_id == "GEN" for v in verses)


def test_search_limit(bible_db: Path) -> None:
    verses, total, _ = search_verses(bible_db, "the", limit=2)
    assert len(verses) <= 2
    assert total >= len(verses)


def test_search_canonical_order_is_default(bible_db: Path) -> None:
    # "God" appears in Genesis and John; default order is by verse key.
    verses, _, _ = search_verses(bible_db, "God")
    keys = [v.key for v in verses]
    assert keys == sorted(keys)
    assert verses[0].book_id == "GEN"


def test_search_relevance_order(bible_db: Path) -> None:
    verses, _, _ = search_verses(bible_db, "God", order="relevance")
    assert {v.book_id for v in verses} == {"GEN", "JHN"}


def test_search_invalid_order_rejected(bible_db: Path) -> None:
    with pytest.raises(ValueError, match="Invalid order"):
        search_verses(bible_db, "God", order="bogus")


# The NABRE prints the Additions to Esther as chapters A-F of Esther itself.
# versiref (>= 0.14.0) holds each lettered verse as one inserted beside a verse
# of EST, in reading order: A before 1:1, C after 4:17, F after 10:3.
ESTHER_SAMPLE = """\
Est 1:1 Now it came to pass in the days of Ahasuerus.
Est 4:17 Mordecai went away and did all that Esther commanded.
Est A:1 In the second year Mordecai had a dream.
Est C:12 Esther the queen sought refuge in the Lord.
Est F:11 These signs happened among God's people.
"""


def test_nabre_lettered_chapters_are_esther(tmp_path: Path) -> None:
    source = tmp_path / "esther.cat"
    source.write_text(ESTHER_SAMPLE, encoding="utf-8")
    db_path = tmp_path / "esther.db"
    stats = build_database(source, db_path, versification="nabre")
    assert stats.stored == 5
    assert stats.malformed == 0
    assert not stats.unknown_books
    assert not stats.off_scheme_books

    # A whole-book reference takes in the lettered chapters, in reading order.
    style = RefStyle.named("en-sbl")
    verses, db_vers = show_verses(db_path, "Esth")
    assert {v.book_id for v in verses} == {"EST"}
    assert [format_verse(v, style, db_vers).split("\t")[0] for v in verses] == [
        "Esth A:1",
        "Esth 1:1",
        "Esth 4:17",
        "Esth C:12",
        "Esth F:11",
    ]

    # A range can pass between a numbered chapter and a lettered one.
    verses, _ = show_verses(db_path, "Esth 4:1-C:30")
    assert [(v.verse, v.subverse) for v in verses] == [(17, ""), (17, "C12")]
    # A numbered chapter leaves out a lettered chapter at its edge.
    verses, _ = show_verses(db_path, "Esth 4")
    assert [v.subverse for v in verses] == [""]


def test_lettered_chapters_off_scheme_without_them(tmp_path: Path) -> None:
    source = tmp_path / "esther.cat"
    source.write_text(ESTHER_SAMPLE, encoding="utf-8")
    db_path = tmp_path / "esther.db"
    # Lettered chapters parse only under a versification that has them; under
    # eng "Est" is recognized, so they count as malformed, not unknown.
    stats = build_database(source, db_path, versification="eng")
    assert stats.stored == 2
    assert stats.malformed == 3
    assert not stats.unknown_books


# The Greek additions to Esther letter their verses a, b, c, …, and CEI 2008
# uses the letter ``f`` (e.g. Est 1:1f). versiref (>= 0.14.1) reads a glued
# ``f`` as that verse where the versification lists it, not as "and following",
# which would fold the verse onto its base verse.
ESTHER_LETTER_F_SAMPLE = """\
Esg 1:1 The narrative begins after the dream.
Esg 1:1f A verse of the dream of Mordecai whose letter is f.
Esg 1:2 The narrative continues.
"""


def test_verse_letter_f_is_not_and_following(tmp_path: Path) -> None:
    source = tmp_path / "esther.cat"
    source.write_text(ESTHER_LETTER_F_SAMPLE, encoding="utf-8")
    db_path = tmp_path / "esther.db"
    stats = build_database(source, db_path, versification="cei")
    # All three lines get distinct keys: 1:1f is not folded onto 1:1.
    assert stats.stored == 3
    assert stats.duplicates == 0
    # cei puts Addition A (1:1a-r) before the base verse 1:1, as the text does,
    # so the chapter (not "1:1-2", which starts at the base verse) takes it in.
    verses, _ = show_verses(db_path, "Esg 1", style_name="en-bibleworks")
    assert [v.text for v in verses] == [
        "A verse of the dream of Mordecai whose letter is f.",
        "The narrative begins after the dream.",
        "The narrative continues.",
    ]
    # show reads the glued letter as that verse too, not as "and following".
    verses, _ = show_verses(db_path, "Esg 1:1f", style_name="en-bibleworks")
    assert [v.text for v in verses] == [
        "A verse of the dream of Mordecai whose letter is f.",
    ]


def test_search_phrase_matches_text_as_written(tmp_path: Path) -> None:
    source = tmp_path / "s.cat"
    source.write_text(
        'Gen 1:1 A so-called beginning.\nGen 1:2 He said "so" and called.\n',
        encoding="utf-8",
    )
    db_path = tmp_path / "s.db"
    build_database(source, db_path, versification="eng")
    # As an FTS5 expression the hyphen is query syntax and is refused, with a
    # pointer to the phrase search.
    with pytest.raises(ValueError, match="--phrase"):
        search_verses(db_path, "so-called")
    verses, total, _ = search_verses(db_path, phrase="so-called")
    assert total == 1
    assert verses[0].verse == 1
    # A quotation mark in the phrase is literal too.
    verses, total, _ = search_verses(db_path, phrase='said "so" and')
    assert [v.verse for v in verses] == [2]


def test_search_requires_exactly_one_of_query_and_phrase(bible_db: Path) -> None:
    with pytest.raises(ValueError, match="Exactly one of"):
        search_verses(bible_db)
    with pytest.raises(ValueError, match="Exactly one of"):
        search_verses(bible_db, "God", phrase="God")


def test_cli_search_phrase_and_limit(bible_db: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["search", str(bible_db), "-p", "so loved"])
    assert result.exit_code == 0
    assert result.output.startswith("John 3:16\t")
    assert runner.invoke(main, ["search", str(bible_db)]).exit_code == 1
    assert (
        runner.invoke(main, ["search", str(bible_db), "God", "-p", "God"]).exit_code
        == 1
    )
    assert (
        runner.invoke(main, ["search", str(bible_db), "God", "-n", "0"]).exit_code == 2
    )


def test_build_refuses_to_overwrite_its_input(tmp_path: Path) -> None:
    source = tmp_path / "sample.cat"
    source.write_text(SAMPLE, encoding="utf-8")
    with pytest.raises(ValueError, match="input file"):
        build_database(source, source, versification="eng")
    assert source.read_text(encoding="utf-8") == SAMPLE


def test_build_ignores_byte_order_mark(tmp_path: Path) -> None:
    source = tmp_path / "bom.cat"
    source.write_text("\ufeff" + SAMPLE, encoding="utf-8")
    db_path = tmp_path / "bom.db"
    stats = build_database(source, db_path, versification="eng")
    assert stats.stored == 6
    assert list(stats.unknown_books) == ["Sip"]


def test_build_counts_a_range_line_as_malformed(tmp_path: Path) -> None:
    source = tmp_path / "r.cat"
    source.write_text(
        "Gen 1:1 One verse.\nGen 1:2-3 Two verses.\nGen 1:4,6 A list.\n",
        encoding="utf-8",
    )
    stats = build_database(source, tmp_path / "r.db", versification="eng")
    assert stats.stored == 1
    assert stats.malformed == 2


def test_cli_build_warns_when_nothing_is_stored(tmp_path: Path) -> None:
    source = tmp_path / "e.cat"
    source.write_text("garbage\n", encoding="utf-8")
    result = CliRunner().invoke(
        main, ["build", str(source), "-o", str(tmp_path / "e.db"), "-v", "eng"]
    )
    assert result.exit_code == 0
    assert "no verses were stored" in result.output


def test_subverse_labels_inserted_verses(tmp_path: Path) -> None:
    # The Greek additions to Esther are verses inserted after 4:17, each with
    # its own key; the stored subverse keeps their labels apart.
    source = tmp_path / "esther.cat"
    source.write_text(
        "Esg 4:17 Mordecai went away.\n"
        "Esg 4:17a Then he prayed to the Lord.\n"
        "Esg 4:17f And now, Lord God.\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "esther.db"
    stats = build_database(source, db_path, versification="lxx")
    assert stats.stored == 3
    assert not stats.duplicates
    lines = _labels(db_path, "Add Esth 4")
    assert [line.split("\t", 1)[0] for line in lines] == [
        "Add Esth 4:17",
        "Add Esth 4:17a",
        "Add Esth 4:17f",
    ]


# Rahlfs gives Daniel and Judges in two texts each, and BibleWorks names the
# Old Greek Daniel "Dan" and the two Judges "Jda" and "Jdg" — which the
# en-bibleworks style reads as DAN (not in the lxx versification) and as JDG
# twice over.
LXX_VARIANTS_SAMPLE = """\
Dan 1:1 Old Greek Daniel.
Dat 1:1 Theodotion Daniel.
Jda 1:1 Judges, the A text.
Jdg 1:1 Judges, the B text.
"""

LXX_STYLE = """\
{
  "base": "en-bibleworks",
  "override_names": {
    "DAG": "Dan", "DAN": "DanH",
    "JDB": "Jdg", "JDG": "Jda"
  }
}
"""


def test_book_style_file_reroutes_abbreviations(tmp_path: Path) -> None:
    source = tmp_path / "lxx.cat"
    source.write_text(LXX_VARIANTS_SAMPLE, encoding="utf-8")
    db_path = tmp_path / "lxx.db"

    # With the named style, Dan is off-scheme and the Judges texts collide.
    stats = build_database(source, db_path, versification="lxx")
    assert stats.stored == 2
    assert stats.off_scheme_books == {"Dan": 1}
    assert stats.duplicates == 1

    style_file = tmp_path / "bibleworks-lxx.json"
    style_file.write_text(LXX_STYLE, encoding="utf-8")
    # A Path, or a string that looks like one, is a style file.
    for book_style in (style_file, str(style_file)):
        stats = build_database(
            source, db_path, versification="lxx", book_style=book_style
        )
        assert stats.stored == 4
        assert not stats.off_scheme_books
        assert not stats.duplicates
    with Database(db_path) as db:
        books = [v.book_id for v in db.verses_in_ranges([(0, 10**10)])]
    assert sorted(books) == ["DAG", "DNT", "JDB", "JDG"]


def test_cli_book_style_file(tmp_path: Path) -> None:
    source = tmp_path / "lxx.cat"
    source.write_text(LXX_VARIANTS_SAMPLE, encoding="utf-8")
    style_file = tmp_path / "bibleworks-lxx.json"
    style_file.write_text(LXX_STYLE, encoding="utf-8")
    db_path = tmp_path / "lxx.db"
    args = ["build", str(source), "-o", str(db_path), "-v", "lxx", "--book-style"]
    runner = CliRunner()
    result = runner.invoke(main, [*args, str(style_file)])
    assert result.exit_code == 0
    assert "4 verses" in result.output
    # A missing or malformed style file is an error, not a traceback.
    result = runner.invoke(main, [*args, str(tmp_path / "missing.json")])
    assert result.exit_code == 1
    assert "Error:" in result.output
    style_file.write_text("{not json", encoding="utf-8")
    result = runner.invoke(main, [*args, str(style_file)])
    assert result.exit_code == 1
    assert "Error:" in result.output
