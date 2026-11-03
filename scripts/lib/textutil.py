"""Text helpers for editorial reasoning on Indonesian speech.

Deliberately conservative: this module only *recognises* things. It never
rewrites a spoken word, and it never decides on its own that something should
be removed.
"""

from __future__ import annotations

import re
import unicodedata

# Arabic script blocks: core, supplement, extended-A, presentation forms.
_ARABIC_RANGES = (
    (0x0600, 0x06FF),
    (0x0750, 0x077F),
    (0x08A0, 0x08FF),
    (0xFB50, 0xFDFF),
    (0xFE70, 0xFEFF),
)

# Hesitation sounds only. Real Indonesian discourse markers ("jadi", "nah",
# "ya", "kan", "itu") are NOT listed: removing them changes how a sentence
# reads, which the editorial rules forbid.
HESITATION_SOUNDS = frozenset(
    {
        "e", "ee", "eee", "eeee",
        "eh", "ehh",
        "em", "emm", "emmm",
        "mm", "mmm",
        "hmm", "hmmm",
        "anu", "anu-anu",
        "apaa", "apah",
    }
)

_PUNCT_STRIP = re.compile(r"^[^\w؀-ۿ]+|[^\w؀-ۿ]+$", re.UNICODE)


def contains_arabic(text: str) -> bool:
    """True when any character falls in an Arabic script block."""
    for char in text:
        code = ord(char)
        for low, high in _ARABIC_RANGES:
            if low <= code <= high:
                return True
    return False


def normalize_word(word: str) -> str:
    """Comparison form for repetition detection: lowercase, punctuation stripped.

    Used only to compare words with each other — the original spelling from the
    transcript is always what gets stored and displayed.
    """
    text = unicodedata.normalize("NFKC", word).strip().lower()
    return _PUNCT_STRIP.sub("", text)


def is_hesitation(word: str) -> bool:
    return normalize_word(word) in HESITATION_SOUNDS


def ends_question(text: str) -> bool:
    """A pause after a question is rhetorical weight, not dead air."""
    return text.rstrip().endswith(("?", "؟"))


def ends_sentence(text: str) -> bool:
    return text.rstrip().endswith((".", "!", "?", "…", "؟"))
