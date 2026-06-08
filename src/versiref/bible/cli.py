"""Command-line interface for versiref-bible."""

import sys
from pathlib import Path

import click
from versiref import RefStyle

from .builder import build_database
from .database import Database
from .models import BuildStats
from .reader import format_verse, search_verses, show_verses


@click.group()
@click.version_option(package_name="versiref-bible")
def main() -> None:
    """Access Bibles stored in an SQLite database with versiref."""
    pass


def _report_build(stats: BuildStats, output: Path) -> None:
    """Print a build summary, sending skip warnings to stderr."""
    click.echo(f"✓ Built {output} ({stats.stored} verses)")
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
    default=None,
    help="Output database path [default: INPUT with a .db suffix]",
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
def build(
    input_file: Path,
    output_file: Path | None,
    versification: str,
    title: str | None,
    book_style: str,
    encoding: str,
) -> None:
    """Build a Bible database from a CCAT-format text file.

    Each line of INPUT_FILE is read as ``Abbrev C:V text``. Lines whose book
    abbreviation is unrecognized, or whose book is not in the chosen
    versification, are skipped with a warning.
    """
    output = output_file or input_file.with_suffix(".db")
    try:
        stats = build_database(
            input_file,
            output,
            versification=versification,
            title=title,
            book_style=book_style,
            encoding=encoding,
        )
        _report_build(stats, output)
    except (ValueError, LookupError, OSError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@main.command()
@click.argument(
    "database", type=click.Path(exists=True, dir_okay=False, path_type=Path)
)
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
    database: Path,
    reference: str,
    style: str,
    from_versification: str | None,
) -> None:
    """Print the verses covered by a Bible REFERENCE, one per line.

    Each line is ``reference<TAB>text``.
    """
    try:
        verses, db_vers = show_verses(
            database,
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
    except (ValueError, LookupError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@main.command()
@click.argument(
    "database", type=click.Path(exists=True, dir_okay=False, path_type=Path)
)
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
    database: Path,
    query: str,
    limit: int,
    scope: str | None,
    order: str,
    style: str,
) -> None:
    """Full-text search verse text with FTS5 QUERY.

    QUERY uses SQLite FTS5 syntax (e.g. ``light``, ``"living water"``,
    ``love AND world``). Output is ``reference<TAB>text``, in canonical verse
    order by default (use ``--order relevance`` for bm25 ranking).
    """
    try:
        verses, total, db_vers = search_verses(
            database, query, limit=limit, scope=scope, order=order, style_name=style
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
    except (ValueError, LookupError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


@main.command()
@click.argument(
    "database", type=click.Path(exists=True, dir_okay=False, path_type=Path)
)
def info(database: Path) -> None:
    """Show metadata and verse count for a Bible database."""
    try:
        with Database(database) as db:
            metadata = db.get_all_metadata()
            count = db.count_verses()
        for key, value in metadata.items():
            click.echo(f"{key}: {value}")
        click.echo(f"verses: {count}")
    except (ValueError, OSError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
