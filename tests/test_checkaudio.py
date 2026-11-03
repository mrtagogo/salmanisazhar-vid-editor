"""The thirty-second check on a recording.

Run from the engine root:

    python -m tests.test_checkaudio

Transcription is the expensive stage and everything downstream trusts it.
The first real recording made the cost concrete: the camera's own microphone
dropped a whole Qur'anic recitation, which then could not be protected
because nothing knew it was there.

The verdict is calibrated against two recordings of the SAME talk where the
outcome is known — 22 dB separation lost the recitation, 45 dB kept it — so
these checks use those two numbers as the fixed points.
"""

from __future__ import annotations

import sys

from scripts.checkaudio import (
    FAIR_SEPARATION,
    POOR_SEPARATION,
    verdict,
)

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


def measured(separation: float, peak: float = -12.0, clipped: float = 0.0) -> dict:
    return {
        "durationSeconds": 150.0,
        "noiseFloorDb": -60.0,
        "speechLevelDb": -60.0 + separation,
        "separationDb": separation,
        "peakDb": peak,
        "clippedFraction": clipped,
    }


def main() -> int:
    print("The two real recordings")
    camera, camera_notes = verdict(measured(21.7))
    check("the camera microphone is called POOR", camera == "POOR", camera)
    check("it says words will be dropped",
          any("drop words" in n for n in camera_notes), str(camera_notes))
    check("it says what to do about it",
          any("closer" in n for n in camera_notes))

    recorder, _ = verdict(measured(44.8))
    check("the separate recorder is called GOOD", recorder == "GOOD", recorder)

    print("\nThe thresholds sit between them")
    check("below the poor line is POOR", verdict(measured(POOR_SEPARATION - 1))[0] == "POOR")
    check("between the lines is FAIR",
          verdict(measured((POOR_SEPARATION + FAIR_SEPARATION) / 2))[0] == "FAIR")
    check("above the fair line is GOOD", verdict(measured(FAIR_SEPARATION + 1))[0] == "GOOD")
    check("the thresholds bracket both real recordings",
          21.7 < POOR_SEPARATION and FAIR_SEPARATION < 44.8,
          f"poor={POOR_SEPARATION} fair={FAIR_SEPARATION}")

    print("\nLevel faults")
    clipping, clip_notes = verdict(measured(45.0, peak=-0.2, clipped=0.02))
    check("clipping makes an otherwise good take POOR", clipping == "POOR", clipping)
    check("it says the damage cannot be undone",
          any("permanent" in n for n in clip_notes), str(clip_notes))

    hot, hot_notes = verdict(measured(45.0, peak=-1.0))
    check("a hot peak is a warning, not a failure", hot == "GOOD", hot)
    check("the hot peak is mentioned", any("ceiling" in n for n in hot_notes))

    quiet, quiet_notes = verdict(measured(45.0, peak=-30.0))
    check("a quiet recording is not called a fault", quiet == "GOOD", quiet)
    check("but the level is mentioned",
          any("input level" in n for n in quiet_notes), str(quiet_notes))

    check("a healthy take collects no complaints",
          len(verdict(measured(45.0, peak=-12.0))[1]) == 1)

    print(f"\n{_checks - len(_failures)}/{_checks} checks passed")
    if _failures:
        print("\nFailed:")
        for failure in _failures:
            print(f"  - {failure}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
