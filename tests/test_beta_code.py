"""Tests for Beta Code conversion and Greek search folding."""

from pathlib import Path

from versiref.bible import (
    Database,
    beta_to_unicode,
    build_database,
    search_verses,
    show_verses,
)
from versiref.bible.greek import fold_greek


def test_letters_breathings_accents_and_iota_subscript() -> None:
    assert (
        beta_to_unicode(
            r"e)n a)rxh^| e)poi/hsen o( qeo\s to\n ou)rano\n kai\ th\n gh^n"
        )
        == "ἐν ἀρχῇ ἐποίησεν ὁ θεὸς τὸν οὐρανὸν καὶ τὴν γῆν"
    )
    assert beta_to_unicode("w)/|khsen") == "ᾤκησεν"
    assert beta_to_unicode("Rafai+n u(i+/") == "Ραφαϊν ὑΐ"


def test_circumflex_in_either_spelling() -> None:
    # "^" in BibleWorks' Beta Code, "=" in the TLG's.
    assert beta_to_unicode("gh^n") == beta_to_unicode("gh=n") == "γῆν"


def test_capitals_in_either_convention() -> None:
    # BibleWorks: an uppercase letter, marks after it. TLG: an asterisk, the
    # marks, then the letter.
    assert beta_to_unicode("A)ssuri/wn Adam") == "Ἀσσυρίων Αδαμ"
    assert beta_to_unicode("*)assuri/wn *adam *(/oti") == "Ἀσσυρίων Αδαμ Ὅτι"


def test_final_sigma() -> None:
    assert beta_to_unicode("o( lo/gos sofo/s") == "ὁ λόγος σοφός"
    # Punctuation ends the word as a space does; a capital does not.
    assert beta_to_unicode("(o(/s) lo/gos, pros*a") == "(ὅς) λόγος, προσΑ"


def test_what_is_not_beta_code_is_kept() -> None:
    assert beta_to_unicode("[1] Iexonia-asir 12") == "[1] Ιεχονια-ασιρ 12"
    # An elision's apostrophe becomes a right single quotation mark.
    assert beta_to_unicode("a)nt' au)tou^") == "ἀντ’ αὐτοῦ"
    # A mark that cannot sit on the letter before it is punctuation.
    assert beta_to_unicode("(kai\\ ton)") == "(καὶ τον)"


def test_fold_greek() -> None:
    assert fold_greek("ἐν ἀρχῇ ὁ θεὸς ᾤκησεν Ραφαϊν") == "εν αρχη ο θεοσ ωκησεν Ραφαιν"
    # Not Greek: unchanged, query syntax included.
    assert fold_greek('perché "città" AND NOT (x*)') == 'perché "città" AND NOT (x*)'


LXX_SAMPLE = (
    "Gen 1:1 e)n a)rxh^| e)poi/hsen o( qeo\\s to\\n ou)rano\\n kai\\ th\\n gh^n\n"
    "Gen 1:3 kai\\ ei)^pen o( qeo/s genhqh/tw fw^s kai\\ e)ge/neto fw^s\n"
)


def _build_lxx(tmp_path: Path) -> Path:
    source = tmp_path / "lxx.cat"
    source.write_text(LXX_SAMPLE, encoding="utf-8")
    db_path = tmp_path / "lxx.db"
    stats = build_database(source, db_path, versification="lxx", encoding="beta-code")
    assert stats.stored == 2
    # The backslashes are grave accents, not small-caps markup.
    assert stats.suspect_markup == 0
    return db_path


def test_build_converts_beta_code_text_not_the_reference(tmp_path: Path) -> None:
    db_path = _build_lxx(tmp_path)
    verses, _ = show_verses(db_path, "Gen 1:1")
    assert verses[0].book_id == "GEN"
    assert verses[0].text == "ἐν ἀρχῇ ἐποίησεν ὁ θεὸς τὸν οὐρανὸν καὶ τὴν γῆν"


def test_greek_search_ignores_accents_case_and_final_sigma(tmp_path: Path) -> None:
    db_path = _build_lxx(tmp_path)
    with Database(db_path) as db:
        assert db.get_metadata("search_folding") == "greek"
    # The grave (1:1) and acute (1:3) forms are one word to a search.
    for query in ("θεὸς", "θεός", "θεος", "ΘΕΟΣ"):
        _, total, _ = search_verses(db_path, query)
        assert total == 2, query
    verses, total, _ = search_verses(db_path, phrase="εν αρχη")
    assert total == 1
    # The stored text keeps its diacritics.
    assert verses[0].text.startswith("ἐν ἀρχῇ")


def test_search_without_folding_key_matches_as_written(tmp_path: Path) -> None:
    # A database built before the index was folded holds accented tokens; its
    # queries must not be folded, or exact searches that worked would miss.
    db_path = _build_lxx(tmp_path)
    with Database(db_path) as db:
        conn = db._require_conn()
        conn.execute("DELETE FROM metadata WHERE key = 'search_folding'")
        conn.execute("INSERT INTO verses_fts(verses_fts) VALUES('rebuild')")
        conn.commit()
    assert search_verses(db_path, "θεὸς")[1] == 1
    assert search_verses(db_path, "θεος")[1] == 0
