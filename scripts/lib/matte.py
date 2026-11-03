"""Person matte: separating the presenter from the room.

The matte is what makes a graphic go BEHIND the presenter instead of across
them. Without it, `text-behind` puts a large word over a face, which the
editorial rules forbid outright — so this pass is not a visual nicety, it is
the thing that makes one effect permissible at all.

Model: RobustVideoMatting (RVM). It is recurrent — each frame's result feeds
the next — which is what keeps the edge from crawling between frames. That
also means frames MUST be processed in order and the state must not be reused
across clips.

NOTE ON LICENCE: RVM's weights are GPL-3.0, while this engine is MIT. They are
not committed here and are downloaded separately. See NOTICE.

As with the face track, the arithmetic is kept apart from the model so the
part that decides what counts as a usable matte can be tested exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import ENGINE_ROOT, get


class MatteError(RuntimeError):
    """Raised when the matte cannot be produced at all."""


# Alpha above this counts as "the presenter is here" when measuring how much
# of the frame the matte covers. Deliberately mid-scale: RVM puts genuinely
# uncertain pixels (hair edges, motion blur) in between, and counting those
# as solid would overstate the coverage.
SOLID_ALPHA = 0.5

# RVM's internal downsample for the recurrent encoder. The authors recommend
# 0.25 for 1080p and above, 0.4 for smaller frames. It does not set the output
# resolution — the alpha comes back at full input size.
DEFAULT_DOWNSAMPLE = 0.4


def model_path(config: dict) -> Path:
    """Resolve the configured model file, or say precisely what is missing."""
    configured = get(config, "analysis.personMatte.model", "")
    if not configured:
        raise MatteError("analysis.personMatte.model is not set in engine.config.json.")

    path = Path(configured)
    if not path.is_absolute():
        path = ENGINE_ROOT / path

    if not path.is_file():
        raise MatteError(
            f"Matting model not found: {path}\n"
            "It is not committed to this repository (it is a third-party binary, "
            "and GPL-3.0).\nSee models/README.md for the download and its checksum."
        )
    return path


def matte_size(width: int, height: int, long_edge: int) -> tuple[int, int]:
    """Scale the frame so its long edge is `long_edge`, keeping both sides even.

    Even dimensions because every codec worth using wants them, and the matte
    is encoded as a video.
    """
    if width <= 0 or height <= 0:
        raise ValueError(f"width and height must be positive (got {width}x{height})")
    if long_edge <= 0:
        raise ValueError(f"long_edge must be positive (got {long_edge})")

    longest = max(width, height)
    scale = min(1.0, long_edge / longest)
    w = max(2, int(round(width * scale)) // 2 * 2)
    h = max(2, int(round(height * scale)) // 2 * 2)
    return w, h


class Matter:
    """One RVM session, carrying its recurrent state across frames."""

    def __init__(self, config: dict, *, width: int, height: int) -> None:
        try:
            import numpy as np
            import onnxruntime as ort
        except ImportError as exc:  # pragma: no cover - environment problem
            raise MatteError(
                "onnxruntime and numpy are required for matting. Install with:\n"
                "  python -m pip install onnxruntime numpy"
            ) from exc

        self._np = np
        self.width = width
        self.height = height
        self.downsample = float(
            get(config, "analysis.personMatte.downsampleRatio", DEFAULT_DOWNSAMPLE)
        )

        options = ort.SessionOptions()
        options.intra_op_num_threads = int(
            get(config, "analysis.personMatte.threads", 0)
        )
        self._session = ort.InferenceSession(
            str(model_path(config)), options, providers=["CPUExecutionProvider"]
        )
        self.reset()

    def reset(self) -> None:
        """Clear the recurrent state. Call between clips, never within one."""
        np = self._np
        self._state = {f"r{i}i": np.zeros((1, 1, 1, 1), dtype=np.float32) for i in range(1, 5)}

    def alpha(self, bgr: bytes) -> Any:
        """Alpha for one BGR frame, as a float32 array of (height, width)."""
        np = self._np
        frame = np.frombuffer(bgr, dtype=np.uint8).reshape(self.height, self.width, 3)
        # ffmpeg gives BGR; RVM wants RGB, channels first, 0..1.
        src = (frame[:, :, ::-1].astype(np.float32) / 255.0).transpose(2, 0, 1)[None]

        outputs = self._session.run(
            None,
            {
                "src": src,
                "downsample_ratio": np.array([self.downsample], dtype=np.float32),
                **self._state,
            },
        )
        # outputs: fgr, pha, r1o..r4o — the new state replaces the old.
        self._state = {f"r{i}i": outputs[i + 1] for i in range(1, 5)}
        return outputs[1][0, 0]


# --------------------------------------------------------------------------
# pure arithmetic
# --------------------------------------------------------------------------


def alpha_to_bytes(alpha: Any) -> bytes:
    """Quantise a 0..1 alpha plane to 8-bit grey for encoding."""
    import numpy as np

    scaled = np.clip(alpha, 0.0, 1.0) * 255.0
    # Round rather than truncate: truncation would turn a solid 1.0 into 254.
    return np.rint(scaled).astype(np.uint8).tobytes()


def coverage(alpha: Any, threshold: float = SOLID_ALPHA) -> float:
    """Fraction of the frame the presenter solidly occupies."""
    import numpy as np

    return float(np.mean(np.asarray(alpha) > threshold))


@dataclass(frozen=True)
class MatteSummary:
    """What the run found, before it is turned into an artefact."""

    frames: int
    meanCoverage: float
    minCoverage: float
    maxCoverage: float
    emptyFrames: list[int]
    gaps: list[dict[str, Any]]


def summarise(coverages: list[float], *, fps: float, empty_below: float = 0.02) -> MatteSummary:
    """Reduce per-frame coverage to the few facts worth recording.

    A frame whose coverage is near zero means the matte found nobody. That is
    not necessarily an error — the presenter may have stepped out — but it is
    exactly the condition under which a Behind layer stops being behind
    anything, so each run of such frames is recorded.
    """
    if fps <= 0:
        raise ValueError(f"fps must be positive (got {fps})")
    if not coverages:
        return MatteSummary(0, 0.0, 0.0, 0.0, [], [])

    empty = [i for i, c in enumerate(coverages) if c < empty_below]

    gaps: list[dict[str, Any]] = []
    start: int | None = None
    previous: int | None = None
    for index in empty:
        if start is None:
            start = index
        elif previous is not None and index != previous + 1:
            gaps.append({"startFrame": start, "endFrame": previous})
            start = index
        previous = index
    if start is not None and previous is not None:
        gaps.append({"startFrame": start, "endFrame": previous})

    for gap in gaps:
        gap["startSeconds"] = gap["startFrame"] / fps
        gap["endSeconds"] = (gap["endFrame"] + 1) / fps

    return MatteSummary(
        frames=len(coverages),
        meanCoverage=sum(coverages) / len(coverages),
        minCoverage=min(coverages),
        maxCoverage=max(coverages),
        emptyFrames=empty,
        gaps=gaps,
    )


__all__ = [
    "DEFAULT_DOWNSAMPLE",
    "SOLID_ALPHA",
    "MatteError",
    "MatteSummary",
    "Matter",
    "alpha_to_bytes",
    "coverage",
    "matte_size",
    "model_path",
    "summarise",
]
