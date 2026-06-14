"""Locate Bible databases by name across a search path.

A Bible can be named on the command line either by a path to its ``.db`` file or
by a bare *name* that is looked up across the directories on a search path. The
search path comes from the ``VERSIREF_BIBLE_PATH`` environment variable
(``os.pathsep``-separated, like ``PATH``); when it is unset the path is a single
per-user data directory (:func:`default_data_dir`).

A repo-local collection needs no special support: point ``VERSIREF_BIBLE_PATH``
at the repo's directory (optionally appending the default with ``os.pathsep``).
"""

import os
import sys
from pathlib import Path

ENV_VAR = "VERSIREF_BIBLE_PATH"
SUFFIX = ".db"


class BibleNotFoundError(ValueError):
    """Raised when a Bible spec cannot be resolved to a database file."""


def default_data_dir() -> Path:
    """Return the per-user directory searched when ``VERSIREF_BIBLE_PATH`` is unset.

    Follows the conventional per-platform location for application data
    (``%LOCALAPPDATA%`` on Windows, ``~/Library/Application Support`` on macOS,
    ``$XDG_DATA_HOME`` or ``~/.local/share`` elsewhere), under ``versiref-bible``.
    """
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "versiref-bible"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "versiref-bible"
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "versiref-bible"


def bible_search_path() -> list[Path]:
    """Return the ordered directories searched for named Bibles.

    Uses ``VERSIREF_BIBLE_PATH`` (``os.pathsep``-separated) when it is set to a
    non-empty value; otherwise a single-element path holding
    :func:`default_data_dir`.
    """
    raw = os.environ.get(ENV_VAR)
    if raw:
        dirs = [Path(part) for part in raw.split(os.pathsep) if part]
        if dirs:
            return dirs
    return [default_data_dir()]


def _looks_like_path(spec: str) -> bool:
    """Return whether ``spec`` is meant as a filesystem path, not a bare name."""
    return os.sep in spec or (os.altsep is not None and os.altsep in spec)


def resolve_bible(spec: str | Path) -> Path:
    """Resolve a Bible ``spec`` (a name or a path) to an existing database file.

    Resolution order:

    1. If ``spec`` names an existing file, return it unchanged. This keeps a
       plain path (``kjv.db``, ``./bibles/kjv.db``, an absolute path) working.
    2. If ``spec`` looks like a path (it contains a separator) but no such file
       exists, raise :class:`BibleNotFoundError` rather than searching by name.
    3. Otherwise treat ``spec`` as a name and look for ``<name>.db`` in each
       directory on :func:`bible_search_path`, in order; the first match wins.

    Raises:
        BibleNotFoundError: If no matching database file can be found.

    """
    text = str(spec)
    candidate = Path(text)
    if candidate.is_file():
        return candidate
    if _looks_like_path(text):
        raise BibleNotFoundError(f"No Bible database at {text!r}.")

    filename = text if text.endswith(SUFFIX) else text + SUFFIX
    path = bible_search_path()
    for directory in path:
        located = directory / filename
        if located.is_file():
            return located
    searched = os.pathsep.join(str(d) for d in path)
    raise BibleNotFoundError(
        f"No Bible named {text!r} found on the search path ({searched}). "
        f"Set {ENV_VAR} or pass a path to the .db file."
    )


def list_bibles() -> list[Path]:
    """Return the database files discovered on the search path.

    Directories are scanned in search-path order and their ``*.db`` files sorted
    by name. When the same name appears in more than one directory only the first
    (the one :func:`resolve_bible` would pick) is returned; missing directories
    are skipped.
    """
    found: dict[str, Path] = {}
    for directory in bible_search_path():
        if not directory.is_dir():
            continue
        for db_file in sorted(directory.glob("*" + SUFFIX)):
            found.setdefault(db_file.stem, db_file)
    return list(found.values())
