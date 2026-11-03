"""Face-track arithmetic.

Run from the engine root:

    python -m tests.test_face_track

Detection itself is not tested here: that needs real footage of a real face,
which this repository does not have. What IS tested is everything between the
detector and the composition layer — outlier rejection, interpolation,
smoothing, gap handling, normalisation and the empty case — because that is
where a bug would be silent. A face track that is merely wrong still renders;
it just drifts the camera, or lets a caption creep onto a face.

The samples below are built by hand, so every expected number is arrived at
independently of the code under test.
"""

from __future__ import annotations

import sys

from scripts.lib.faces import (
    DEFAULT_HEAD_TOP_ABOVE_CENTRE,
    FaceSample,
    alpha_for,
    build_track,
    ema,
    median3,
    smooth,
)

WIDTH = 1920
HEIGHT = 1080
FPS = 30.0

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


def near(a: float, b: float, tol: float = 1e-6) -> bool:
    return abs(a - b) <= tol


def steady(seconds: float, *, cx: float = 960.0, cy: float = 400.0, w: float = 300.0,
           sample_fps: float = 10.0, score: float = 0.9) -> list[FaceSample]:
    """A face that does not move, sampled at `sample_fps`."""
    count = int(round(seconds * sample_fps))
    return [
        FaceSample(time=i / sample_fps, cx=cx, cy=cy, w=w, score=score)
        for i in range(count)
    ]


def main() -> int:
    print("Outlier rejection")
    # One wild value between two sane ones must not survive.
    spiked = [100.0, 100.0, 900.0, 100.0, 100.0]
    cleaned = median3(spiked)
    check("a single wild sample is discarded", near(cleaned[2], 100.0), f"got {cleaned[2]}")
    check("the ends are left alone",
          near(cleaned[0], 100.0) and near(cleaned[-1], 100.0))
    check("a genuine step survives",
          median3([0.0, 0.0, 0.0, 10.0, 10.0, 10.0])[4] == 10.0)
    check("too short to filter is returned unchanged", median3([5.0, 7.0]) == [5.0, 7.0])

    print("\nSmoothing")
    flat = [5.0] * 20
    check("a constant signal is unchanged", all(near(v, 5.0) for v in smooth(flat, 0.3)))

    # The point of the backward pass: no lag. A one-sided EMA on a step lands
    # well short of the new level; the zero-phase version is centred on it.
    step = [0.0] * 10 + [1.0] * 10
    one_way = ema(step, 0.3)
    both_ways = smooth(step, 0.3)
    check("a one-pass EMA lags behind a step", one_way[10] < 0.5, f"got {one_way[10]:.3f}")
    check("zero-phase smoothing is centred on the step",
          0.3 < both_ways[9] < 0.7 and 0.3 < both_ways[10] < 0.7,
          f"got {both_ways[9]:.3f}, {both_ways[10]:.3f}")
    check("smoothing preserves the overall level",
          near(sum(both_ways) / len(both_ways), 0.5, 0.05))
    check("alpha falls as the time constant grows",
          alpha_for(0.5, FPS) < alpha_for(0.1, FPS))
    check("a zero time constant means no smoothing", alpha_for(0.0, FPS) == 1.0)

    print("\nEmpty input")
    empty = build_track([], frames=30, fps=FPS, width=WIDTH, height=HEIGHT)
    check("no detections is reported as not ok", empty["ok"] is False)
    check("no detections gives a reason", bool(empty["reason"]))
    check("no detections produces no face data", empty["face"] == [] and empty["top"] == [])
    check("no detections reports zero coverage", empty["stats"]["coverage"] == 0.0)

    print("\nNormalisation")
    track = build_track(
        steady(2.0), frames=60, fps=FPS, width=WIDTH, height=HEIGHT, smoothing_seconds=0.0
    )
    check("the track is ok", track["ok"] is True)
    check("one entry per frame", len(track["face"]) == 60 and len(track["top"]) == 60)
    x, y, w = track["face"][30]
    check("x is normalised by width", near(x, 960 / WIDTH, 1e-4), f"got {x}")
    check("y is normalised by height", near(y, 400 / HEIGHT, 1e-4), f"got {y}")
    check("w is normalised by width", near(w, 300 / WIDTH, 1e-4), f"got {w}")
    expected_top = (400 - DEFAULT_HEAD_TOP_ABOVE_CENTRE * 300) / HEIGHT
    check("top is the crown estimate above the centre",
          near(track["top"][30], expected_top, 1e-4),
          f"got {track['top'][30]}, expected {expected_top}")
    check("the crown sits above the face centre", track["top"][30] < y)

    print("\nInterpolation")
    # Two samples a second apart: the frame halfway between them must be
    # halfway between their positions.
    pair = [
        FaceSample(time=0.0, cx=100.0, cy=200.0, w=300.0, score=1.0),
        FaceSample(time=1.0, cx=300.0, cy=400.0, w=300.0, score=1.0),
    ]
    ramp = build_track(
        pair, frames=31, fps=FPS, width=WIDTH, height=HEIGHT, smoothing_seconds=0.0
    )
    mid_x = ramp["face"][15][0] * WIDTH
    check("a frame between samples is interpolated", near(mid_x, 200.0, 4.0), f"got {mid_x}")
    check("the first frame matches the first sample",
          near(ramp["face"][0][0] * WIDTH, 100.0, 1.0))
    check("the last frame matches the last sample",
          near(ramp["face"][30][0] * WIDTH, 300.0, 1.0))

    print("\nGaps")
    # Detections for the first second, then nothing until the fourth.
    gapped = steady(1.0) + [
        FaceSample(time=4.0, cx=960.0, cy=400.0, w=300.0, score=0.9)
    ]
    with_gap = build_track(
        gapped, frames=int(5 * FPS), fps=FPS, width=WIDTH, height=HEIGHT,
        max_gap_seconds=0.5, smoothing_seconds=0.0,
    )
    # Two gaps, not one: the hole in the middle, and the tail after the last
    # detection at 4.0s — the video runs to 5.0s, and from 4.5s onward the
    # engine no longer knows where the face is either.
    check("both the middle hole and the tail are recorded", len(with_gap["gaps"]) == 2,
          f"got {len(with_gap['gaps'])}")
    check("coverage is below 1 when there is a gap", with_gap["stats"]["coverage"] < 1.0,
          f"got {with_gap['stats']['coverage']}")
    check("every frame still has a position",
          len(with_gap["face"]) == int(5 * FPS) and all(len(f) == 3 for f in with_gap["face"]))
    if len(with_gap["gaps"]) == 2:
        middle, tail = with_gap["gaps"]
        check("the middle gap starts after the last early detection",
              middle["startSeconds"] > 1.0, f"got {middle['startSeconds']}")
        check("the middle gap ends before the late detection",
              middle["endSeconds"] < 4.1, f"got {middle['endSeconds']}")
        check("the tail gap opens after the final detection",
              tail["startSeconds"] > 4.0, f"got {tail['startSeconds']}")
        check("the tail gap runs to the end", near(tail["endSeconds"], 5.0, 0.05),
              f"got {tail['endSeconds']}")

    full = build_track(
        steady(5.0), frames=int(5 * FPS), fps=FPS, width=WIDTH, height=HEIGHT,
        max_gap_seconds=0.5, smoothing_seconds=0.0,
    )
    check("continuous detection reports no gaps", full["gaps"] == [])
    check("continuous detection reports full coverage",
          near(full["stats"]["coverage"], 1.0, 1e-9), f"got {full['stats']['coverage']}")

    print("\nRefusing nonsense")
    for label, kwargs in (
        ("zero frames", {"frames": 0, "fps": FPS, "width": WIDTH, "height": HEIGHT}),
        ("zero fps", {"frames": 10, "fps": 0.0, "width": WIDTH, "height": HEIGHT}),
        ("zero width", {"frames": 10, "fps": FPS, "width": 0, "height": HEIGHT}),
    ):
        try:
            build_track(steady(1.0), **kwargs)
            raised = False
        except ValueError:
            raised = True
        check(f"{label} raises ValueError", raised)

    print(f"\n{_checks - len(_failures)}/{_checks} checks passed")
    if _failures:
        print("\nFailed:")
        for failure in _failures:
            print(f"  - {failure}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
