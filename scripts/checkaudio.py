"""A thirty-second check on a recording, before spending anything on it.

    python -m scripts.checkaudio --input "input/kajian-02.mp4"

Transcription is the expensive stage and everything downstream trusts it. If
the sound is poor the transcript loses words, and losing words is not a
cosmetic fault here: on the first real recording the camera's own microphone
dropped an entire Qur'anic recitation, which then could not be protected
because nothing knew it was there.

So this measures the one thing that predicted that failure, and says plainly
whether the take is worth transcribing.

Calibrated against two recordings of the SAME talk, where the outcome is
known:

    camera microphone   22 dB separation  -> the recitation was lost
    separate recorder   45 dB separation  -> the recitation was transcribed

The thresholds below sit between those two measurements. They are a rule of
thumb drawn from one pair of recordings, not a law.
"""

from __future__ import annotations

import argparse
import wave
from pathlib import Path
from typing import Any

from .lib import media
from .lib.config import ENGINE_ROOT, load_config

# Speech level minus noise floor. Below POOR, expect dropped words.
POOR_SEPARATION = 25.0
FAIR_SEPARATION = 35.0

# Peak level. Too low wastes resolution; too near zero risks clipping.
QUIET_PEAK = -24.0
HOT_PEAK = -2.0
CLIPPING_FRACTION = 0.0005


def measure(config: dict, source: Path, work: Path) -> dict[str, Any]:
    import numpy as np

    work.mkdir(parents=True, exist_ok=True)
    wav = work / "check-16k-mono.wav"
    media.extract_audio(config, source, wav)

    with wave.open(str(wav)) as handle:
        rate = handle.getframerate()
        raw = handle.readframes(handle.getnframes())
    samples = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    if samples.size == 0:
        raise SystemExit(f"No audio in {source}")

    # 20 ms frames: short enough to sit inside a syllable, long enough to be
    # a stable level.
    size = int(0.02 * rate)
    frames = samples[: len(samples) // size * size].reshape(-1, size)
    db = 20 * np.log10(np.maximum(np.sqrt((frames**2).mean(axis=1)), 1e-9))

    floor = float(np.percentile(db, 10))
    speech = float(np.percentile(db, 90))
    peak = float(20 * np.log10(max(float(np.abs(samples).max()), 1e-9)))
    clipped = float(np.mean(np.abs(samples) > 0.985))

    return {
        "durationSeconds": len(samples) / rate,
        "noiseFloorDb": floor,
        "speechLevelDb": speech,
        "separationDb": speech - floor,
        "peakDb": peak,
        "clippedFraction": clipped,
    }


def verdict(m: dict[str, Any]) -> tuple[str, list[str]]:
    notes: list[str] = []
    separation = m["separationDb"]

    if separation < POOR_SEPARATION:
        state = "POOR"
        notes.append(
            f"Speech stands only {separation:.0f} dB above the room. The transcriber "
            "will drop words, and anything it drops cannot be protected or subtitled. "
            "Move the microphone closer before re-recording."
        )
    elif separation < FAIR_SEPARATION:
        state = "FAIR"
        notes.append(
            f"Speech stands {separation:.0f} dB above the room. Usable, but quiet "
            "passages and recitation are where words get lost. Closer is better."
        )
    else:
        state = "GOOD"
        notes.append(f"Speech stands {separation:.0f} dB above the room.")

    if m["clippedFraction"] > CLIPPING_FRACTION:
        state = "POOR"
        notes.append(
            f"{m['clippedFraction'] * 100:.2f}% of samples are clipped. That damage is "
            "permanent — lower the input level and record again."
        )
    elif m["peakDb"] > HOT_PEAK:
        notes.append(
            f"Peaks reach {m['peakDb']:.1f} dB, close to the ceiling. A loud moment "
            "could clip."
        )
    elif m["peakDb"] < QUIET_PEAK:
        notes.append(
            f"Peaks only reach {m['peakDb']:.1f} dB. Not a fault, but raising the "
            "input level gives the transcriber more to work with."
        )

    return state, notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="checkaudio")
    parser.add_argument("--input", required=True, help="The recording to check.")
    args = parser.parse_args(argv)

    source = Path(args.input)
    if not source.is_absolute():
        source = (ENGINE_ROOT / source).resolve()
    if not source.is_file():
        raise SystemExit(f"Not found: {source}")

    config = load_config()
    measured = measure(config, source, ENGINE_ROOT / "projects" / "_checkaudio")
    state, notes = verdict(measured)

    print(f"{source.name}  ({measured['durationSeconds'] / 60:.1f} min)")
    print()
    print(f"  noise floor   {measured['noiseFloorDb']:7.1f} dB")
    print(f"  speech level  {measured['speechLevelDb']:7.1f} dB")
    print(f"  separation    {measured['separationDb']:7.1f} dB")
    print(f"  peak          {measured['peakDb']:7.1f} dB")
    print()
    print(f"  {state}")
    for note in notes:
        print(f"    - {note}")
    print()
    print(
        "  For reference, on two recordings of the same talk: the camera microphone "
        "managed 22 dB and lost a recitation entirely; a recorder closer to the "
        "speaker managed 45 dB and kept it."
    )
    return 0 if state != "POOR" else 1


if __name__ == "__main__":
    raise SystemExit(main())
