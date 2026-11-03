"""Stage 3 — acoustic silence detection.

Produces data/03-silence.json. This stage is intentionally free of editorial
judgement: it reports where the audio is quiet and nothing more. Whether a
quiet span is dead air or a deliberate pause is decided in stage 4.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..lib import media
from ..lib.config import get
from ..lib.jsonio import read_json, rounded, utc_now, write_json
from ..lib.paths import ProjectPaths

SCHEMA = "tadabbur-motion/silence@1"


def run(config: dict, paths: ProjectPaths) -> dict[str, Any]:
    """Detect silent spans in the project's audio and write the artefact."""
    metadata = read_json(paths.metadata)
    source = Path(metadata["source"]["path"])
    duration = metadata["container"].get("durationSeconds") or 0.0

    paths.ensure()
    if not paths.audio_wav.exists():
        media.extract_audio(config, source, paths.audio_wav)

    raw_spans = media.detect_silence(config, paths.audio_wav, duration)

    spans: list[dict[str, Any]] = []
    silent_seconds = 0.0

    for index, span in enumerate(raw_spans):
        start = max(0.0, span["start"])
        end = min(duration, span["end"]) if duration else span["end"]
        length = max(0.0, end - start)
        if length <= 0:
            continue

        silent_seconds += length
        spans.append(
            {
                "id": f"sil-{index + 1:04d}",
                "start": rounded(start),
                "end": rounded(end),
                "durationSeconds": rounded(length),
                # Positional facts only — leading/trailing silence is usually
                # head/tail slate, which is a different case from a mid-talk pause.
                "position": (
                    "leading"
                    if start <= 0.05
                    else "trailing"
                    if duration and end >= duration - 0.05
                    else "interior"
                ),
            }
        )

    longest = max((s["durationSeconds"] for s in spans), default=0.0)

    payload = {
        "schema": SCHEMA,
        "generatedAt": utc_now(),
        "detector": {
            "filter": "ffmpeg silencedetect",
            "noiseFloorDb": get(config, "analysis.silence.noiseFloorDb", -32),
            "minSilenceSeconds": get(config, "analysis.silence.minSilenceSeconds", 0.3),
            "audioFile": str(paths.audio_wav),
        },
        "durationSeconds": rounded(duration) if duration else None,
        "stats": {
            "spanCount": len(spans),
            "silentSeconds": rounded(silent_seconds),
            "silentRatio": rounded(silent_seconds / duration, 4) if duration else None,
            "longestSilenceSeconds": rounded(longest),
        },
        "spans": spans,
    }

    write_json(paths.silence, payload)
    return payload
