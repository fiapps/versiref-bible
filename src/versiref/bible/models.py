"""Data models for versiref-bible."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Verse:
    """A single Bible verse stored in the database.

    Attributes:
        key: Integer verse key (BBCCCVVV) from ``range_keys`` under the
            database's versification; also the FTS5 rowid.
        book_id: Paratext book ID (e.g. ``JHN``).
        chapter: Chapter number.
        verse: Verse number.
        text: Verse text.

    """

    key: int
    book_id: str
    chapter: int
    verse: int
    text: str


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
            ``Abbrev C:V text``.
        duplicates: Number of lines whose verse key collided with an earlier
            line (later line wins).

    """

    stored: int = 0
    unknown_books: dict[str, int] = field(default_factory=dict)
    off_scheme_books: dict[str, int] = field(default_factory=dict)
    malformed: int = 0
    duplicates: int = 0
