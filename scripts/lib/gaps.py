"""Finding sound inside the holes in a transcript.

A gap between transcribed words is supposed to be a gap in the talking. When
the microphone says otherwise, something was said there and never written
down — and every rule downstream reads that hole as a pause.
"""

from __future__ import annotations

from typing import Any


def longest_unsilent(
    start: float, end: float, silence_spans: list[dict]
) -> tuple[float, float]:
    """The longest continuous stretch inside a span that is NOT quiet."""
    quiet = sorted(
        (max(start, float(s["start"])), min(end, float(s["end"])))
        for s in silence_spans
        if float(s["end"]) > start and float(s["start"]) < end
    )
    best = (start, start)
    cursor = start
    for low, high in quiet:
        if low - cursor > best[1] - best[0]:
            best = (cursor, low)
        cursor = max(cursor, high)
    if end - cursor > best[1] - best[0]:
        best = (cursor, end)
    return best


def unheard_spans(
    words: list[dict], silence_spans: list[dict], min_seconds: float
) -> list[dict[str, Any]]:
    """Word-gaps holding a long stretch of sound."""
    out: list[dict[str, Any]] = []
    for index in range(len(words) - 1):
        start = float(words[index]["end"])
        end = float(words[index + 1]["start"])
        if end - start <= min_seconds:
            continue
        low, high = longest_unsilent(start, end, silence_spans)
        if high - low < min_seconds:
            continue
        out.append({"start": low, "end": high, "gapStart": start, "gapEnd": end})
    return out


__all__ = ["longest_unsilent", "unheard_spans"]
