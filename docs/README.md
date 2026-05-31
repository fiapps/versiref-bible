# versiref-bible Documentation

versiref-bible stores a Bible in an SQLite database and serves its verses by reference or by
full-text search. It uses [versiref](https://github.com/fiapps/versiref) to parse references
and handle versification.

The CLI is designed for an LLM consumer: output is compact plain text, one verse per line as
`reference⇥text` (TAB-separated).

## For Database Consumers

If you have a versiref-bible database and want to read verses—by reference (`show`) or by
full-text search (`search`)—see **[Querying Databases](querying.md)**.
This covers the `show`, `search`, and `info` CLI commands, output format, and the Python API.

## For Database Producers

If you need to build a database from a CCAT-format Bible text file, see
**[Building Databases](building.md)**.
This covers the `build` CLI command, book-name styles, versification, encoding, and the
Python build API.
