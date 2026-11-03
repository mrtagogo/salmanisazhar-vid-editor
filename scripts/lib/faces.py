"""Face tracking: detection, then the arithmetic that turns detections into a
per-frame track.

The two halves are kept apart on purpose. Everything below `build_track` is
pure arithmetic over plain numbers — no OpenCV, no model, no video — so the
part most likely to hold a bug can be tested exactly rather than approximately.
Detection itself is a thin adapter around one model.

What a track is for: framing a punch-in, and keeping captions and graphics off
the presenter's face. Both are editorial promises, so a track the engine is not
confident about must say so rather than quietly supplying plausible numbers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import ENGINE_ROOT, get
from .media import MediaToolError, sample_frames


class FaceTrackError(RuntimeError):
    """Raised when the detector cannot run at all."""


# The detector returns a face box, which runs roughly from the brow to the
# chin. The top of the HEAD — hair, and whatever is worn on it — is above that
# and is never detected. This is how far above the box centre the crown is
# assumed to be, in units of face width. It is an ESTIMATE, deliberately
# generous, and it is the number to revisit first when real footage arrives:
# a presenter in a peci or songkok has a taller head than this assumes.
DEFAULT_HEAD_TOP_ABOVE_CENTRE = 0.75


@dataclass(frozen=True)
class FaceSample:
    """One detection, in source pixels."""

    time: float
    cx: float
    cy: float
    w: float
    score: float


# --------------------------------------------------------------------------
# detection
# --------------------------------------------------------------------------


def model_path(config: dict) -> Path:
    """Resolve the configured model file, or say precisely what is missing."""
    configured = get(config, "analysis.faceTrack.model", "")
    if not configured:
        raise FaceTrackError(
            "analysis.faceTrack.model is not set in engine.config.json."
        )

    path = Path(configured)
    if not path.is_absolute():
        path = ENGINE_ROOT / path

    if not path.is_file():
        raise FaceTrackError(
            f"Face detection model not found: {path}\n"
            "It is not committed to this repository (it is a third-party binary).\n"
            "See models/README.md for the download and its checksum."
        )
    return path


def detect(config: dict, source: Path, *, width: int, height: int) -> list[FaceSample]:
    """Run the detector over the video and return one sample per examined frame.

    Frames with no face produce no sample; the gaps are handled by build_track.
    """
    try:
        import cv2
    except ImportError as exc:  # pragma: no cover - environment problem
        raise FaceTrackError(
            "OpenCV is not installed. Install it with:\n"
            "  python -m pip install opencv-python"
        ) from exc

    settings = get(config, "analysis.faceTrack", {})
    sample_fps = float(settings.get("sampleFps", 10))
    detect_width = int(settings.get("detectWidth", 640))
    score_threshold = float(settings.get("scoreThreshold", 0.6))
    nms_threshold = float(settings.get("nmsThreshold", 0.3))
    top_k = int(settings.get("topK", 50))

    if width <= 0 or height <= 0:
        raise FaceTrackError(f"Source has no usable video size ({width}x{height}).")

    # Detect on a smaller frame: YuNet is trained around this scale, it is much
    # faster, and the result is scaled back to source pixels anyway.
    detect_width = min(detect_width, width)
    detect_height = max(2, int(round(detect_width * height / width)) // 2 * 2)
    scale_back = width / detect_width

    import numpy as np

    detector = cv2.FaceDetectorYN.create(
        str(model_path(config)),
        "",
        (detect_width, detect_height),
        score_threshold,
        nms_threshold,
        top_k,
    )

    samples: list[FaceSample] = []
    for index, raw in enumerate(
        sample_frames(config, source, fps=sample_fps, width=detect_width, height=detect_height)
    ):
        frame = np.frombuffer(raw, dtype=np.uint8).reshape(detect_height, detect_width, 3)
        _, faces = detector.detect(frame)
        if faces is None or len(faces) == 0:
            continue

        # One presenter: the largest box wins. A second face in shot is far
        # more likely to be a poster or a reflection than a co-host, and
        # switching between them mid-sentence would swing the camera.
        best = max(faces, key=lambda f: float(f[2]) * float(f[3]))
        x, y, w, h = (float(best[0]), float(best[1]), float(best[2]), float(best[3]))
        samples.append(
            FaceSample(
                time=index / sample_fps,
                cx=(x + w / 2) * scale_back,
                cy=(y + h / 2) * scale_back,
                w=w * scale_back,
                score=float(best[14]) if len(best) > 14 else 1.0,
            )
        )

    return samples


# --------------------------------------------------------------------------
# pure arithmetic
# --------------------------------------------------------------------------


def median3(values: list[float]) -> list[float]:
    """Median of every three neighbouring values; ends are left alone.

    A detector occasionally returns one badly wrong box. Averaging drags that
    error into its neighbours; a median discards it outright.
    """
    if len(values) < 3:
        return list(values)
    out = list(values)
    for i in range(1, len(values) - 1):
        out[i] = sorted(values[i - 1 : i + 2])[1]
    return out


def ema(values: list[float], alpha: float) -> list[float]:
    """Exponential moving average, one pass."""
    if not values:
        return []
    out: list[float] = []
    acc = values[0]
    for v in values:
        acc = alpha * v + (1 - alpha) * acc
        out.append(acc)
    return out


def smooth(values: list[float], alpha: float) -> list[float]:
    """Zero-phase smoothing: one pass forward, one back.

    A single pass lags, and a camera that lags behind the head is visibly
    wrong — it looks like the operator is reacting late. Running the filter
    backwards over its own output cancels the delay.
    """
    if not values or alpha >= 1:
        return list(values)
    forward = ema(values, alpha)
    return list(reversed(ema(list(reversed(forward)), alpha)))


def alpha_for(seconds: float, fps: float) -> float:
    """Smoothing strength for a given time constant."""
    if seconds <= 0 or fps <= 0:
        return 1.0
    return 1.0 - math.exp(-(1.0 / fps) / seconds)


def _interpolate(samples: list[FaceSample], t: float) -> tuple[float, float, float, float]:
    """Face at time t, linearly between the two nearest samples.

    Returns (cx, cy, w, distance_to_nearest_sample_in_seconds).
    """
    first, last = samples[0], samples[-1]
    if t <= first.time:
        return first.cx, first.cy, first.w, first.time - t
    if t >= last.time:
        return last.cx, last.cy, last.w, t - last.time

    lo, hi = 0, len(samples) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if samples[mid].time <= t:
            lo = mid
        else:
            hi = mid

    a, b = samples[lo], samples[hi]
    span = b.time - a.time
    k = 0.0 if span <= 0 else (t - a.time) / span
    gap = min(t - a.time, b.time - t)
    return (
        a.cx + (b.cx - a.cx) * k,
        a.cy + (b.cy - a.cy) * k,
        a.w + (b.w - a.w) * k,
        gap,
    )


def build_track(
    samples: list[FaceSample],
    *,
    frames: int,
    fps: float,
    width: int,
    height: int,
    smoothing_seconds: float = 0.25,
    max_gap_seconds: float = 0.5,
    head_top_above_centre: float = DEFAULT_HEAD_TOP_ABOVE_CENTRE,
) -> dict[str, Any]:
    """Turn detections into the per-frame track the composition layer reads.

    Coordinates come out normalised — x and w by width, y and top by height —
    so the track survives a change of output resolution. Frames where no face
    was found near enough in time are still filled, by holding the nearest
    known position, but every one of them is recorded in `gaps`. A gap is not a
    neutral fact: inside one, the engine does not know where the face is, so
    nothing may claim to be keeping clear of it.
    """
    if frames <= 0 or fps <= 0:
        raise ValueError(f"frames and fps must be positive (got {frames}, {fps})")
    if width <= 0 or height <= 0:
        raise ValueError(f"width and height must be positive (got {width}, {height})")

    ordered = sorted(samples, key=lambda s: s.time)
    if not ordered:
        return {
            "ok": False,
            "reason": "no face was detected anywhere in the video",
            "frames": frames,
            "fps": fps,
            "width": width,
            "height": height,
            "face": [],
            "top": [],
            "gaps": [],
            "stats": {"sampleCount": 0, "coverage": 0.0, "meanScore": None},
        }

    # Kill single-frame outliers before anything interpolates through them.
    cleaned_cx = median3([s.cx for s in ordered])
    cleaned_cy = median3([s.cy for s in ordered])
    cleaned_w = median3([s.w for s in ordered])
    cleaned = [
        FaceSample(time=s.time, cx=cx, cy=cy, w=w, score=s.score)
        for s, cx, cy, w in zip(ordered, cleaned_cx, cleaned_cy, cleaned_w)
    ]

    xs: list[float] = []
    ys: list[float] = []
    ws: list[float] = []
    gap_frames: list[bool] = []

    for f in range(frames):
        cx, cy, w, gap = _interpolate(cleaned, f / fps)
        xs.append(cx)
        ys.append(cy)
        ws.append(w)
        gap_frames.append(gap > max_gap_seconds)

    alpha = alpha_for(smoothing_seconds, fps)
    xs = smooth(xs, alpha)
    ys = smooth(ys, alpha)
    ws = smooth(ws, alpha)

    face = [[x / width, y / height, w / width] for x, y, w in zip(xs, ys, ws)]
    top = [(y - head_top_above_centre * w) / height for y, w in zip(ys, ws)]

    gaps: list[dict[str, Any]] = []
    start: int | None = None
    for f, missing in enumerate(gap_frames):
        if missing and start is None:
            start = f
        elif not missing and start is not None:
            gaps.append({"startFrame": start, "endFrame": f - 1})
            start = None
    if start is not None:
        gaps.append({"startFrame": start, "endFrame": frames - 1})

    covered = sum(1 for m in gap_frames if not m)
    return {
        "ok": True,
        "reason": None,
        "frames": frames,
        "fps": fps,
        "width": width,
        "height": height,
        "face": face,
        "top": top,
        "gaps": [
            {
                **g,
                "startSeconds": g["startFrame"] / fps,
                "endSeconds": (g["endFrame"] + 1) / fps,
            }
            for g in gaps
        ],
        "stats": {
            "sampleCount": len(ordered),
            "coverage": covered / frames,
            "meanScore": sum(s.score for s in ordered) / len(ordered),
        },
    }


__all__ = [
    "DEFAULT_HEAD_TOP_ABOVE_CENTRE",
    "FaceSample",
    "FaceTrackError",
    "MediaToolError",
    "alpha_for",
    "build_track",
    "detect",
    "ema",
    "median3",
    "model_path",
    "smooth",
]
