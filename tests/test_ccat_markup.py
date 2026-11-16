"""Tests for CCAT/BibleWorks markup stripping."""

from pathlib import Path

from click.testing import CliRunner

from versiref import RefStyle
from versiref.bible import (
    Database,
    Note,
    build_database,
    extract_markup,
    format_note,
    search_verses,
    show_verses,
    strip_markup,
)
from versiref.bible.ccat_markup import has_markup_residue
from versiref.bible.cli import main

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


def test_single_angle_superscription_is_unwrapped() -> None:
    # The NRSV export wraps Psalm titles in single angle brackets, and one of
    # them quotes speech, so the body carries double quotes of its own.
    line = (
        "<To the leader. A Maskil of David, when Doeg the Edomite came to "
        'Saul and said to him, "David has come to the house of Ahimelech.">'
        " Why do you boast, O mighty one?"
    )
    assert strip_markup(line) == (
        "To the leader. A Maskil of David, when Doeg the Edomite came to "
        'Saul and said to him, "David has come to the house of Ahimelech." '
        "Why do you boast, O mighty one?"
    )


def test_formatting_tags_are_dropped_and_their_words_kept() -> None:
    # The Clementine Vulgate marks the Hebrew alphabet of Psalm 118 with an
    # <i> whose closing tag is malformed ("< i>" for "</i>").
    line = "<i>Beth< i> In quo corrigit adolescentior viam suam?"
    assert strip_markup(line) == "Beth In quo corrigit adolescentior viam suam?"
    # A <link> is closed by the generic "</>".
    assert strip_markup('See <link b="Gen 1:1">1:1</> here.') == "See 1:1 here."


def test_html_style_note_anchors_are_dropped() -> None:
    # NETS carries HTML anchors for its footnotes, sometimes mid-word and
    # sometimes with the opening <sup> lost, leaving the anchor letter behind.
    line = (
        'there are ephoud, theraphin<a id="pg231en_b"></a>, a carved '
        'object<a id="pg231en_c"></a> and a cast object'
    )
    assert strip_markup(line) == (
        "there are ephoud, theraphin, a carved object and a cast object"
    )


def test_tag_between_two_words_leaves_a_space() -> None:
    # Welding the words together would hide both from the search index.
    assert strip_markup("c</a></sup>these shall be") == "c these shall be"
    assert strip_markup("31.9<br/>follows 24.34") == "31.9 follows 24.34"


def test_doubled_brackets_become_literal_brackets() -> None:
    # "[[" and "]]" escape a literal bracket; Brenton and the ESV use them to
    # fence passages of doubtful authenticity, sometimes across verses.
    assert strip_markup("[[Jews]] and [supplied] words") == "[Jews] and supplied words"
    assert strip_markup("[[Now when he rose early") == "[Now when he rose early"


def test_small_caps_backslashes_are_dropped() -> None:
    assert strip_markup(r"And the \LORD\ said") == "And the LORD said"


def test_strongs_number_with_homograph_letter() -> None:
    assert strip_markup("was <07363b> moving") == "was moving"


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


def test_unrecognized_tag_is_not_unwrapped_into_its_attributes() -> None:
    # A tag outside the known vocabulary must not be mistaken for a
    # superscription, which would spill its attributes into the verse text.
    line = 'x <span class="q">y</span> z'
    assert strip_markup(line) == line
    assert has_markup_residue(strip_markup(line))


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


def test_small_caps_keep_a_following_possessive() -> None:
    assert strip_markup(r"the \LORD\'s anointed") == "the LORD's anointed"


def test_beta_code_grave_accents_are_not_small_caps() -> None:
    # In Beta Code Greek a backslash is the grave accent, following a letter
    # or another diacritic; it never opens a word as small caps do.
    for line in (
        r"e)n a)rxh^| e)poi/hsen o( qeo\s to\n ou)rano\n kai\ th\n gh^n",
        r"kai\ ei)^den o( qeo\s to\ fw^s o(/ti kalo/n",
        r"a)\n de\ kai\ o(\s a)\n",
    ):
        assert strip_markup(line) == line


def test_extract_markup_text_matches_strip_markup() -> None:
    for line in (KJV_LINE, ESV_LINE, r"the \LORD\ said <0559> [unto] him"):
        assert extract_markup(line).text == strip_markup(line)


def test_extract_markup_routes_notes_and_cross_references() -> None:
    extracted = extract_markup(ESV_LINE)
    # Note bodies are stripped of markup like the verse text.
    assert extracted.notes == (Note("1", "Or fashioned; also verse 16"),)
    assert extracted.cross_references == (
        Note("a", "Pro 8:27-29"),
        Note("b", "Psa 148:4"),
    )
    assert extracted.anchors == ("N1", "Ra", "Rb")
    assert extracted.strongs == ()


def test_extract_markup_notes_need_no_matching_anchor() -> None:
    # KJV Gen 1:20: one <N1> anchor for several numbered notes, in an
    # unterminated block ending in an empty <p> piece.
    extracted = extract_markup(KJV_LINE)
    assert extracted.anchors == ("N1",)
    assert [note.label for note in extracted.notes] == ["1", "2"]
    assert extracted.notes[0].text == "moving: or, creeping"


def test_extract_markup_strongs_word_spans() -> None:
    extracted = extract_markup(
        "And God <0430> saw <07200> (08799) <0853> the light <0216>, "
        "that <03588> [it was] good <02896>:"
    )
    words = extracted.text.split()
    spans = [
        (tag.lang, tag.number, words[tag.word_start : tag.word_end])
        for tag in extracted.strongs
    ]
    assert spans == [
        ("H", 430, ["And", "God"]),
        ("H", 7200, ["saw"]),
        # A tag directly after another tags no word: an empty span that still
        # records where it sat.
        ("H", 853, []),
        ("H", 216, ["the", "light,"]),
        ("H", 3588, ["that"]),
        ("H", 2896, ["it", "was", "good:"]),
    ]


def test_extract_markup_greek_strongs_and_suffix() -> None:
    extracted = extract_markup("The book <976> of the generation <1078a>")
    assert [(t.lang, t.number, t.suffix) for t in extracted.strongs] == [
        ("G", 976, ""),
        ("G", 1078, "a"),
    ]


def test_extract_markup_ignores_strongs_inside_note_block() -> None:
    # KJV Luk 10:22: the note quotes tagged text; those tags are not the
    # verse's, and the note body is stripped of them.
    extracted = extract_markup(
        "All things <3956> are delivered.<N1> { <p><nsup>1</nsup> and <2532> "
        "turning <4762> (5651) to his disciples<p>"
    )
    assert [tag.number for tag in extracted.strongs] == [3956]
    assert extracted.notes == (Note("1", "and turning to his disciples"),)


def test_build_stores_notes_and_show_returns_them(tmp_path: Path) -> None:
    db_path, stats = _build(tmp_path, KJV_LINE)
    assert stats.notes == 2
    with Database(db_path) as db:
        assert db.get_metadata("notes_count") == "2"
    plain, _ = show_verses(db_path, "Gen 1:20")
    assert plain[0].notes == ()
    verses, db_vers = show_verses(db_path, "Gen 1:20", notes=True)
    assert [note.label for note in verses[0].notes] == ["1", "2"]
    line = format_note(verses[0], verses[0].notes[1], RefStyle.named("en-sbl"), db_vers)
    assert line == "Gen 1:20 note 2\tcreature: Heb. soul"


def test_build_keep_markup_extracts_no_notes(tmp_path: Path) -> None:
    db_path, stats = _build(tmp_path, KJV_LINE, keep_markup=True)
    assert stats.notes == 0
    # The key is still written: the database has the feature, just no data.
    with Database(db_path) as db:
        assert db.get_metadata("notes_count") == "0"
    verses, _ = show_verses(db_path, "Gen 1:20", notes=True)
    assert verses[0].notes == ()


def test_duplicate_line_replaces_notes(tmp_path: Path) -> None:
    source = tmp_path / "sample.cat"
    source.write_text(
        "Gen 1:1 First.<N1> {<p><nsup>1</nsup> old note }\n"
        "Gen 1:1 Second.\n"
        "Gen 1:2 Third.<N1> {<p><nsup>1</nsup> kept note }\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "sample.db"
    stats = build_database(source, db_path, versification="eng")
    assert stats.duplicates == 1
    assert stats.notes == 1
    verses, _ = show_verses(db_path, "Gen 1:1-2", notes=True)
    assert [v.notes for v in verses] == [(), (Note("1", "kept note"),)]


def test_cli_show_notes_interleaves_two_field_lines(tmp_path: Path) -> None:
    source = tmp_path / "sample.cat"
    source.write_text(
        "Gen 1:6 Let there be an expanse.<N1> {<p><nsup>1</nsup> Or [a canopy] }\n"
        "Gen 1:7 And God made the expanse.\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "sample.db"
    build_database(source, db_path, versification="eng")
    runner = CliRunner()
    result = runner.invoke(main, ["show", str(db_path), "Gen 1:6-7", "--notes"])
    assert result.exit_code == 0
    assert result.output.splitlines() == [
        "Gen 1:6\tLet there be an expanse.",
        "Gen 1:6 note 1\tOr a canopy",
        "Gen 1:7\tAnd God made the expanse.",
    ]
    # Without the flag the notes stay out of the output.
    result = runner.invoke(main, ["show", str(db_path), "Gen 1:6-7"])
    assert len(result.output.splitlines()) == 2
