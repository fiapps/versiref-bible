"""End-to-end tests for build, show, and search."""

from pathlib import Path

import pytest
from versiref import RefStyle

from versiref.bible import build_database, format_verse, search_verses, show_verses

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
    with pytest.raises(ValueError):
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
    with pytest.raises(ValueError):
        search_verses(bible_db, "God", order="bogus")
