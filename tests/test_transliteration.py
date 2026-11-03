"""Scripture written in Latin letters.

Run from the engine root:

    python -m tests.test_transliteration

Arabic script becomes a protected region. Scripture spoken aloud never
arrives as Arabic script — the transcriber writes what it hears — so the rule
that matters most was not firing on the case it exists for. This covers the
detector that notices the shape of a transliterated quotation, and the fact
that a hit only ever makes a proposal MORE cautious.

The Indonesian lines below are real: they are what the transcriber produced
from the presenter's own recording. Exactly one of them is scripture, which
makes them the only honest false-positive test available.
"""

from __future__ import annotations

import sys

from scripts.lib.textutil import (
    arabic_weight,
    contains_arabic,
    looks_transliterated,
    tokenize,
    transliteration_runs,
)
from scripts.stages.s04_edl import (
    STATUS_AUTO,
    STATUS_BLOCKED,
    STATUS_REVIEW,
    _flag_suspected,
    _suspected_transliteration,
    _untranscribed_spans,
)

# From the presenter's recording. The verse is at index 9.
REAL_SPEECH = [
    "Udahlah move on aja gak sih?",
    "Kalimat itu bukan sesuatu yang baru.",
    "Ribuan tahun yang lalu, anak-anaknya Nabi Yaakob sudah mengatakan kalimat itu kepada bapaknya sendiri.",
    "Bahkan dengan versi jauh lebih kasar.",
    "Bapak itu gak pernah berhenti nyebut Yusuf sampai hancur bahkan sampai mati.",
    "Bayangin, yang ngomong kayak gitu bukan tetangga.",
    "Tapi anak-anaknya sendiri.",
    "Dan Nabi Yaakob gak pernah bantah.",
    "Nabi Yaakob cuma mindahin alamat kesedihannya.",
    "In nama ashku bathi wa huzni ilallah.",
    "Aku hanya mengadukan bathku dan huzinku kepada Allah.",
    "Sebagian ahli tafsir, menyebut kata itu berbeda.",
    "Bath itu sesuatu yang tampak di depan manusia.",
    "Sedangkan huzni, kesedihan, itu sesuatu yang tidak tampak di hadapan manusia.",
    "Atau sesuatu yang tidak bisa kita tampakkan.",
    "Jadi yang ditambah Nabi Yaakob itu bukan besarnya tangis.",
    "banyaknya tangisan sebenarnya bukan tanda lemahnya keimanan.",
    "Sesuatu yang kita pikul sendiri bukan karena orang tahu.",
    "Tetapi karena memang kita sendiri susah untuk mengungkapkannya.",
    "Atau bahkan orang lain gak bisa dengar apa yang kita pikul.",
    "tapi satu-satunya yang sanggup mendengar keluh kesah kita malah kita gak pernah datangi.",
]
VERSE = 9

_failures: list[str] = []
_checks = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global _checks
    _checks += 1
    if condition:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}" + (f" — {detail}" if detail else ""))
        _failures.append(label)


def word(w: str, start: float, end: float) -> dict:
    return {"word": w, "start": start, "end": end}


def main() -> int:
    print("The gap this exists to close")
    verse = REAL_SPEECH[VERSE]
    check("the verse carries no Arabic script at all", not contains_arabic(verse))
    check("so the script-based rule cannot see it", not contains_arabic(verse))
    check("but the shape is recognised", looks_transliterated(verse))

    print("\nAgainst the presenter's real speech")
    fired = [i for i, t in enumerate(REAL_SPEECH) if looks_transliterated(t)]
    check("the verse is caught", VERSE in fired)
    check("nothing else fires", fired == [VERSE],
          f"also fired: {[REAL_SPEECH[i][:40] for i in fired if i != VERSE]}")

    print("\nSingle words are never enough")
    # Indonesian religious speech is full of these. If one word could fire,
    # the report would be noise and nobody would read it.
    for ordinary in ("Alhamdulillah kita mulai", "Akhirnya syukur dan ikhlas",
                     "Insya Allah besok lanjut", "Masyaallah tinggi sekali"):
        check(f"{ordinary!r} does not fire", not looks_transliterated(ordinary))

    print("\nWeighting")
    check("an Arabic particle counts fully", arabic_weight("inna") == 1.0)
    check("an everyday formula counts half", arabic_weight("alhamdulillah") == 0.5)
    check("a spelling hint counts half", arabic_weight("ashku") == 0.5)
    check("a plain Indonesian word counts nothing", arabic_weight("sendiri") == 0.0)
    check("gemination is a hint", arabic_weight("rabbi") > 0.0)
    check("Indonesian double-g is not", arabic_weight("tinggi") == 0.0)
    check("empty input is harmless", arabic_weight("") == 0.0)

    print("\nRuns")
    check("no tokens, no runs", transliteration_runs([]) == [])
    toks = tokenize(verse)
    runs = transliteration_runs(toks)
    check("the verse yields exactly one run", len(runs) == 1, f"got {len(runs)}")
    if runs:
        lo, hi = runs[0]
        span = " ".join(toks[lo : hi + 1])
        check("the run stops at the Arabic words", span.endswith("ilallah"), f"got {span!r}")
        check("the run does not open on an Indonesian word",
              not span.startswith("nama"), f"got {span!r}")

    print("\nRegions from timed words")
    words = [
        word("Nabi", 0.0, 0.4), word("Yaakob", 0.4, 0.9), word("berkata", 0.9, 1.4),
        word("In", 2.0, 2.2), word("nama", 2.2, 2.5), word("ashku", 2.5, 3.0),
        word("bathi", 3.0, 3.5), word("wa", 3.5, 3.7), word("huzni", 3.7, 4.2),
        word("ilallah", 4.2, 4.9),
        word("begitu", 6.0, 6.5), word("katanya", 6.5, 7.0),
    ]
    regions = _suspected_transliteration(words)
    check("one region is found", len(regions) == 1, f"got {len(regions)}")
    if regions:
        r = regions[0]
        check("it starts inside the quotation", r["start"] >= 2.0, f"got {r['start']}")
        check("it ends with the quotation", abs(r["end"] - 4.9) < 1e-6, f"got {r['end']}")
        check("it does not swallow the words after it", r["end"] < 6.0)
        check("it is labelled as suspected, not protected",
              r["reason"] == "possible_transliterated_scripture")
        check("it carries an id", r["id"].startswith("sus-"))
    check("no words, no regions", _suspected_transliteration([]) == [])

    print("\nSpeech that was never written down")
    # From the presenter's recording: he recites a verse, and the transcriber
    # collapsed 5.58s of it into the word "hanya" at confidence 1.00. No
    # Arabic script, no transliterated text, no low confidence — only the
    # clock shows it.
    recited = [
        word("Nabi", 46.63, 48.31), word("Yaakob", 48.31, 48.67),
        word("Aku", 54.87, 56.25),
        word("hanya", 56.25, 61.83),       # 5.58s for one word
        word("mengadukan", 61.83, 62.61),
    ]
    spans = _untranscribed_spans(recited, 2.0)
    check("the over-long word is found", len(spans) == 1, f"got {len(spans)}")
    if spans:
        s = spans[0]
        check("it spans exactly that word",
              abs(s["start"] - 56.25) < 1e-6 and abs(s["end"] - 61.83) < 1e-6)
        check("it is labelled untranscribed_speech", s["reason"] == "untranscribed_speech")
        check("the note gives the duration", "5.58" in s["note"], s["note"][:60])
    check("ordinary word lengths are left alone",
          _untranscribed_spans([word("Nabi", 0.0, 1.2), word("Yaakob", 1.2, 1.9)], 2.0) == [])
    check("the threshold is honoured",
          len(_untranscribed_spans([word("x", 0.0, 2.4)], 3.0)) == 0
          and len(_untranscribed_spans([word("x", 0.0, 2.4)], 2.0)) == 1)
    check("no words, no spans", _untranscribed_spans([], 2.0) == [])

    print("\nIt only ever makes a proposal more cautious")
    region = regions[0] if regions else {"id": "sus-0001", "start": 2.0, "end": 4.9}
    proposals = [
        {"id": "p1", "start": 3.0, "end": 3.4, "status": STATUS_AUTO, "reason": "Dead air."},
        {"id": "p2", "start": 3.0, "end": 3.4, "status": STATUS_REVIEW, "reason": "Unclear."},
        {"id": "p3", "start": 3.0, "end": 3.4, "status": STATUS_BLOCKED, "reason": "Refused."},
        {"id": "p4", "start": 8.0, "end": 8.4, "status": STATUS_AUTO, "reason": "Dead air."},
    ]
    flagged = {p["id"]: p for p in _flag_suspected(proposals, [region])}
    check("an auto cut inside the span becomes review",
          flagged["p1"]["status"] == STATUS_REVIEW, flagged["p1"]["status"])
    check("a review stays review", flagged["p2"]["status"] == STATUS_REVIEW)
    check("a blocked cut is NOT loosened", flagged["p3"]["status"] == STATUS_BLOCKED)
    check("a cut outside the span is untouched",
          flagged["p4"]["status"] == STATUS_AUTO and flagged["p4"]["reason"] == "Dead air.")
    check("the downgraded proposal says why",
          "sus-" in flagged["p1"]["reason"] and "decide" in flagged["p1"]["reason"].lower())
    check("nothing happens when there is nothing suspected",
          all(p["status"] == s for p, s in zip(
              _flag_suspected(
                  [{"id": "q", "start": 0, "end": 1, "status": STATUS_AUTO, "reason": "x"}], []
              ),
              [STATUS_AUTO],
          )))

    print(f"\n{_checks - len(_failures)}/{_checks} checks passed")
    if _failures:
        print("\nFailed:")
        for failure in _failures:
            print(f"  - {failure}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
