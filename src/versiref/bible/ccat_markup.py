r"""Strip and extract BibleWorks-style CCAT markup from verse text.

BibleWorks exports decorate the plain verse text with several kinds of inline
markup, all of which get in the way of full-text search and of clean output:

- ``{...}`` footnote blocks after the verse text (cross-references and
  translator's notes). Some exports omit the closing brace on the last block,
  so an unterminated block runs to the end of the line; others emit a stray
  closing brace at the end of a line with no opening brace.
- ``<N1>``/``<Ra>`` markers anchoring those notes in the text.
- ``<0430>`` Strong's numbers (a leading zero marks a Hebrew number, a trailing
  letter a homograph) and ``(08799)`` tense/voice/mood codes.
- SGML-like formatting tags: ``<i>...</i>``, ``<sup>...</sup>``,
  ``<link b="Gen 1:1">...</>`` and the rest of the documented vocabulary, plus
  the HTML-ish ``<a id="...">`` and ``<br/>`` some exports emit. The tags go;
  the text they wrap is kept. ``<p>``/``<br/>`` mark a line break, so they
  leave a space behind.
- ``[word]`` italics marking words supplied by the translator; the word itself
  is part of the translation and is kept. ``[[`` and ``]]`` are the escape for
  a literal bracket (used for passages of doubtful authenticity) and collapse
  to ``[`` and ``]``. Bracket italics are an option of the BibleWorks
  compiler, and a text prepared without it uses brackets as printed
  characters; ``literal_brackets=True`` leaves every bracket as written.
- ``\Lord\`` small caps for the divine name; the word is kept.
- ``<<A Psalm of David.>>`` (KJV) and ``<A Psalm of David.>`` (NRSV) Psalm
  superscriptions; the title text is part of the verse and is kept.

Stripping is pattern-based and tolerant: only recognized markup is removed,
and anything unrecognized is left in the text (see :func:`has_markup_residue`).

:func:`extract_markup` returns the clean text together with the content the
markup carried: the translator's notes and cross-references of the footnote
blocks, the Strong's numbers with the words they tag, and the note anchors.
:func:`strip_markup` is the same operation keeping only the clean text.

One documented notation is deliberately not handled: the two-digit codes for
special Greek manuscript characters, which are bare digits inside Greek text
and so indistinguishable from ordinary digits without knowing the font.
"""

import re
from dataclasses import dataclass

from .models import Note

# The documented SGML-like formatting tags, plus the note/cross-reference
# tags of the BibleWorks example (<nsup>, <rsup>) and the HTML-ish tags real
# exports carry: <a id="..."> anchors (NETS) and <vs>N</vs> verse markers
# (CEI 2008). Each wraps text that is kept.
_FORMAT_NAMES = "b|i|h|gb|g|sup|sub|ee|sym|cyr|wing|link|nsup|rsup|a|vs"
# Tags standing for a line break rather than wrapping anything.
_BREAK_NAMES = "p|br"
# Tag attributes, e.g. the b="Gen 1:1" of a <link> or the id of an <a>.
_ATTRS = r'(?:\s+[A-Za-z][\w:.-]*\s*=\s*"[^"<>]*")*'

# A footnote block, terminated by "}" or by the end of the line. The group is
# the block's content.
_NOTE_BLOCK = re.compile(r"\s*\{(.*?)(?:\}|$)")
# The paragraph tag that starts each note of a footnote block.
_NOTE_BREAK = re.compile(r"<\s*p\s*>")
# One note of a footnote block: its kind (<nsup> for a translator's note,
# <rsup> for a cross-reference), its label, and its body.
_NOTE_ENTRY = re.compile(r"\s*<(nsup|rsup)>(.*?)</\1>(.*)", re.DOTALL)
# A stray closing brace at the end of a line whose opening brace is missing.
_STRAY_BRACE = re.compile(r"\s*\}\s*$")
# A Strong's number, with the whitespace separating it from the word it tags.
_STRONGS = re.compile(r"\s*<(0?\d{1,5})([a-z]?)>")
# Stands in for a Strong's number while the rest of the markup is stripped, so
# that the number's position can be read off the finished text.
_STRONGS_MARK = "\x02"
# A tense/voice/mood code, likewise with its leading whitespace.
_TVM_CODE = re.compile(r"\s*\(\d{4,5}\)")
# A footnote (<N1>) or cross-reference (<Ra>) anchor.
_NOTE_MARKER = r"<(?:N\d{1,3}|R[a-z]{1,3})>"
_ANCHOR = re.compile(r"<(N\d{1,3}|R[a-z]{1,3})>")
# Any closing tag, including the generic "</>" that closes a <link>.
_CLOSE_TAG = rf"<\s*/\s*(?:{_FORMAT_NAMES}|{_BREAK_NAMES})?\s*>"
# An opening or self-closing line-break tag.
_BREAK_TAG = re.compile(rf"<\s*(?:{_BREAK_NAMES})\b{_ATTRS}\s*/?\s*>")
# An opening or self-closing formatting tag. The Clementine Vulgate closes
# its <i> with a malformed "< i>", which this matches as an opening tag; the
# effect (drop the tag, keep the words) is the same either way.
_FORMAT_TAG = rf"<\s*/?\s*(?:{_FORMAT_NAMES})\b{_ATTRS}\s*/?\s*>"
# A run of adjacent tags, matched as one so that the text on either side of
# the run decides whether removing it needs to leave a space behind.
_TAG_RUN = re.compile(
    rf"(?:{_CLOSE_TAG}|{_BREAK_TAG.pattern}|{_FORMAT_TAG}|{_NOTE_MARKER})+"
)
# A Psalm superscription in double angle brackets (KJV): unwrap, keeping the
# title text.
_SUPERSCRIPTION = re.compile(r"<<([^<>]*)>>")
# A superscription in single angle brackets (NRSV, "<A Psalm of David.>").
# Recognized by shape once the real tags are gone: several words, and nothing
# with the ``name="value"`` shape of an attribute, so that an unrecognized
# tag is left alone rather than unwrapped into its attributes.
_BRACKETED_PROSE = re.compile(r"<(?![^<>]*=\")(?!\s*/)([^<>]*\s[^<>]*)>")
# Small caps for the divine name, marked by surrounding backslashes that hug
# the words they wrap ("the \LORD\ said"). A backslash is also the grave accent
# of Beta Code Greek ("qeo\s to\n", "kai\ th\n"), where it always *follows* a
# letter or another diacritic. So the opening backslash must start a word (not
# follow a letter or a Beta Code diacritic), and the closing one must end one.
_SMALL_CAPS = re.compile(
    r"(?<![\w()/=|+^*\\])\\(?=\S)([\w'\u2019 -]{1,40})(?<=\S)\\(?!\w)"
)
# Italics for translator-supplied words: unwrap, keeping the words.
_ITALICS = re.compile(r"\[([^][]*)\]")

# Escapes for a literal square bracket, parked out of the way of _ITALICS.
_BRACKET_ESCAPES = (("[[", "\x00"), ("]]", "\x01"))

_RESIDUE = re.compile(r"[<>{}]")


def _drop_tags(match: re.Match[str]) -> str:
    """Replace a run of tags with a space only where one is needed.

    A tag usually sits at a word boundary ("made<N1> the", "theraphin<a
    id=...></a>,") and leaves no gap to fill. But a stray anchor or a line
    break can fall between two words ("31.9<br/>follows"), and dropping the
    tag outright would weld them into a token no search would find.
    """
    if _BREAK_TAG.search(match.group()):
        return " "
    text = match.string
    before = text[match.start() - 1] if match.start() else ""
    after = text[match.end() : match.end() + 1]
    return " " if before.isalnum() and after.isalnum() else ""


@dataclass(frozen=True)
class StrongsTag:
    """A Strong's number and the words of the clean text it tags.

    The words are a span of ``text.split()``, running from the previous tag
    (or the start of the verse) to this one. The span is empty
    (``word_end == word_start``) when the tag follows another directly, as the
    untranslated ``<0853>`` does in the KJV's Gen 1:4.

    Attributes:
        lang: ``"H"`` for a Hebrew number (written with a leading zero) or
            ``"G"`` for a Greek one.
        number: The Strong's number.
        suffix: The letter distinguishing a homograph, or ``""``.
        word_start: Index of the first tagged word (0-based).
        word_end: Index after the last tagged word.

    """

    lang: str
    number: int
    suffix: str
    word_start: int
    word_end: int


@dataclass(frozen=True)
class ExtractedMarkup:
    """The clean text of a verse and the content its markup carried.

    Anchors and notes need not pair up: a verse can carry one ``<N1>`` anchor
    and four numbered notes (KJV Gen 1:20), so neither is derived from the
    other.

    Attributes:
        text: The verse text with recognized markup removed, as
            :func:`strip_markup` returns it.
        notes: Translator's notes (``<nsup>``) in block order, their bodies
            stripped of markup like the verse text.
        cross_references: Cross-references (``<rsup>``) in block order; each
            body is a reference list, stripped of markup but not parsed.
        strongs: Strong's numbers of the verse text in order of occurrence.
        anchors: Labels of the note (``N1``) and cross-reference (``Ra``)
            anchors found in the verse text, in order.

    """

    text: str
    notes: tuple[Note, ...] = ()
    cross_references: tuple[Note, ...] = ()
    strongs: tuple[StrongsTag, ...] = ()
    anchors: tuple[str, ...] = ()


def _clean(
    text: str, literal_brackets: bool = False
) -> tuple[str, tuple[StrongsTag, ...]]:
    """Strip inline markup from text holding no footnote block.

    Returns the clean text and its Strong's numbers. Each number is swapped
    for a mark that rides through the rest of the stripping, because the word
    offsets only mean something against the finished text: unwrapping and tag
    removal shift positions.
    """
    tags: list[tuple[str, str]] = []

    def mark(match: re.Match[str]) -> str:
        tags.append((match.group(1), match.group(2)))
        return _STRONGS_MARK

    text = text.replace(_STRONGS_MARK, "")
    text = _STRONGS.sub(mark, text)
    text = _TVM_CODE.sub("", text)
    text = _TAG_RUN.sub(_drop_tags, text)
    # After the inner tags are gone: KJV superscriptions contain Strong's
    # numbers ("<<A Psalm <04210> of David <01732>...>>"), which would
    # otherwise keep the [^<>]* body from matching. Likewise the single-angle
    # form must not see a tag's attributes and mistake them for prose.
    text = _SUPERSCRIPTION.sub(r"\1", text)
    text = _BRACKETED_PROSE.sub(r"\1", text)
    text = _SMALL_CAPS.sub(r"\1", text)
    if not literal_brackets:
        for escape, placeholder in _BRACKET_ESCAPES:
            text = text.replace(escape, placeholder)
        text = _ITALICS.sub(r"\1", text)
        for escape, placeholder in _BRACKET_ESCAPES:
            text = text.replace(placeholder, escape[0])

    strongs: list[StrongsTag] = []
    if tags:
        # A mark hugs the word it follows, so the words before it — counting
        # one it interrupts ("light<0216>,") — are the words tagged so far.
        pieces = text.split(_STRONGS_MARK)
        prefix = ""
        word_start = 0
        for (digits, suffix), piece in zip(tags, pieces, strict=False):
            prefix += piece
            word_end = len(prefix.split())
            lang = "H" if digits.startswith("0") else "G"
            strongs.append(StrongsTag(lang, int(digits), suffix, word_start, word_end))
            word_start = word_end
        text = "".join(pieces)
    return re.sub(r"\s{2,}", " ", text).strip(), tuple(strongs)


def extract_markup(text: str, *, literal_brackets: bool = False) -> ExtractedMarkup:
    r"""Strip recognized BibleWorks/CCAT markup, returning what it carried.

    The clean text is exactly what :func:`strip_markup` returns. Alongside it
    come the translator's notes and cross-references of the ``{...}`` footnote
    blocks (split at ``<p>``; a piece labelled neither ``<nsup>`` nor
    ``<rsup>`` is discarded), the Strong's numbers of the verse text with the
    word spans they tag, and the labels of the note anchors.

    Strong's numbers inside a footnote block belong to the note, not the
    verse, and are dropped with the rest of the note's markup.

    With ``literal_brackets=True`` square brackets are printed characters:
    ``[word]`` is not unwrapped as italics and ``[[`` is two brackets, not an
    escape for one. This holds for the note bodies as for the verse text.
    """
    blocks: list[str] = []

    def take_block(match: re.Match[str]) -> str:
        blocks.append(match.group(1))
        return ""

    text = _NOTE_BLOCK.sub(take_block, text)
    text = _STRAY_BRACE.sub("", text)
    anchors = tuple(_ANCHOR.findall(text))
    clean, strongs = _clean(text, literal_brackets)

    notes: list[Note] = []
    cross_references: list[Note] = []
    for block in blocks:
        for piece in _NOTE_BREAK.split(block):
            entry = _NOTE_ENTRY.fullmatch(piece)
            if entry is None:
                continue
            kind, label, body = entry.groups()
            note = Note(_clean(label)[0], _clean(body, literal_brackets)[0])
            (notes if kind == "nsup" else cross_references).append(note)

    return ExtractedMarkup(
        text=clean,
        notes=tuple(notes),
        cross_references=tuple(cross_references),
        strongs=strongs,
        anchors=anchors,
    )


def strip_markup(text: str, *, literal_brackets: bool = False) -> str:
    r"""Return ``text`` with recognized BibleWorks/CCAT markup removed.

    Footnote blocks, note anchors, Strong's numbers, tense/voice/mood codes,
    and SGML-like formatting tags are deleted; ``[bracketed]`` italics,
    ``\smallcaps\``, ``<<superscriptions>>``, and the text wrapped by
    formatting tags are kept. Unrecognized markup is left untouched.

    With ``literal_brackets=True`` square brackets are left as written
    instead of being read as italics and bracket escapes.
    """
    return extract_markup(text, literal_brackets=literal_brackets).text


def has_markup_residue(text: str) -> bool:
    """Report whether ``text`` still contains markup-like characters.

    Any of ``<``, ``>``, ``{``, ``}`` remaining after :func:`strip_markup`
    signals a markup shape this module does not recognize; the build tallies
    such lines so a new source file's quirks surface at build time.
    """
    return _RESIDUE.search(text) is not None
