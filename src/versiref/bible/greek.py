"""Fold Greek text for full-text search.

SQLite's FTS5 tokenizer folds case and strips the diacritics of Latin
letters, but leaves polytonic Greek as written, so ``θεὸς``, ``θεός``, and
``θεος`` would index as three different words — and the grave and acute
forms alternate with a word's position in the sentence. The build therefore
indexes Greek folded, and a search folds its query the same way.
"""

import unicodedata


def _is_greek(char: str) -> bool:
    """Report whether ``char`` is in the Greek or Greek Extended block."""
    return "Ͱ" <= char <= "Ͽ" or "ἀ" <= char <= "῿"


def fold_greek(text: str) -> str:
    """Return ``text`` with its Greek letters stripped of diacritics.

    Breathings, accents, diaereses, and iota subscripts are dropped and a
    final sigma becomes an ordinary one (so that ``ΘΕΟΣ`` matches ``θεός``
    once the tokenizer folds case). Everything that is not Greek, including
    the syntax of a search query, is returned unchanged.
    """
    if text.isascii():
        return text
    folded: list[str] = []
    for char in text:
        if not _is_greek(char):
            folded.append(char)
            continue
        base = "".join(
            part
            for part in unicodedata.normalize("NFD", char)
            if not unicodedata.combining(part)
        )
        folded.append("σ" if base == "ς" else base)
    return "".join(folded)
