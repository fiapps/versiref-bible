r"""Convert Beta Code Greek to Unicode.

Beta Code writes polytonic Greek in ASCII: a Latin letter for each Greek one
(``q`` for theta, ``w`` for omega) followed by marks for its breathing,
accent, diaeresis, and iota subscript, so that ``e)n a)rxh^|`` is ἐν ἀρχῇ.
Some CCAT exports, such as the BibleWorks Rahlfs Septuagint, are encoded this
way.

Two conventions for capitals are accepted. BibleWorks writes an uppercase
Latin letter with the marks after it (``A)ssuri/wn``); the TLG writes an
asterisk, then the marks, then the letter (``*)assuri/wn``). The case of a
letter otherwise carries over, so a TLG file in the all-uppercase form (where
``A`` is a *lowercase* alpha) is not supported.

Conversion is tolerant, like markup stripping: whatever is not a letter with
its marks is left as it stands, and a mark that cannot belong to the letter
before it (the ``)`` closing a parenthesis after a consonant) is kept as
written.
"""

import re
import unicodedata

# The value of ``--encoding`` (``build_database(encoding=...)``) that selects
# Beta Code, handled here rather than by Python's codecs.
BETA_CODE = "beta-code"

_LETTERS = {
    "a": "α",
    "b": "β",
    "g": "γ",
    "d": "δ",
    "e": "ε",
    "z": "ζ",
    "h": "η",
    "q": "θ",
    "i": "ι",
    "k": "κ",
    "l": "λ",
    "m": "μ",
    "n": "ν",
    "c": "ξ",
    "o": "ο",
    "p": "π",
    "r": "ρ",
    "s": "σ",
    "t": "τ",
    "u": "υ",
    "f": "φ",
    "x": "χ",
    "y": "ψ",
    "w": "ω",
    "v": "ϝ",
    # Some texts mark a final sigma explicitly.
    "j": "ς",
}

# Each mark's combining character, and its place in the canonical order: a
# breathing or diaeresis, then an accent, then the iota subscript. The
# circumflex is "=" in TLG Beta Code and "^" in BibleWorks'.
_MARKS = {
    ")": (0, "̓"),
    "(": (0, "̔"),
    "+": (0, "̈"),
    "/": (1, "́"),
    "\\": (1, "̀"),
    "^": (1, "͂"),
    "=": (1, "͂"),
    "|": (2, "ͅ"),
}

_MARK_CLASS = r"[)(+/\\^=|]"
# A letter with its marks: the marks follow it, or (TLG capitals) stand
# between the asterisk and the letter.
_LETTER = re.compile(rf"(\*{_MARK_CLASS}*)?([A-Za-z])({_MARK_CLASS}*)")


def _compose(base: str, marks: str) -> str | None:
    """Return the single character for a letter and its marks, if there is one."""
    combining = sorted(_MARKS[mark] for mark in marks)
    composed = unicodedata.normalize(
        "NFC", base + "".join(char for _, char in combining)
    )
    return composed if len(composed) == 1 else None


def _convert(match: re.Match[str]) -> str:
    prefix, letter, marks = match.group(1) or "", match.group(2), match.group(3)
    base = _LETTERS.get(letter.lower())
    if base is None:
        # Not a Beta Code letter: leave the whole sequence alone.
        return match.group()
    if prefix or letter.isupper():
        base = base.upper()
    elif letter == "s":
        # A sigma ending its word is final. No mark belongs to a sigma, so
        # one after it is punctuation and ends the word too ("o(/s)").
        after = match.string[match.end() : match.end() + 1]
        if marks or not ((after.isascii() and after.isalpha()) or after == "*"):
            base = "ς"

    marks = prefix[1:] + marks
    # Keep the longest run of marks that makes one character with the letter;
    # whatever follows is ordinary punctuation, kept as written.
    for count in range(len(marks), -1, -1):
        composed = _compose(base, marks[:count])
        if composed is not None:
            return composed + marks[count:]
    return match.group()


def beta_to_unicode(text: str) -> str:
    r"""Return Beta Code Greek ``text`` as Unicode (NFC) Greek.

    ``e)n a)rxh^| e)poi/hsen o( qeo\s`` becomes ``ἐν ἀρχῇ ἐποίησεν ὁ θεὸς``.
    An apostrophe marking an elision (``a)nt' au)tou^``) becomes ``’``.
    Digits, brackets, and other punctuation are unchanged.
    """
    return _LETTER.sub(_convert, text).replace("'", "’")


def is_beta_code(encoding: str) -> bool:
    """Report whether an ``encoding`` value names Beta Code."""
    return encoding.lower().replace("_", "-") in (BETA_CODE, "betacode")
