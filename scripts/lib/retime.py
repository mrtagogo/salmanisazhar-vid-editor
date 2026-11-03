"""Moving timings from the uncut recording onto the cut.

The transcript, the EDL and every region in them describe the ORIGINAL
recording. The rough cut is shorter and has holes where speech was removed, so
a word at 55.36s in the transcript is somewhere else entirely in the cut — and
a word inside a removed span is nowhere at all.

Getting this wrong does not crash anything. It puts subtitles on the wrong
words, which is the kind of fault that survives all the way to publishing.
"""

from __future__ import annotations

from typing import Any

# Keep-ranges are floats from JSON; comparisons need a little slack.
EPSILON = 1e-6


def to_cut(keep_ranges: list[dict], t: float) -> float | None:
    """Where source time `t` lands in the cut, or None if it was removed."""
    elapsed = 0.0
    for keep in keep_ranges:
        start, end = float(keep["start"]), float(keep["end"])
        if start - EPSILON <= t < end:
            return elapsed + (t - start)
        elapsed += end - start
    return None


def to_source(keep_ranges: list[dict], t: float) -> float | None:
    """The reverse: where cut time `t` came from in the recording."""
    elapsed = 0.0
    for keep in keep_ranges:
        start, end = float(keep["start"]), float(keep["end"])
        length = end - start
        if elapsed - EPSILON <= t < elapsed + length:
            return start + (t - elapsed)
        elapsed += length
    return None


def clamp_to_cut(keep_ranges: list[dict], start: float, end: float) -> tuple[float, float] | None:
    """A span's position in the cut, trimmed to whatever survived.

    A span straddling a removal comes back as the part that is still there.
    One removed entirely comes back as None — the caller must drop it rather
    than show it at a guessed time.
    """
    best: tuple[float, float] | None = None
    elapsed = 0.0
    for keep in keep_ranges:
        k0, k1 = float(keep["start"]), float(keep["end"])
        lo, hi = max(start, k0), min(end, k1)
        if hi - lo > EPSILON:
            piece = (elapsed + (lo - k0), elapsed + (hi - k0))
            # Keep the longest surviving piece: a caption should follow the
            # bulk of what was said, not a fragment at its edge.
            if best is None or (piece[1] - piece[0]) > (best[1] - best[0]):
                best = piece
        elapsed += k1 - k0
    return best


def retime_words(words: list[dict], keep_ranges: list[dict]) -> list[dict]:
    """Words that survived the cut, with their new timings."""
    out: list[dict] = []
    for word in words:
        span = clamp_to_cut(keep_ranges, float(word["start"]), float(word["end"]))
        if span is None:
            continue
        out.append({**word, "start": round(span[0], 4), "end": round(span[1], 4)})
    return out


def retime_regions(regions: list[dict], keep_ranges: list[dict]) -> list[dict[str, Any]]:
    """Protected or suspected spans, moved onto the cut."""
    out: list[dict[str, Any]] = []
    for region in regions:
        span = clamp_to_cut(keep_ranges, float(region["start"]), float(region["end"]))
        if span is None:
            continue
        out.append({**region, "start": round(span[0], 4), "end": round(span[1], 4)})
    return out


__all__ = ["clamp_to_cut", "retime_regions", "retime_words", "to_cut", "to_source"]
