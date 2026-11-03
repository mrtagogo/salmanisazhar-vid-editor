"""Lining up a separately recorded soundtrack.

Run from the engine root:

    python -m tests.test_sync

Dual-system sound is ordinary: the camera records a guide track, a recorder
closer to the speaker records what you keep. The engine measures the offset
rather than asking for it, because a number typed by hand is a number nobody
checks.

The danger is not failing to align. It is aligning WRONGLY — a plausible
offset desynchronises every word while the pipeline still looks like it
worked. So most of this file is about the cases where the measurement must be
refused.

The fixtures are built here with known offsets, so every expected number is
arrived at independently of the code under test.
"""

from __future__ import annotations

import math
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

from scripts.lib import sync
from scripts.lib.config import load_config

RATE = 16000

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


def speechlike(seconds: float, seed: int) -> np.ndarray:
    """Noise bursts with pauses: not speech, but the same loud/quiet shape."""
    rng = np.random.default_rng(seed)
    out = np.zeros(int(seconds * RATE), dtype=np.float64)
    t = 0.0
    while t < seconds:
        burst = float(rng.uniform(0.4, 1.6))
        gap = float(rng.uniform(0.2, 0.9))
        a, b = int(t * RATE), int(min(seconds, t + burst) * RATE)
        if b > a:
            out[a:b] = rng.normal(0, 0.25, b - a)
        t += burst + gap
    return np.clip(out, -1, 1)


def write_wav(path: Path, samples: np.ndarray) -> Path:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())
    return path


def main() -> int:
    config = load_config()

    print("Envelope")
    env = sync.envelope(speechlike(4.0, 1), RATE)
    check("one value per hop", abs(len(env) - 4.0 / sync.HOP_SECONDS) <= 1,
          f"got {len(env)}")
    loud = sync.envelope(np.full(RATE, 0.5), RATE)
    quiet = sync.envelope(np.full(RATE, 0.001), RATE)
    check("loud reads higher than quiet", loud.mean() > quiet.mean())
    check("silence does not blow up", np.isfinite(sync.envelope(np.zeros(RATE), RATE)).all())

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)

        print("\nA known offset is recovered")
        # The 'recorder' started 0.75s BEFORE the camera, so the same moment
        # sits 0.75s later in its file.
        OFFSET = 0.75
        base = speechlike(40.0, 7)
        picture = base[int(OFFSET * RATE):]
        # different mic: different level, different room noise
        sound = base * 0.6 + np.random.default_rng(99).normal(0, 0.004, len(base))

        write_wav(work / "picture.wav", picture)
        write_wav(work / "sound.wav", sound)
        result = sync.measure(config, work / "picture.wav", work / "sound.wav", work / "c1")

        check("the offset is found", abs(result.offsetSeconds - OFFSET) < 0.02,
              f"got {result.offsetSeconds:+.3f}s, expected {OFFSET:+.3f}s")
        check("the match is strong", result.correlation > 0.7, f"{result.correlation:.3f}")
        check("the peak is sharp", result.sharpness >= sync.MIN_SHARPNESS,
              f"{result.sharpness:.2f}x")
        check("no drift is reported", abs(result.driftSeconds) < 0.02,
              f"{result.driftSeconds:+.4f}s")
        check("it is accepted", result.confident, result.reason)
        check("the reason is stated even on success", bool(result.reason))
        check("it reports per-window measurements", len(result.windows) >= 4,
              f"{len(result.windows)} window(s)")
        check("the dict form rounds for the artefact",
              isinstance(result.as_dict()["offsetSeconds"], float))

        print("\nA negative offset too")
        # Recorder started AFTER the camera: silence has to be prepended later.
        base2 = speechlike(40.0, 11)
        write_wav(work / "p2.wav", base2)
        write_wav(work / "s2.wav", base2[int(0.5 * RATE):])
        back = sync.measure(config, work / "p2.wav", work / "s2.wav", work / "c2")
        check("a late recorder gives a negative offset", back.offsetSeconds < -0.3,
              f"got {back.offsetSeconds:+.3f}s")

        print("\nDifferent takes are refused")
        write_wav(work / "p3.wav", speechlike(40.0, 21))
        write_wav(work / "s3.wav", speechlike(40.0, 22))   # unrelated
        other = sync.measure(config, work / "p3.wav", work / "s3.wav", work / "c3")
        check("two different recordings are NOT accepted", not other.confident,
              f"corr {other.correlation:.2f}, sharp {other.sharpness:.2f}")
        check("the refusal explains itself", len(other.reason) > 20, other.reason)

        print("\nDrifting clocks are refused")
        # Resample one side slightly: the offset grows across the recording.
        base3 = speechlike(60.0, 31)
        write_wav(work / "p4.wav", base3)
        idx = np.arange(0, len(base3) - 1, 1.0 - 0.0015)
        stretched = np.interp(idx, np.arange(len(base3)), base3)
        write_wav(work / "s4.wav", stretched)
        drifting = sync.measure(config, work / "p4.wav", work / "s4.wav", work / "c4")
        check("a drifting pair is NOT accepted", not drifting.confident,
              f"spread {drifting.spreadSeconds:.3f}s drift {drifting.driftSeconds:+.3f}s")
        check("drift is named in the refusal",
              "drift" in drifting.reason or "varies" in drifting.reason, drifting.reason)

    print(f"\n{_checks - len(_failures)}/{_checks} checks passed")
    if _failures:
        print("\nFailed:")
        for failure in _failures:
            print(f"  - {failure}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
