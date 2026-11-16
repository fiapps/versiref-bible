"""Access Bibles stored in an SQLite database with versiref."""

from versiref.bible.builder import build_database
from versiref.bible.ccat_markup import (
    ExtractedMarkup,
    StrongsTag,
    extract_markup,
    strip_markup,
)
from versiref.bible.database import Database, IncompatibleDatabaseError
from versiref.bible.models import BuildStats, Note, Verse
from versiref.bible.reader import (
    format_note,
    format_verse,
    search_verses,
    show_verses,
)
from versiref.bible.resolver import (
    BibleNotFoundError,
    bible_search_path,
    default_data_dir,
    list_bibles,
    resolve_bible,
)

__all__ = [
    "BibleNotFoundError",
    "BuildStats",
    "Database",
    "ExtractedMarkup",
    "IncompatibleDatabaseError",
    "Note",
    "StrongsTag",
    "Verse",
    "bible_search_path",
    "build_database",
    "default_data_dir",
    "extract_markup",
    "format_note",
    "format_verse",
    "list_bibles",
    "resolve_bible",
    "search_verses",
    "show_verses",
    "strip_markup",
]
