"""Data models for versiref-bible."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Note:
    """A labelled note attached to a verse.

    Attributes:
        label: The note's label in the source (e.g. ``1``).
        text: The note body, stripped of markup.

    """

    label: str
    text: str


@dataclass(frozen=True)
class Verse:
    """A single Bible verse stored in the database.

    Attributes:
        key: Integer verse key (BBCCCVVVSS, the trailing SS a subverse ordinal)
            from ``range_keys`` under the database's versification; also the
            FTS5 rowid.
        book_id: Paratext book ID (e.g. ``JHN``).
        chapter: Chapter number.
        verse: Verse number.
        text: Verse text.
        subverse: Letters naming an inserted verse (``a`` in Add Esth 4:17a),
            or ``""`` for an ordinary verse.
        notes: The verse's translator's notes, filled in only when they are
            asked for (``show_verses(..., notes=True)``).

    """

    key: int
    book_id: str
    chapter: int
    verse: int
    text: str
    subverse: str = ""
    notes: tuple[Note, ...] = ()


@dataclass
class BuildStats:
    """Summary of a ``build`` run, for reporting to the operator.

    Attributes:
        stored: Number of verses written to the database.
        unknown_books: Abbreviation -> count for tokens the book style did not
            recognize (e.g. the Sirach prologue ``Sip``).
        off_scheme_books: Abbreviation -> count for books not present in the
            chosen versification (no integer key can be computed).
        malformed: Number of non-blank lines that did not parse as
            ``Abbrev C:V text`` naming a single verse.
        duplicates: Number of lines whose verse key collided with an earlier
            line (later line wins).
        stripped_markup: Number of stored verses whose text had recognized
            CCAT/BibleWorks markup stripped.
        suspect_markup: Number of stored verses whose text still contains
            markup-like characters after stripping (unrecognized markup,
            kept verbatim).
        notes: Number of translator's notes extracted and stored.
        strongs: Number of Strong's tags extracted and stored.

    """

    stored: int = 0
    unknown_books: dict[str, int] = field(default_factory=dict)
    off_scheme_books: dict[str, int] = field(default_factory=dict)
    malformed: int = 0
    duplicates: int = 0
    stripped_markup: int = 0
    suspect_markup: int = 0
    notes: int = 0
    strongs: int = 0
