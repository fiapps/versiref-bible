"""Strip BibleWorks-style CCAT markup from verse text.

BibleWorks exports decorate the plain verse text with several kinds of inline
markup, all of which get in the way of full-text search and of clean output:

- ``{...}`` footnote blocks after the verse text (cross-references and
  translator's notes). Some exports omit the closing brace on the last block,
  so an unterminated block runs to the end of the line; others emit a stray
  closing brace at the end of a line with no opening brace.
- ``<N1>``/``<Ra>`` markers anchoring those notes in the text.
- ``<0430>`` Strong's numbers (a leading zero marks a Hebrew number) and
  ``(08799)`` tense/voice/mood codes.
- ``[word]`` italics marking words supplied by the translator; the word itself
  is part of the translation and is kept.
- ``<<A Psalm of David.>>`` Psalm superscriptions (KJV); the title text is
  part of the verse and is kept.

Stripping is pattern-based and tolerant: only recognized markup is removed,
and anything unrecognized is left in the text (see :func:`has_markup_residue`).
"""

import re

# A footnote block, terminated by "}" or by the end of the line.
_NOTE_BLOCK = re.compile(r"\s*\{.*?(?:\}|$)")
# A stray closing brace at the end of a line whose opening brace is missing.
_STRAY_BRACE = re.compile(r"\s*\}\s*$")
# A Psalm superscription (KJV): unwrap, keeping the title text.
_SUPERSCRIPTION = re.compile(r"<<([^<>]*)>>")
# A Strong's number, with the whitespace separating it from the word it tags.
_STRONGS = re.compile(r"\s*<0?\d{1,5}>")
# A tense/voice/mood code, likewise with its leading whitespace.
_TVM_CODE = re.compile(r"\s*\(\d{4,5}\)")
# A footnote (<N1>) or cross-reference (<Ra>) anchor. These attach directly
# to a word ("made<N1>", "<Ra>separated"), so no whitespace is consumed.
_NOTE_MARKER = re.compile(r"<(?:N\d{1,3}|R[a-z]{1,2})>")
# Italics for translator-supplied words: unwrap, keeping the words.
_ITALICS = re.compile(r"\[([^][]*)\]")

_RESIDUE = re.compile(r"[<>{}]")


def strip_markup(text: str) -> str:
    """Return ``text`` with recognized BibleWorks/CCAT markup removed.

    Footnote blocks, note anchors, Strong's numbers, and tense/voice/mood
    codes are deleted; ``[bracketed]`` italics and ``<<superscriptions>>``
    are unwrapped to their words. Unrecognized markup is left untouched.
    """
    text = _NOTE_BLOCK.sub("", text)
    text = _STRAY_BRACE.sub("", text)
    text = _STRONGS.sub("", text)
    text = _TVM_CODE.sub("", text)
    text = _NOTE_MARKER.sub("", text)
    # After the inner tags are gone: KJV superscriptions contain Strong's
    # numbers ("<<A Psalm <04210> of David <01732>...>>"), which would
    # otherwise keep the [^<>]* body from matching.
    text = _SUPERSCRIPTION.sub(r"\1", text)
    text = _ITALICS.sub(r"\1", text)
    return re.sub(r"  +", " ", text).strip()


def has_markup_residue(text: str) -> bool:
    """Report whether ``text`` still contains markup-like characters.

    Any of ``<``, ``>``, ``{``, ``}`` remaining after :func:`strip_markup`
    signals a markup shape this module does not recognize; the build tallies
    such lines so a new source file's quirks surface at build time.
    """
    return _RESIDUE.search(text) is not None
