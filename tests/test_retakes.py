"""Repeated takes, and moments not looking at the lens.

Run from the engine root:

    python -m tests.test_retakes

Both came from the presenter watching his own cut and saying what was wrong
with it: sentences he had said twice were still in, and there were moments
where he glanced at his notes.

The repetition rule that already existed works on short n-grams a moment
apart — a stutter, a doubled word. It cannot see a whole sentence delivered,
fumbled, and delivered again seconds later, which is what actually happens
while recording.

Neither check is ever allowed to decide. Deliberate repetition is a real
device, and a glance away can be a glance at anything.
"""

from __future__ import annotations

import sys

from scripts.lib.config import cutting_profile, load_config
from scripts.lib.faces import FaceSample, attention_spans
from scripts.stages.s04_edl import STATUS_REVIEW, _retake_proposals

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


def seg(start: float, end: float, text: str) -> dict:
    return {"start": start, "end": end, "text": text}


def transcript(*segments: dict) -> dict:
    return {"segments": list(segments)}


def sample(t: float, yaw: float = 0.0, eye_mouth: float = 1.0) -> FaceSample:
    return FaceSample(time=t, cx=500, cy=400, w=300, score=0.9, yaw=yaw, eyeMouth=eye_mouth)


def main() -> int:
    profile = cutting_profile(load_config())

    print("A sentence said twice")
    # Taken from the real recording: the line restarts, dragging a wrong
    # continuation with it.
    real = transcript(
        seg(110.11, 112.21, "Tanda lemahnya keimanan"),
        seg(114.16, 116.68, "Sesuatu yang kita pikul sendiri"),
        seg(118.26, 120.54, "Bukan karena orang taun"),
        seg(121.88, 123.82, "Sesuatu yang kita pikul sendiri"),
        seg(123.82, 126.80, "Bukan karena orang lain gak boleh tau loh ya"),
    )
    props = _retake_proposals(real, [], profile)
    check("the retake is found", len(props) == 1, f"got {len(props)}")
    if props:
        p = props[0]
        check("it never decides for you", p["status"] == STATUS_REVIEW, p["status"])
        check("it removes the first delivery", abs(p["start"] - 114.16) < 1e-6, str(p["start"]))
        check("it runs up to the second one", abs(p["end"] - 121.88) < 1e-6, str(p["end"]))
        check("the wrong continuation goes with it",
              "orang taun" in p["evidence"]["firstTake"], p["evidence"]["firstTake"])
        check("the kept take is named",
              p["evidence"]["keptTake"].startswith("Sesuatu"), p["evidence"]["keptTake"])
        check("the reason says it may be deliberate", "deliberate" in p["reason"].lower())

    print("\nWhat it must NOT flag")
    different = transcript(
        seg(0, 3, "Kalimat itu bukan sesuatu yang baru"),
        seg(3, 7, "Ribuan tahun yang lalu anak-anaknya Nabi Yaakob"),
        seg(7, 10, "Bahkan dengan versi jauh lebih kasar"),
    )
    check("ordinary consecutive speech is left alone",
          _retake_proposals(different, [], profile) == [])

    far_apart = transcript(
        seg(0, 3, "Sesuatu yang kita pikul sendiri"),
        seg(300, 303, "Sesuatu yang kita pikul sendiri"),
    )
    check("a line echoed much later is not a retake",
          _retake_proposals(far_apart, [], profile) == [])

    short = transcript(seg(0, 1, "Iya"), seg(2, 3, "Iya"))
    check("two short words are not a retake", _retake_proposals(short, [], profile) == [])

    protected = _retake_proposals(
        real, [{"id": "prot-1", "start": 100.0, "end": 130.0}], profile
    )
    check("nothing is proposed inside protected speech", protected == [])

    check("an empty transcript is harmless", _retake_proposals(transcript(), [], profile) == [])
    off = dict(profile)
    off["retakes"] = {"enabled": False}
    check("it can be switched off", _retake_proposals(real, [], off) == [])

    print("\nLooking away from the lens")
    # Resting posture, then a clear turn away, then back.
    steady = [sample(i * 0.2) for i in range(40)]
    looking = list(steady)
    for i in range(15, 25):
        looking[i] = sample(i * 0.2, yaw=-0.45)
    spans = attention_spans(looking, min_seconds=0.4, threshold=1.6)
    check("a sustained turn away is found", len(spans) == 1, f"got {len(spans)}")
    if spans:
        a = spans[0]
        check("it starts around the turn", 2.5 < a["start"] < 3.6, str(a["start"]))
        check("it ends around the return", 4.4 < a["end"] < 5.6, str(a["end"]))
        check("it carries a duration", a["durationSeconds"] > 0.4)
        check("it reports a peak strength", a["peak"] > 1.6)
        check("it says it cannot know why", "glance" in a["note"].lower())

    check("a steady gaze produces nothing", attention_spans(steady) == [])
    blink = list(steady)
    blink[20] = sample(4.0, yaw=-0.5)
    check("a single-sample flick is too short to report",
          attention_spans(blink, min_seconds=0.6) == [])
    check("too few samples is handled", attention_spans([sample(0)]) == [])

    # A head that is always off-centre is this presenter's normal, not a glance.
    tilted = [sample(i * 0.2, yaw=-0.5) for i in range(40)]
    check("a consistently off-axis posture is the baseline, not a finding",
          attention_spans(tilted) == [])

    print(f"\n{_checks - len(_failures)}/{_checks} checks passed")
    if _failures:
        print("\nFailed:")
        for failure in _failures:
            print(f"  - {failure}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
