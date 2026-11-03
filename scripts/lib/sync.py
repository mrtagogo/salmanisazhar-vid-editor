"""Lining up a separately recorded soundtrack with the picture.

Dual-system sound is ordinary practice: the camera records a usable guide
track, and a phone or recorder closer to the speaker records the sound you
actually keep. The two start at different moments, so they have to be lined
up before anything downstream can treat them as one timeline.

Matching is done on the ENVELOPE — the shape of loud and quiet — not on the
waveform. Two microphones in different places, through different codecs,
never agree sample for sample, but they agree completely about when someone
is talking.

Nothing here edits audio. It measures, and reports how much to trust the
measurement, because a wrong offset is worse than none: it desynchronises
every word while looking like a working pipeline.
"""

from __future__ import annotations

import math
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .media import extract_audio

# Envelope resolution. 5 ms is well under one frame at 30 fps, so the
# measurement is finer than the thing it is used to correct.
HOP_SECONDS = 0.005

# A correlation below this means the two recordings are not the same take.
MIN_CORRELATION = 0.5
# ...and the best match must beat the next-best alignment by this much,
# otherwise the peak is noise rather than a match.
MIN_SHARPNESS = 1.6
# Offsets measured in different windows may disagree by at most this much.
# One frame at 30 fps is 33 ms; half of that is comfortably invisible.
MAX_SPREAD_SECONDS = 0.016
# Total clock drift that may accumulate across the whole recording.
MAX_DRIFT_SECONDS = 0.033


@dataclass(frozen=True)
class Alignment:
    """How a separate recording lines up with the picture."""

    offsetSeconds: float
    correlation: float
    sharpness: float
    spreadSeconds: float
    driftSeconds: float
    windows: list[dict[str, float]]
    confident: bool
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "offsetSeconds": round(self.offsetSeconds, 4),
            "correlation": round(self.correlation, 4),
            "sharpness": round(self.sharpness, 3),
            "spreadSeconds": round(self.spreadSeconds, 4),
            "driftSeconds": round(self.driftSeconds, 4),
            "confident": self.confident,
            "reason": self.reason,
            "windows": self.windows,
        }


def _read_wav(path: Path):
    import numpy as np

    with wave.open(str(path)) as handle:
        rate = handle.getframerate()
        raw = handle.readframes(handle.getnframes())
    return np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0, rate


def envelope(samples, rate: int, hop: float = HOP_SECONDS):
    """Log loudness per hop. Normalised, so level differences do not matter."""
    import numpy as np

    size = max(1, int(hop * rate))
    usable = len(samples) // size * size
    frames = samples[:usable].reshape(-1, size)
    energy = np.log10(np.sqrt((frames**2).mean(axis=1)) + 1e-6)
    return energy


def _normalise(values):
    import numpy as np

    values = np.asarray(values, dtype=np.float64)
    return (values - values.mean()) / (values.std() + 1e-9)


def _coarse_offset(reference, other, hop: float) -> tuple[float, float, float]:
    """Best whole-file offset, its correlation, and how sharp the peak is."""
    import numpy as np

    a, b = _normalise(reference), _normalise(other)
    size = 1 << int(math.ceil(math.log2(len(a) + len(b))))
    spectrum = np.fft.rfft(a, size) * np.conj(np.fft.rfft(b, size))
    corr = np.fft.irfft(spectrum, size)
    corr = np.concatenate([corr[-(len(b) - 1) :], corr[: len(a)]]) / math.sqrt(len(a) * len(b))
    lags = (np.arange(-(len(b) - 1), len(a))) * hop

    best = int(np.argmax(corr))
    peak = float(corr[best])
    offset = float(lags[best])

    # The runner-up has to be far away, or the peak means nothing.
    far = np.abs(lags - offset) > 2.0
    runner_up = float(corr[far].max()) if far.any() else 0.0
    sharpness = peak / max(runner_up, 1e-9)
    return offset, peak, sharpness


def _window_offsets(reference, other, hop: float, around: float, windows: int = 8):
    """Measure the offset separately across the recording, to expose drift."""
    import numpy as np

    span = int(15 / hop)
    search = int(3.0 / hop)
    usable = len(reference) - span
    if usable <= 0:
        return []

    results: list[dict[str, float]] = []
    for index in range(windows):
        start = int(usable * index / max(1, windows - 1)) if windows > 1 else 0
        segment = _normalise(reference[start : start + span])
        centre = start + int(around / hop)
        lo, hi = max(0, centre - search), min(len(other), centre + span + search)
        reference_slice = other[lo:hi]
        if len(reference_slice) < len(segment):
            continue
        scores = np.correlate(_normalise(reference_slice), segment, mode="valid") / len(segment)
        peak = int(np.argmax(scores))
        results.append(
            {
                "atSeconds": round(start * hop, 3),
                "offsetSeconds": round((lo + peak - start) * hop, 4),
                "correlation": round(float(scores[peak]), 4),
            }
        )
    return results


def measure(config: dict, picture: Path, sound: Path, cache: Path) -> Alignment:
    """Measure how `sound` lines up with the audio inside `picture`."""
    import numpy as np

    cache.mkdir(parents=True, exist_ok=True)
    picture_wav = cache / "sync-picture.wav"
    sound_wav = cache / "sync-sound.wav"
    if not picture_wav.exists():
        extract_audio(config, picture, picture_wav)
    if not sound_wav.exists():
        extract_audio(config, sound, sound_wav)

    a, rate = _read_wav(picture_wav)
    b, _ = _read_wav(sound_wav)
    ea, eb = envelope(a, rate), envelope(b, rate)

    offset, correlation, sharpness = _coarse_offset(ea, eb, HOP_SECONDS)
    windows = _window_offsets(ea, eb, HOP_SECONDS, offset)

    if windows:
        measured = np.array([w["offsetSeconds"] for w in windows])
        times = np.array([w["atSeconds"] for w in windows])
        spread = float(measured.max() - measured.min())
        slope = float(np.polyfit(times, measured, 1)[0]) if len(windows) > 1 else 0.0
        drift = slope * (len(ea) * HOP_SECONDS)
        offset = float(np.median(measured))
    else:
        spread, drift = 0.0, 0.0

    reasons = []
    if correlation < MIN_CORRELATION:
        reasons.append(
            f"the two recordings only match at {correlation:.2f}; they are probably "
            "not the same take"
        )
    if sharpness < MIN_SHARPNESS:
        reasons.append(
            f"the best alignment is only {sharpness:.1f}x better than the next one, "
            "so the match is ambiguous"
        )
    if spread > MAX_SPREAD_SECONDS:
        reasons.append(
            f"the offset varies by {spread * 1000:.0f} ms across the recording, which "
            "is more than half a frame"
        )
    if abs(drift) > MAX_DRIFT_SECONDS:
        reasons.append(
            f"the clocks drift {drift * 1000:+.0f} ms over the recording; one offset "
            "will not hold to the end"
        )

    return Alignment(
        offsetSeconds=offset,
        correlation=correlation,
        sharpness=sharpness,
        spreadSeconds=spread,
        driftSeconds=drift,
        windows=windows,
        confident=not reasons,
        reason="; ".join(reasons) if reasons else "one constant offset lines them up",
    )


__all__ = ["Alignment", "envelope", "measure"]
