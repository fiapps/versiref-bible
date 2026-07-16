"""Command-line interface for versiref-bible."""

import os
import sqlite3
import sys
from importlib.resources import files
from pathlib import Path

import click
from versiref import RefStyle

from .builder import build_database
from .database import Database, IncompatibleDatabaseError
from .models import BuildStats
from .reader import format_verse, search_verses, show_verses
from .resolver import (
    ENV_VAR,
    bible_search_path,
    list_bibles,
    resolve_bible,
)


@click.group()
@click.version_option(package_name="versiref-bible")
def main() -> None:
    """Access Bibles stored in an SQLite database with versiref."""
    pass


def _report_build(stats: BuildStats, output: Path) -> None:
    """Print a build summary, sending skip warnings to stderr."""
    click.echo(f"✓ Built {output} ({stats.stored} verses)")
    if stats.stripped_markup:
        click.echo(f"  stripped markup from {stats.stripped_markup} verse(s)")
    if stats.suspect_markup:
        click.echo(
            f"  warning: {stats.suspect_markup} verse(s) still contain "
            "unrecognized markup after stripping",
            err=True,
        )
    if stats.unknown_books:
        total = sum(stats.unknown_books.values())
        names = ", ".join(sorted(stats.unknown_books))
        click.echo(
            f"  warning: skipped {total} line(s) with unrecognized book "
            f"abbreviations: {names}",
            err=True,
        )
    if stats.off_scheme_books:
        total = sum(stats.off_scheme_books.values())
        names = ", ".join(sorted(stats.off_scheme_books))
        click.echo(
            f"  warning: skipped {total} line(s) in books not in the "
            f"versification: {names}",
            err=True,
        )
    if stats.malformed:
        click.echo(
            f"  warning: skipped {stats.malformed} malformed line(s)", err=True
        )
    if stats.duplicates:
        click.echo(
            f"  warning: {stats.duplicates} duplicate verse key(s) (last kept)",
            err=True,
        )


@main.command()
@click.argument(
    "input_file", type=click.Path(exists=True, dir_okay=False, path_type=Path)
)
@click.option(
    "-o",
    "--output",
    "output_file",
    type=click.Path(dir_okay=False, path_type=Path),
    required=True,
    help="Output database path.",
)
@click.option(
    "-v",
    "--versification",
    required=True,
    help="Named versification of the Bible (e.g. eng, lxx, cei).",
)
@click.option("--title", default=None, help="Human-readable title for the Bible.")
@click.option(
    "--book-style",
    default="en-bibleworks",
    show_default=True,
    help="Reference style whose names map the file's book abbreviations.",
)
@click.option(
    "--encoding",
    default="utf-8",
    show_default=True,
    help="Text encoding of the input file (e.g., cp1252).",
)
@click.option(
    "--keep-markup",
    is_flag=True,
    help="Store verse text verbatim instead of stripping CCAT/BibleWorks "
    "markup (footnotes, Strong's numbers, italics brackets).",
)
def build(
    input_file: Path,
    output_file: Path,
    versification: str,
    title: str | None,
    book_style: str,
    encoding: str,
    keep_markup: bool,
) -> None:
    """Build a Bible database from a CCAT-format text file.

    Each line of INPUT_FILE is read as ``Abbrev C:V text``. Lines whose book
    abbreviation is unrecognized, or whose book is not in the chosen
    versification, are skipped with a warning. Recognized CCAT/BibleWorks
    markup (footnotes, Strong's numbers, italics brackets) is stripped from
    the verse text unless ``--keep-markup`` is given.
    """
    output = output_file
    try:
        stats = build_database(
            input_file,
            output,
            versification=versification,
            title=title,
            book_style=book_style,
            encoding=encoding,
            keep_markup=keep_markup,
        )
        _report_build(stats, output)
    except (ValueError, LookupError, OSError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@main.command()
@click.argument("database")
@click.argument("reference")
@click.option(
    "--style",
    default="en-sbl",
    show_default=True,
    help="Reference style for parsing input and labelling output.",
)
@click.option(
    "--from-versification",
    default=None,
    help="Interpret REFERENCE in this versification and map it to the database's.",
)
def show(
    database: str,
    reference: str,
    style: str,
    from_versification: str | None,
) -> None:
    """Print the verses covered by a Bible REFERENCE, one per line.

    DATABASE is a Bible name on the search path (see ``list``) or a path to a
    ``.db`` file. Each line is ``reference<TAB>text``.
    """
    try:
        db_path = resolve_bible(database)
        verses, db_vers = show_verses(
            db_path,
            reference,
            style_name=style,
            from_versification=from_versification,
        )
        if not verses:
            click.echo("No verses found.", err=True)
            return
        ref_style = RefStyle.named(style)
        for verse in verses:
            click.echo(format_verse(verse, ref_style, db_vers))
    except (ValueError, LookupError, IncompatibleDatabaseError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@main.command()
@click.argument("database")
@click.argument("query")
@click.option(
    "-n",
    "--limit",
    type=int,
    default=20,
    show_default=True,
    help="Maximum number of verses to return.",
)
@click.option(
    "--in",
    "scope",
    default=None,
    help='Restrict the search to a reference (e.g. "Gen 1", "John").',
)
@click.option(
    "--order",
    type=click.Choice(["canonical", "relevance"]),
    default="canonical",
    show_default=True,
    help="Result order: canonical (verse order) or relevance (bm25 rank).",
)
@click.option(
    "--style",
    default="en-sbl",
    show_default=True,
    help="Reference style for labelling output and parsing --in.",
)
def search(
    database: str,
    query: str,
    limit: int,
    scope: str | None,
    order: str,
    style: str,
) -> None:
    """Full-text search verse text with FTS5 QUERY.

    DATABASE is a Bible name on the search path (see ``list``) or a path to a
    ``.db`` file. QUERY uses SQLite FTS5 syntax (e.g. ``light``,
    ``"living water"``, ``love AND world``). Output is ``reference<TAB>text``, in
    canonical verse order by default (use ``--order relevance`` for bm25 ranking).
    """
    try:
        db_path = resolve_bible(database)
        verses, total, db_vers = search_verses(
            db_path, query, limit=limit, scope=scope, order=order, style_name=style
        )
        if not verses:
            click.echo("No matching verses.", err=True)
            return
        ref_style = RefStyle.named(style)
        for verse in verses:
            click.echo(format_verse(verse, ref_style, db_vers))
        if total > len(verses):
            click.echo(
                f"… showing {len(verses)} of {total} matches "
                f"(raise --limit to see more)",
                err=True,
            )
    except (ValueError, LookupError, IncompatibleDatabaseError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@main.command()
@click.argument("database")
def info(database: str) -> None:
    """Show metadata and verse count for a Bible database.

    DATABASE is a Bible name on the search path (see ``list``) or a path to a
    ``.db`` file.
    """
    try:
        db_path = resolve_bible(database)
        with Database(db_path) as db:
            db.validate_schema()
            metadata = db.get_all_metadata()
            count = db.count_verses()
        for key, value in metadata.items():
            click.echo(f"{key}: {value}")
        click.echo(f"verses: {count}")
    except (ValueError, OSError, IncompatibleDatabaseError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@main.command(name="list")
def list_command() -> None:
    """List the Bible databases found on the search path.

    Each line is ``name<TAB>versification<TAB>verses<TAB>title``; the name is
    what ``show``, ``search``, and ``info`` accept in place of a path. The search
    path comes from the VERSIREF_BIBLE_PATH environment variable
    (os.pathsep-separated); when unset it is a single per-user data directory.
    """
    path = bible_search_path()
    databases = list_bibles()
    if not databases:
        searched = os.pathsep.join(str(d) for d in path)
        click.echo(f"No Bible databases found on the search path ({searched}).", err=True)
        click.echo(
            f"Set {ENV_VAR} or place .db files in one of those directories.", err=True
        )
        return
    for db_file in databases:
        versification = ""
        title = ""
        count = ""
        try:
            with Database(db_file) as db:
                versification = db.get_metadata("versification") or ""
                title = db.get_metadata("title") or ""
                count = str(db.count_verses())
        except (sqlite3.Error, OSError):
            title = "(unreadable)"
        click.echo(f"{db_file.stem}\t{versification}\t{count}\t{title}")


@main.command()
@click.argument("name", required=False)
def docs(name: str | None) -> None:
    """Print the filesystem path to the bundled documentation.

    With no argument, prints the path to the bundled docs directory. Pass a
    file NAME (e.g., querying.md) to print the path to that single doc.
    """
    docs_dir = files("versiref.bible") / "docs"
    if name is not None:
        target = docs_dir / name
        if not target.is_file():
            click.echo(f"Error: no such doc: {name}", err=True)
            sys.exit(1)
        click.echo(str(target))
    else:
        click.echo(str(docs_dir))


if __name__ == "__main__":
    main()
