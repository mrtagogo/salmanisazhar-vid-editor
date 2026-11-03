"""Put a finished project where Remotion can read it.

Remotion runs in a browser. It cannot open a file by absolute path, and it
cannot read projects/ — anything it shows has to be served from public/. So
this writes a proxy of the cut and a data file beside it.

It also does the one piece of arithmetic that cannot be skipped: the
transcript describes the UNCUT recording, and the cut is shorter with holes in
it. Every caption timing is moved onto the cut here, and anything that was
removed is dropped rather than shown at a guessed time.

    python -m scripts.prepare_composition --slug kajian-yusuf-sync
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .lib import media, retime
from .lib.config import ENGINE_ROOT, load_config
from .lib.jsonio import read_json
from .lib.paths import PROJECTS_DIR

PUBLIC_DIR = ENGINE_ROOT / "public"

# Captions are built from the transcriber's own segments, which follow the
# speaker's phrasing. A segment longer than this is split, because a subtitle
# that hangs for six seconds stops tracking what is being said.
MAX_CUE_SECONDS = 4.0
MAX_CUE_WORDS = 7


def _split(words: list[dict]) -> list[list[dict]]:
    """Break a long run of words into cue-sized groups."""
    groups: list[list[dict]] = []
    current: list[dict] = []
    for word in words:
        if current and (
            len(current) >= MAX_CUE_WORDS
            or word["end"] - current[0]["start"] > MAX_CUE_SECONDS
        ):
            groups.append(current)
            current = []
        current.append(word)
    if current:
        groups.append(current)
    return groups


def build_cues(transcript: dict, edl: dict, keep_ranges: list[dict]) -> list[dict[str, Any]]:
    """Caption cues on the cut's timeline."""
    suspected = retime.retime_regions(edl.get("suspectedRegions") or [], keep_ranges)
    protected = retime.retime_regions(edl.get("protectedRegions") or [], keep_ranges)

    cues: list[dict[str, Any]] = []
    for segment in transcript.get("segments", []):
        words = retime.retime_words(segment.get("words") or [], keep_ranges)
        if not words:
            continue
        for group in _split(words):
            start = float(group[0]["start"])
            end = float(group[-1]["end"])
            overlaps = lambda rs: [  # noqa: E731
                r["id"] for r in rs if end > r["start"] and start < r["end"]
            ]
            cues.append(
                {
                    "start": round(start, 3),
                    "end": round(end, 3),
                    "text": " ".join(w["word"].strip() for w in group),
                    "words": [
                        {
                            "w": w["word"].strip(),
                            "start": round(float(w["start"]), 3),
                            "end": round(float(w["end"]), 3),
                        }
                        for w in group
                    ],
                    # Carried through so the composition can refuse to
                    # decorate something that may be scripture.
                    "suspected": overlaps(suspected),
                    "protected": overlaps(protected),
                }
            )
    cues.sort(key=lambda c: c["start"])
    return cues


def retime_track(track: dict, keep_ranges: list[dict], frames: int, fps: float) -> dict[str, Any]:
    """Sample a per-frame face track onto the cut's frames.

    The track describes the uncut recording. For each frame of the cut we ask
    where it came from and read the track there, so the face follows the
    picture across every join instead of drifting after the first removal.
    """
    face_in, top_in = track["face"], track["top"]
    source_fps = float(track["fps"])
    face: list[list[float]] = []
    top: list[float] = []
    for frame in range(frames):
        at = retime.to_source(keep_ranges, frame / fps)
        index = 0 if at is None else min(len(face_in) - 1, max(0, round(at * source_fps)))
        face.append([round(v, 5) for v in face_in[index]])
        top.append(round(top_in[index], 5))
    return {"face": face, "top": top, "headTopAboveCentre": track.get("headTopAboveCentre")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="prepare_composition")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--crf", default="30", help="Proxy quality; lower is better.")
    parser.add_argument(
        "--track",
        help=(
            "A 06-face-track.json for the SAME source video. The face track "
            "belongs to the picture, so one computed for another project of the "
            "same recording is valid; it is re-timed onto this cut."
        ),
    )
    args = parser.parse_args(argv)

    config = load_config()
    data = PROJECTS_DIR / args.slug / "data"
    cut_artefact = data / "08-rough-cut.json"
    if not cut_artefact.is_file():
        raise SystemExit(
            f"No rough cut for {args.slug!r}. Approve the EDL and run --only cut first."
        )

    cut = read_json(cut_artefact)
    transcript = read_json(data / "02-transcript.json")
    edl = read_json(data / "04-edl.json")
    keep_ranges = cut["keepRanges"]

    out = PUBLIC_DIR / args.slug
    out.mkdir(parents=True, exist_ok=True)

    proxy = out / "video.mp4"
    print(f"proxy  : {proxy}")
    media.run(
        [
            str(media.ffmpeg_bin(config)),
            "-hide_banner", "-nostdin", "-y",
            "-i", cut["roughCut"],
            "-c:v", "libx264", "-preset", "veryfast", "-crf", str(args.crf),
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "96k",
            "-movflags", "+faststart",
            str(proxy),
        ],
        timeout=3600,
    )

    cues = build_cues(transcript, edl, keep_ranges)
    payload = {
        "slug": args.slug,
        "video": f"{args.slug}/video.mp4",
        "fps": 30,
        "width": cut["width"],
        "height": cut["height"],
        "durationSeconds": cut["actualDurationSeconds"],
        "soundFrom": Path(cut.get("soundFrom", "")).name or None,
        "cues": cues,
        "note": (
            "Timings are on the CUT timeline. Anything removed by the cut is "
            "absent, not moved."
        ),
    }
    if args.track:
        track = read_json(Path(args.track))
        if not track.get("ok"):
            raise SystemExit(f"That face track is not usable: {track.get('reason')}")
        frames = int(round(float(cut["actualDurationSeconds"]) * 30))
        payload["track"] = retime_track(track, keep_ranges, frames, 30.0)
        print(f"track  : {frames} frames re-timed onto the cut")

    (out / "data.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    flagged = sum(1 for c in cues if c["suspected"] or c["protected"])
    print(f"cues   : {len(cues)} ({flagged} touching a protected or suspected span)")
    print(f"data   : {out / 'data.json'}")
    print(f"size   : {proxy.stat().st_size/1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
