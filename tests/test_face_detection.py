"""End-to-end face tracking against a clip whose face position is known.

Run from the engine root:

    python -m tests.test_face_detection

test_face_track.py checks the arithmetic with hand-built samples. It cannot
catch a fault in the half that touches real media: if frames came out of
ffmpeg reshaped wrongly, or detections were scaled back to source pixels
wrongly, the detector would simply find nothing — which is indistinguishable
from a clip that has no face in it.

So this generates a clip with a face drawn at a trajectory known in advance,
and checks the track comes back with that trajectory. It needs ffmpeg with
libx264 and the YuNet model; it skips, loudly, if either is missing.

The face is DRAWN, not photographed. This proves the plumbing and the
coordinate maths. It says nothing about how well YuNet finds a real presenter
in real light — that is unverified until there is footage.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from scripts.lib import faces, media
from scripts.lib.config import load_config

WIDTH = 1280
HEIGHT = 720
FPS = 30
SECONDS = 3
FRAMES = FPS * SECONDS

# The trajectory the face is drawn along, as fractions of the frame.
X_START = 0.35
X_END = 0.65
Y_CENTRE = 300
FACE_WIDTH = 150

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


def draw_face(draw, cx: int, cy: int) -> None:
    """A face plausible enough for a detector trained on photographs.

    Proportions matter more than prettiness: a detector keys on the dark
    eye band above a lighter midface, and on the overall oval.
    """
    fw, fh = FACE_WIDTH, int(FACE_WIDTH * 1.3)
    skin = (214, 176, 148)

    draw.ellipse([cx - 46, cy + 70, cx + 46, cy + 210], fill=(188, 152, 126))
    draw.ellipse([cx - fw // 2, cy - fh // 2, cx + fw // 2, cy + fh // 2], fill=skin)
    draw.chord(
        [cx - fw // 2 - 8, cy - fh // 2 - 14, cx + fw // 2 + 8, cy + 30],
        180, 360, fill=(58, 44, 38),
    )
    draw.ellipse([cx - 62, cy - 56, cx + 62, cy - 16], fill=(196, 158, 132))
    for sx in (-34, 34):
        draw.ellipse([cx + sx - 22, cy - 34, cx + sx + 22, cy - 8], fill=(245, 243, 240))
        draw.ellipse([cx + sx - 10, cy - 32, cx + sx + 10, cy - 10], fill=(74, 56, 42))
        draw.ellipse([cx + sx - 5, cy - 27, cx + sx + 5, cy - 15], fill=(16, 14, 14))
        draw.arc([cx + sx - 26, cy - 50, cx + sx + 26, cy - 24], 190, 350,
                 fill=(58, 44, 38), width=6)
    draw.polygon([(cx, cy - 10), (cx - 14, cy + 30), (cx + 14, cy + 30)], fill=(198, 160, 134))
    draw.ellipse([cx - 16, cy + 22, cx + 16, cy + 38], fill=(206, 168, 140))
    draw.ellipse([cx - 34, cy + 56, cx + 34, cy + 82], fill=(168, 96, 92))
    draw.line([cx - 32, cy + 69, cx + 32, cy + 69], fill=(120, 64, 62), width=3)


def expected_cx(frame: int) -> float:
    k = frame / (FRAMES - 1)
    return (X_START + (X_END - X_START) * k) * WIDTH


def make_clip(config: dict, destination: Path, work: Path) -> None:
    """Render the frames and encode them."""
    from PIL import Image, ImageDraw, ImageFilter

    for f in range(FRAMES):
        img = Image.new("RGB", (WIDTH, HEIGHT), (118, 126, 140))
        draw_face(ImageDraw.Draw(img), int(round(expected_cx(f))), Y_CENTRE)
        img.filter(ImageFilter.GaussianBlur(1.0)).save(work / f"{f:04d}.png")

    media.run(
        [
            str(media.ffmpeg_bin(config)),
            "-hide_banner", "-nostdin", "-y",
            "-framerate", str(FPS),
            "-i", str(work / "%04d.png"),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            str(destination),
        ]
    )


def main() -> int:
    config = load_config()

    try:
        faces.model_path(config)
    except faces.FaceTrackError as exc:
        print(f"SKIPPED — {exc}")
        return 0
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("SKIPPED — Pillow is not installed")
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        clip = work / "face-clip.mp4"

        print("Generating a clip with a known face trajectory")
        try:
            make_clip(config, clip, work)
        except media.MediaToolError as exc:
            print(f"SKIPPED — could not encode the clip:\n{exc}")
            return 0
        check("the clip was written", clip.is_file() and clip.stat().st_size > 0)

        print("\nDetection")
        samples = faces.detect(config, clip, width=WIDTH, height=HEIGHT)
        check("the face is found", len(samples) > 0, f"got {len(samples)} samples")
        if not samples:
            print(f"\n{_checks - len(_failures)}/{_checks} checks passed")
            return 1

        sample_fps = float(config["analysis"]["faceTrack"]["sampleFps"])
        expected_samples = SECONDS * sample_fps
        check("roughly one sample per examined frame",
              abs(len(samples) - expected_samples) <= 2,
              f"got {len(samples)}, expected about {expected_samples:.0f}")
        check("detection confidence is high",
              min(s.score for s in samples) > 0.5,
              f"lowest {min(s.score for s in samples):.3f}")

        print("\nCoordinates are scaled back to source pixels")
        # Detection runs on a 640-wide frame; the source is 1280 wide. A
        # missing scale-back would halve every coordinate, so this is the
        # check that catches it.
        first, last = samples[0], samples[-1]
        check("the first sample sits near the trajectory start",
              abs(first.cx - expected_cx(0)) < 40,
              f"got {first.cx:.0f}, expected about {expected_cx(0):.0f}")
        check("the last sample sits near the trajectory end",
              abs(last.cx - expected_cx(FRAMES - 1)) < 40,
              f"got {last.cx:.0f}, expected about {expected_cx(FRAMES - 1):.0f}")
        check("the face width is close to the drawn width",
              abs(first.w - FACE_WIDTH) < 40,
              f"got {first.w:.0f}, drawn {FACE_WIDTH}")
        check("vertical position is near the drawn centre",
              abs(first.cy - Y_CENTRE) < 50,
              f"got {first.cy:.0f}, drawn {Y_CENTRE}")

        print("\nThe assembled track")
        track = faces.build_track(
            samples, frames=FRAMES, fps=float(FPS), width=WIDTH, height=HEIGHT,
        )
        check("the track is ok", track["ok"] is True)
        check("one entry per frame", len(track["face"]) == FRAMES)
        check("coverage is complete", track["stats"]["coverage"] > 0.98,
              f"got {track['stats']['coverage']:.3f}")
        check("no gaps", track["gaps"] == [], f"got {track['gaps']}")

        xs = [f[0] for f in track["face"]]
        check("the track starts near 0.35 of the width", abs(xs[0] - X_START) < 0.04,
              f"got {xs[0]:.3f}")
        check("the track ends near 0.65 of the width", abs(xs[-1] - X_END) < 0.04,
              f"got {xs[-1]:.3f}")
        # Smoothing may flatten a step, but it must never reverse a steady move.
        backwards = sum(1 for a, b in zip(xs, xs[1:]) if b < a - 1e-6)
        check("the track never moves backwards", backwards == 0,
              f"{backwards} frame(s) went the wrong way")
        check("the crown estimate is above the face centre",
              all(t < f[1] for t, f in zip(track["top"], track["face"])))

    print(f"\n{_checks - len(_failures)}/{_checks} checks passed")
    if _failures:
        print("\nFailed:")
        for failure in _failures:
            print(f"  - {failure}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
