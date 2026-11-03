"""Person matte: arithmetic, the video round-trip, and a real run.

Run from the engine root:

    python -m tests.test_matte

Three groups:

1. The arithmetic, with hand-built numbers.
2. The video round-trip. The matte is stored as a greyscale video, and a
   matte squeezed into the broadcast 16-235 range comes back with solid alpha
   at about 0.92 — the presenter would render slightly see-through, and the
   background slightly visible through them. Encoding and decoding a known
   pattern is the only way to be sure that is not happening.
3. A real run, against talking-head footage in _ref/. RVM is trained on
   photographs: a drawn stand-in produces almost no alpha at all, so unlike
   the face detector this cannot be tested with a synthetic figure. _ref/ is
   not committed, so this group skips on a fresh clone.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from scripts.lib import matte as matte_lib
from scripts.lib import media
from scripts.lib.config import load_config
from scripts.lib.paths import ProjectPaths
from scripts.stages import s01_ingest, s07_person_matte

DEMO = Path("_ref/facecammaxxing/demo/slow-push.mp4")

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


def main() -> int:
    config = load_config()
    import numpy as np

    print("Sizing")
    check("a 1080x1920 frame is scaled to the long edge",
          matte_lib.matte_size(1080, 1920, 1280) == (720, 1280),
          f"got {matte_lib.matte_size(1080, 1920, 1280)}")
    check("a landscape frame is scaled the same way",
          matte_lib.matte_size(1920, 1080, 1280) == (1280, 720),
          f"got {matte_lib.matte_size(1920, 1080, 1280)}")
    check("a frame already smaller is left alone",
          matte_lib.matte_size(640, 360, 1280) == (640, 360))
    check("both sides come out even",
          all(v % 2 == 0 for v in matte_lib.matte_size(1079, 1921, 1281)),
          f"got {matte_lib.matte_size(1079, 1921, 1281)}")
    for bad in ((0, 100, 128), (100, 0, 128), (100, 100, 0)):
        try:
            matte_lib.matte_size(*bad)
            raised = False
        except ValueError:
            raised = True
        check(f"matte_size{bad} raises ValueError", raised)

    print("\nQuantising")
    alpha = np.array([[0.0, 0.5, 1.0]], dtype=np.float32)
    raw = matte_lib.alpha_to_bytes(alpha)
    check("empty alpha becomes 0", raw[0] == 0, f"got {raw[0]}")
    check("solid alpha becomes 255", raw[2] == 255, f"got {raw[2]}")
    check("half alpha rounds to 128", raw[1] == 128, f"got {raw[1]}")
    over = matte_lib.alpha_to_bytes(np.array([[-0.5, 1.7]], dtype=np.float32))
    check("out-of-range alpha is clamped", over[0] == 0 and over[1] == 255,
          f"got {over[0]}, {over[1]}")

    print("\nCoverage")
    half = np.zeros((10, 10), dtype=np.float32)
    half[:5, :] = 1.0
    check("coverage counts the solid half", abs(matte_lib.coverage(half) - 0.5) < 1e-6)
    check("uncertain pixels do not count as solid",
          matte_lib.coverage(np.full((4, 4), 0.4, dtype=np.float32)) == 0.0)

    print("\nSummarising")
    summary = matte_lib.summarise([0.4] * 10, fps=10.0)
    check("a steady matte reports no gaps", summary.gaps == [])
    check("mean coverage is reported", abs(summary.meanCoverage - 0.4) < 1e-6)

    # Present, gone for half a second, present again, then gone at the end.
    pattern = [0.4] * 5 + [0.0] * 5 + [0.4] * 5 + [0.0] * 3
    gapped = matte_lib.summarise(pattern, fps=10.0)
    check("two separate empty stretches are found", len(gapped.gaps) == 2,
          f"got {len(gapped.gaps)}")
    if len(gapped.gaps) == 2:
        first, second = gapped.gaps
        check("the first gap spans the right frames",
              first["startFrame"] == 5 and first["endFrame"] == 9,
              f"got {first['startFrame']}..{first['endFrame']}")
        check("the trailing gap runs to the last frame",
              second["endFrame"] == len(pattern) - 1,
              f"got {second['endFrame']}")
        check("gap seconds follow the frame rate",
              abs(first["startSeconds"] - 0.5) < 1e-6,
              f"got {first['startSeconds']}")
    check("an empty run summarises to nothing",
          matte_lib.summarise([], fps=30.0).frames == 0)
    try:
        matte_lib.summarise([0.1], fps=0.0)
        raised = False
    except ValueError:
        raised = True
    check("a zero frame rate raises ValueError", raised)

    print("\nVideo round-trip (full range must survive)")
    W, H = 64, 32
    # Left column empty, right column solid, middle a ramp.
    plane = np.zeros((H, W), dtype=np.float32)
    plane[:, W // 2:] = 1.0
    frame = matte_lib.alpha_to_bytes(plane)

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "matte.mp4"
        try:
            with media.frame_encoder(
                config, out, fps=10, width=W, height=H, pix_fmt="gray",
                output_args=s07_person_matte._encoder_args({"crf": 14, "preset": "medium"}),
            ) as write:
                for _ in range(10):
                    write(frame)
        except media.MediaToolError as exc:
            print(f"  SKIPPED — could not encode: {exc}")
        else:
            check("the matte video was written", out.is_file() and out.stat().st_size > 0)
            decoded = list(media.sample_frames(config, out, fps=10, width=W, height=H))
            check("frames come back", len(decoded) >= 5, f"got {len(decoded)}")
            if decoded:
                back = np.frombuffer(decoded[len(decoded) // 2], np.uint8).reshape(H, W, 3)
                left = float(back[:, : W // 2 - 4, 0].mean())
                right = float(back[:, W // 2 + 4 :, 0].mean())
                check("empty alpha survives as near 0", left < 6, f"got {left:.1f}")
                check("solid alpha survives as near 255", right > 249, f"got {right:.1f}")

    print("\nA real run")
    if not DEMO.is_file():
        print(f"  SKIPPED — {DEMO} is not present (it is not committed)")
    else:
        try:
            matte_lib.model_path(config)
        except matte_lib.MatteError as exc:
            print(f"  SKIPPED — {exc}")
        else:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                paths = ProjectPaths(
                    slug="matte-test", root=root,
                    data=root / "data", cache=root / "cache", review=root / "review",
                )
                paths.ensure()
                s01_ingest.run(config, DEMO.resolve(), paths)
                result = s07_person_matte.run(config, paths)

                check("the matte is usable", result["ok"] is True,
                      f"warnings: {result['warnings']}")
                check("the matte video exists",
                      Path(result["matteVideo"]).is_file())
                check("every frame was matted", result["frames"] > 0,
                      f"got {result['frames']}")

                stats = result["stats"]
                # A talking head fills a good part of a vertical frame, but
                # never all of it; near 100% would mean the background came
                # along too, near 0% that nobody was found.
                check("the presenter occupies a plausible share of the frame",
                      0.1 < stats["meanCoverage"] < 0.85,
                      f"got {stats['meanCoverage']}")
                check("no empty stretches in a clip of one person talking",
                      stats["gapCount"] == 0, f"got {stats['gapCount']} gap(s)")

                # Read the matte back and check it where the answer is known.
                frames = list(media.sample_frames(
                    config, Path(result["matteVideo"]), fps=result["fps"],
                    width=result["width"], height=result["height"],
                ))
                check("the matte video decodes to the expected frame count",
                      abs(len(frames) - result["frames"]) <= 2,
                      f"got {len(frames)} vs {result['frames']}")
                if frames:
                    mid = np.frombuffer(
                        frames[len(frames) // 2], np.uint8
                    ).reshape(result["height"], result["width"], 3)[:, :, 0]
                    corner = float(mid[:40, :40].mean())
                    check("the top corner is background", corner < 20,
                          f"got {corner:.1f}")
                    # The presenter stands in the middle of a vertical frame.
                    h, w = mid.shape
                    middle = float(mid[int(h * 0.55):int(h * 0.75),
                                       int(w * 0.35):int(w * 0.65)].mean())
                    check("the middle of the body is solid", middle > 200,
                          f"got {middle:.1f}")

    print(f"\n{_checks - len(_failures)}/{_checks} checks passed")
    if _failures:
        print("\nFailed:")
        for failure in _failures:
            print(f"  - {failure}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
