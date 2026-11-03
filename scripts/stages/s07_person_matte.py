"""Stage 7 — person matte.

Produces cache/matte.mp4 and data/07-person-matte.json.

The matte video is GREYSCALE: its luma IS the alpha. It does not carry the
presenter's colour, on purpose. A transparent video would mean re-encoding the
presenter's pixels a second time and storing them twice, while the source
already holds them at full quality. One pass should record one thing — where
the presenter is — and let the renderer composite the source through it.

Frames are matted strictly in order. RVM is recurrent: each frame's result
feeds the next, which is what stops the edge crawling. Processing out of
order, or reusing a session across clips, would quietly degrade the result.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..lib import matte as matte_lib
from ..lib import media
from ..lib.config import get
from ..lib.jsonio import read_json, rounded, utc_now, write_json
from ..lib.paths import ProjectPaths

SCHEMA = "tadabbur-motion/person-matte@1"


def _encoder_args(settings: dict) -> list[str]:
    """H.264, full range, high quality.

    Full range matters more here than it would for pictures. A matte squeezed
    into the broadcast 16-235 range comes back with solid alpha at about 0.92
    and empty alpha at about 0.06, so the presenter renders slightly
    transparent and the background slightly visible. The round-trip test in
    tests/test_matte.py is what keeps this honest.
    """
    return [
        "-c:v", "libx264",
        "-preset", str(settings.get("preset", "medium")),
        "-crf", str(settings.get("crf", 14)),
        "-pix_fmt", "yuv420p",
        "-color_range", "pc",
        "-movflags", "+faststart",
    ]


def _warnings(summary: matte_lib.MatteSummary, min_mean: float) -> list[str]:
    notes: list[str] = []

    if summary.frames == 0:
        notes.append("No frames were matted.")
        return notes

    if summary.meanCoverage < min_mean:
        notes.append(
            f"The presenter fills only {summary.meanCoverage * 100:.1f}% of the frame on "
            f"average (threshold {min_mean * 100:.0f}%). Either the shot is very wide, or "
            "the matte is failing — compare a frame against the source before using it."
        )

    if summary.gaps:
        longest = max(g["endSeconds"] - g["startSeconds"] for g in summary.gaps)
        notes.append(
            f"{len(summary.gaps)} stretch(es) with no presenter found, longest "
            f"{longest:.2f}s. A Behind layer is not behind anything there, so any effect "
            "that relies on the body hiding it will instead draw across the shot."
        )

    if summary.maxCoverage > 0.9:
        notes.append(
            f"At its largest the matte covers {summary.maxCoverage * 100:.1f}% of the "
            "frame, which usually means the background was matted in as well."
        )

    return notes


def run(config: dict, paths: ProjectPaths) -> dict[str, Any]:
    """Matte the presenter out of every frame and write the artefact."""
    metadata = read_json(paths.metadata)
    source = Path(metadata["source"]["path"])
    video = metadata.get("video") or {}

    width = video.get("width")
    height = video.get("height")
    if not width or not height:
        raise matte_lib.MatteError(
            "01-metadata.json records no video size, so there is nothing to matte."
        )

    settings = get(config, "analysis.personMatte", {})
    fps = float(get(config, "output.portrait.fps", 30))
    matte_w, matte_h = matte_lib.matte_size(
        int(width), int(height), int(settings.get("longEdge", 1280))
    )

    # Fails early and clearly if the model is missing, before any decoding.
    model = matte_lib.model_path(config)
    matter = matte_lib.Matter(config, width=matte_w, height=matte_h)

    paths.ensure()
    coverages: list[float] = []

    with media.frame_encoder(
        config,
        paths.matte_video,
        fps=fps,
        width=matte_w,
        height=matte_h,
        pix_fmt="gray",
        output_args=_encoder_args(settings),
    ) as write:
        for raw in media.sample_frames(
            config, source, fps=fps, width=matte_w, height=matte_h
        ):
            alpha = matter.alpha(raw)
            coverages.append(matte_lib.coverage(alpha))
            write(matte_lib.alpha_to_bytes(alpha))

    summary = matte_lib.summarise(
        coverages,
        fps=fps,
        empty_below=float(settings.get("emptyCoverageBelow", 0.02)),
    )
    warnings = _warnings(summary, float(settings.get("minMeanCoverage", 0.1)))

    payload = {
        "schema": SCHEMA,
        "generatedAt": utc_now(),
        "matter": {
            "name": "RobustVideoMatting (rvm_mobilenetv3)",
            "model": str(model),
            "licence": "GPL-3.0 — see NOTICE",
            "downsampleRatio": matter.downsample,
        },
        "ok": summary.frames > 0 and summary.meanCoverage >= float(
            settings.get("minMeanCoverage", 0.1)
        ),
        # The matte is a video, not numbers: a per-frame alpha plane will not
        # fit in JSON. This artefact describes it and judges it.
        "matteVideo": str(paths.matte_video),
        "encoding": "greyscale H.264, full range; luma is the alpha",
        "fps": fps,
        "frames": summary.frames,
        "width": matte_w,
        "height": matte_h,
        "sourceWidth": int(width),
        "sourceHeight": int(height),
        "stats": {
            "meanCoverage": rounded(summary.meanCoverage, 4),
            "minCoverage": rounded(summary.minCoverage, 4),
            "maxCoverage": rounded(summary.maxCoverage, 4),
            "emptyFrameCount": len(summary.emptyFrames),
            "gapCount": len(summary.gaps),
        },
        "warnings": warnings,
        "gaps": [
            {
                "startFrame": g["startFrame"],
                "endFrame": g["endFrame"],
                "startSeconds": rounded(g["startSeconds"]),
                "endSeconds": rounded(g["endSeconds"]),
            }
            for g in summary.gaps
        ],
    }

    write_json(paths.person_matte, payload)
    return payload
