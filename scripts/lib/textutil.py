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


# ---------------------------------------------------------------------------
# Transliterated Arabic
# ---------------------------------------------------------------------------
#
# Scripture spoken aloud does not arrive as Arabic script. Whisper, asked for
# Indonesian, writes what it hears in Latin letters: a verse comes back as
# "In nama ashku bathi wa huzni ilallah". contains_arabic() sees nothing, so
# the rule that Arabic is never cut does not fire on the very case it exists
# for.
#
# This recognises the SHAPE of a transliterated quotation. It is deliberately
# fallible and it never protects anything outright — a hit downgrades a
# proposal to review, so the cost of a false positive is a human glance and
# the cost of a false negative is bounded by a human still reading the report.
#
# The signal is a RUN, not a word. Indonesian religious speech is full of
# single Arabic-derived words — "akhirnya", "syukur", "ikhlas",
# "alhamdulillah" — and flagging those would bury the report in noise until
# nobody read it. Several Arabic-looking tokens close together is a different
# thing.

# Function words and particles that carry a quotation. These are not
# Indonesian words, so one of them is already meaningful.
_ARABIC_FUNCTION_WORDS = frozenset(
    {
        "inna", "innama", "innallaha", "anna", "annahu", "an",
        "qala", "qaala", "qul", "yaqulu",
        "wa", "fa", "bi", "li", "min", "fi", "fii", "fiihi", "ila", "ilaa",
        "ala", "alaa", "alaihi", "alaihim", "alaihis",
        "ma", "maa", "man", "la", "laa", "illa", "illaa", "lam", "lan",
        "lahu", "lahum", "hum", "huma", "hu", "hi",
        "anta", "antum", "nahnu", "kum", "naa", "bihi", "minhu",
        "allazi", "alladzi", "alladzina", "allati", "hadza", "haadza",
        "dzalika", "kana", "yakunu", "kullu", "kulli",
        # compounds: unlike bare "allah", these only occur inside Arabic
        "ilallah", "lillah", "billah", "illallah", "minallah", "walllah",
        "allahumma", "rabbana", "rabbi", "rabbanaa", "rabbil",
        "subhanahu", "wataala", "taala", "azza", "jalla",
        "shallallahu", "radhiyallahu", "wasallam", "wabarakatuh",
    }
)

# Everyday Indonesian interjections of Arabic origin. Arabic-looking, but on
# their own they mean nothing about scripture, so they count for half.
_COMMON_FORMULAE = frozenset(
    {
        "allah", "allahu", "bismillah", "alhamdulillah", "subhanallah",
        "insyaallah", "insya", "masyaallah", "astaghfirullah", "amin", "aamiin",
        "ya", "yaa",
    }
)

# Spellings that transliteration produces and ordinary Indonesian rarely
# needs. Weak on their own — plenty of absorbed vocabulary matches.
#
# The doubled consonants are gemination (shadda) written out: "inni",
# "rabbi", "minni". 'g' is excluded deliberately — "tinggi", "minggu",
# "tunggu", "panggil" are everyday Indonesian and would fire constantly.
_TRANSLITERATION_MARKS = re.compile(
    r"(dz|ts|sy|kh|gh|zh|th|sh|aa|ii|uu|'|bb|dd|ff|kk|ll|mm|nn|pp|rr|ss|tt|zz)"
)

_TOKEN_SPLIT = re.compile(r"[^\w']+", re.UNICODE)

_STRONG = 1.0
_WEAK = 0.5
# A run is judged over this many consecutive tokens...
RUN_WINDOW = 6
# ...and needs this much weight inside it. Two strong words and one spelling
# hint, or equivalent. One Arabic loanword in a sentence cannot reach it.
RUN_THRESHOLD = 2.5


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens, apostrophes kept — they are transliteration."""
    return [t for t in _TOKEN_SPLIT.split(text.lower()) if t]


def arabic_weight(token: str) -> float:
    """How much this single token suggests transliterated Arabic."""
    word = normalize_word(token)
    if not word:
        return 0.0
    if word in _ARABIC_FUNCTION_WORDS:
        return _STRONG
    if word in _COMMON_FORMULAE:
        return _WEAK
    if _TRANSLITERATION_MARKS.search(word):
        return _WEAK
    return 0.0


def transliteration_runs(
    tokens: list[str],
    *,
    window: int = RUN_WINDOW,
    threshold: float = RUN_THRESHOLD,
) -> list[tuple[int, int]]:
    """Index ranges (inclusive) of tokens that look like quoted Arabic.

    Overlapping windows are merged, so a long verse comes back as one run
    rather than a scatter of fragments.
    """
    if not tokens:
        return []

    weights = [arabic_weight(t) for t in tokens]
    hits: list[tuple[int, int]] = []

    for start in range(len(tokens)):
        end = min(len(tokens), start + window)
        if sum(weights[start:end]) < threshold:
            continue
        # Tighten to the first and last contributing token, so the run does
        # not advertise Indonesian words on either side as scripture.
        inside = [i for i in range(start, end) if weights[i] > 0]
        hits.append((inside[0], inside[-1]))

    if not hits:
        return []

    merged: list[tuple[int, int]] = [hits[0]]
    for lo, hi in hits[1:]:
        last_lo, last_hi = merged[-1]
        if lo <= last_hi + 1:
            merged[-1] = (last_lo, max(last_hi, hi))
        else:
            merged.append((lo, hi))
    return merged


def looks_transliterated(text: str) -> bool:
    """Convenience: does this text contain a suspected Arabic quotation?"""
    return bool(transliteration_runs(tokenize(text)))
