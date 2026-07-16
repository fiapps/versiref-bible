"""Tests for CCAT/BibleWorks markup stripping."""

from pathlib import Path

from versiref.bible import build_database, search_verses, strip_markup
from versiref.bible.ccat_markup import has_markup_residue

# An ESV-style line: note anchors, cross-reference anchors, a terminated
# footnote block, and italics inside the notes.
ESV_LINE = (
    "And God made<N1> the expanse and <Ra>separated the waters that were "
    "under the expanse from the waters that were <Rb>above the expanse. "
    "And it was so. {<p><rsup>a</rsup> Pro 8:27-29 <p><rsup>b</rsup> "
    "Psa 148:4 <p><nsup>1</nsup> Or [fashioned]; also verse 16 }"
)

# A KJV-style line: Strong's numbers, tense/voice/mood codes, italics in the
# verse text, and an *unterminated* footnote block running to end of line.
KJV_LINE = (
    "And God <0430> said <0559> (08799), Let the waters <04325> bring forth "
    "abundantly <08317> (08799) the moving creature <08318> that hath "
    "<05315> life <02416>, and fowl <05775> [that] may fly <05774> (08787) "
    "above <05921> the earth <0776> in the open <06440> firmament <07549> "
    "of heaven <08064>.<N1> { <p><nsup>1</nsup> moving: or, creeping"
    "<p><nsup>2</nsup> creature: Heb. soul<p>"
)


def test_strip_esv_style_notes() -> None:
    assert strip_markup(ESV_LINE) == (
        "And God made the expanse and separated the waters that were under "
        "the expanse from the waters that were above the expanse. "
        "And it was so."
    )


def test_strip_kjv_style_strongs() -> None:
    assert strip_markup(KJV_LINE) == (
        "And God said, Let the waters bring forth abundantly the moving "
        "creature that hath life, and fowl that may fly above the earth in "
        "the open firmament of heaven."
    )


def test_psalm_superscription_is_unwrapped() -> None:
    # KJV Psalm titles are wrapped in double angle brackets.
    line = "<<A Psalm of David.>> The LORD is my shepherd; I shall not want."
    assert strip_markup(line) == (
        "A Psalm of David. The LORD is my shepherd; I shall not want."
    )


def test_stray_trailing_brace_is_dropped() -> None:
    # The NABRE export ends some lines with an unmatched closing brace.
    line = 'How can you say to me, "Flee like a bird to the mountains! }'
    assert strip_markup(line) == (
        'How can you say to me, "Flee like a bird to the mountains!'
    )


def test_plain_text_is_unchanged() -> None:
    text = "In the beginning God created the heaven and the earth."
    assert strip_markup(text) == text


def test_unrecognized_markup_is_kept_and_detected() -> None:
    stripped = strip_markup("And God <weird> said.")
    assert stripped == "And God <weird> said."
    assert has_markup_residue(stripped)
    assert not has_markup_residue("And God said.")


def _build(tmp_path: Path, line: str, **kwargs: bool) -> tuple[Path, object]:
    source = tmp_path / "sample.cat"
    source.write_text(f"Gen 1:20 {line}\n", encoding="utf-8")
    db_path = tmp_path / "sample.db"
    stats = build_database(source, db_path, versification="eng", **kwargs)
    return db_path, stats


def test_build_strips_markup_and_fixes_phrase_search(tmp_path: Path) -> None:
    db_path, stats = _build(tmp_path, KJV_LINE)
    assert stats.stripped_markup == 1
    assert stats.suspect_markup == 0
    # A phrase broken up by Strong's numbers in the raw text now matches.
    verses, total, _ = search_verses(db_path, '"waters bring forth abundantly"')
    assert total == 1
    assert "<0430>" not in verses[0].text
    # Footnote text no longer produces false positives.
    _, total, _ = search_verses(db_path, "creeping")
    assert total == 0


def test_build_keep_markup_stores_verbatim(tmp_path: Path) -> None:
    db_path, stats = _build(tmp_path, KJV_LINE, keep_markup=True)
    assert stats.stripped_markup == 0
    verses, total, _ = search_verses(db_path, "creeping")
    assert total == 1
    assert "<0430>" in verses[0].text
