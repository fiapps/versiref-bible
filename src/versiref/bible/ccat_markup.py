r"""Strip BibleWorks-style CCAT markup from verse text.

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
  to ``[`` and ``]``.
- ``\Lord\`` small caps for the divine name; the word is kept.
- ``<<A Psalm of David.>>`` (KJV) and ``<A Psalm of David.>`` (NRSV) Psalm
  superscriptions; the title text is part of the verse and is kept.

Stripping is pattern-based and tolerant: only recognized markup is removed,
and anything unrecognized is left in the text (see :func:`has_markup_residue`).

One documented notation is deliberately not handled: the two-digit codes for
special Greek manuscript characters, which are bare digits inside Greek text
and so indistinguishable from ordinary digits without knowing the font.
"""

import re

# The documented SGML-like formatting tags, plus the note/cross-reference
# tags of the BibleWorks example (<nsup>, <rsup>) and the HTML-ish tags real
# exports carry: <a id="..."> anchors (NETS) and <vs>N</vs> verse markers
# (CEI 2008). Each wraps text that is kept.
_FORMAT_NAMES = "b|i|h|gb|g|sup|sub|ee|sym|cyr|wing|link|nsup|rsup|a|vs"
# Tags standing for a line break rather than wrapping anything.
_BREAK_NAMES = "p|br"
# Tag attributes, e.g. the b="Gen 1:1" of a <link> or the id of an <a>.
_ATTRS = r'(?:\s+[A-Za-z][\w:.-]*\s*=\s*"[^"<>]*")*'

# A footnote block, terminated by "}" or by the end of the line.
_NOTE_BLOCK = re.compile(r"\s*\{.*?(?:\}|$)")
# A stray closing brace at the end of a line whose opening brace is missing.
_STRAY_BRACE = re.compile(r"\s*\}\s*$")
# A Strong's number, with the whitespace separating it from the word it tags.
_STRONGS = re.compile(r"\s*<0?\d{1,5}[a-z]?>")
# A tense/voice/mood code, likewise with its leading whitespace.
_TVM_CODE = re.compile(r"\s*\(\d{4,5}\)")
# A footnote (<N1>) or cross-reference (<Ra>) anchor.
_NOTE_MARKER = r"<(?:N\d{1,3}|R[a-z]{1,3})>"
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
# Small caps for the divine name, marked by surrounding backslashes.
_SMALL_CAPS = re.compile(r"\\([\w'\u2019 -]{1,40})\\")
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


def strip_markup(text: str) -> str:
    r"""Return ``text`` with recognized BibleWorks/CCAT markup removed.

    Footnote blocks, note anchors, Strong's numbers, tense/voice/mood codes,
    and SGML-like formatting tags are deleted; ``[bracketed]`` italics,
    ``\smallcaps\``, ``<<superscriptions>>``, and the text wrapped by
    formatting tags are kept. Unrecognized markup is left untouched.
    """
    text = _NOTE_BLOCK.sub("", text)
    text = _STRAY_BRACE.sub("", text)
    text = _STRONGS.sub("", text)
    text = _TVM_CODE.sub("", text)
    text = _TAG_RUN.sub(_drop_tags, text)
    # After the inner tags are gone: KJV superscriptions contain Strong's
    # numbers ("<<A Psalm <04210> of David <01732>...>>"), which would
    # otherwise keep the [^<>]* body from matching. Likewise the single-angle
    # form must not see a tag's attributes and mistake them for prose.
    text = _SUPERSCRIPTION.sub(r"\1", text)
    text = _BRACKETED_PROSE.sub(r"\1", text)
    text = _SMALL_CAPS.sub(r"\1", text)
    for escape, placeholder in _BRACKET_ESCAPES:
        text = text.replace(escape, placeholder)
    text = _ITALICS.sub(r"\1", text)
    for escape, placeholder in _BRACKET_ESCAPES:
        text = text.replace(placeholder, escape[0])
    return re.sub(r"\s{2,}", " ", text).strip()


def has_markup_residue(text: str) -> bool:
    """Report whether ``text`` still contains markup-like characters.

    Any of ``<``, ``>``, ``{``, ``}`` remaining after :func:`strip_markup`
    signals a markup shape this module does not recognize; the build tallies
    such lines so a new source file's quirks surface at build time.
    """
    return _RESIDUE.search(text) is not None
