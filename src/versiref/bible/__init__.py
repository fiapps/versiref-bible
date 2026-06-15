"""Access Bibles stored in an SQLite database with versiref."""

from versiref.bible.builder import build_database
from versiref.bible.database import Database, IncompatibleDatabaseError
from versiref.bible.models import BuildStats, Verse
from versiref.bible.reader import format_verse, search_verses, show_verses
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
    "IncompatibleDatabaseError",
    "Verse",
    "bible_search_path",
    "build_database",
    "default_data_dir",
    "format_verse",
    "list_bibles",
    "resolve_bible",
    "search_verses",
    "show_verses",
]
