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
            hit_protected = overlaps(protected)
            # Withholding exists to keep UNVERIFIED SCRIPTURE off the screen.
            # An untranscribed_speech suspicion says something extra was said
            # in this span that nobody wrote down — it says nothing about the
            # words that WERE written, and suppressing a perfectly good
            # subtitle because of it just leaves the viewer with silence.
            scripture = [
                r["id"]
                for r in suspected
                if end > r["start"]
                and start < r["end"]
                and r.get("reason") == "possible_transliterated_scripture"
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
                    "protected": hit_protected,
                    "withhold": bool(hit_protected or scripture),
                }
            )
    # A protected or suspected span with no words of its own would otherwise
    # pass with no subtitle at all — silently absent rather than visibly
    # withheld. Recovered scripture is exactly that case: it reaches the
    # transcript as a segment with no word timings, so nothing above produces
    # a cue for it, and the composition would show nothing without ever
    # saying why.
    for region in protected + suspected:
        covered = any(
            c["end"] > region["start"] and c["start"] < region["end"] for c in cues
        )
        if covered:
            continue
        cues.append(
            {
                "start": round(float(region["start"]), 3),
                "end": round(float(region["end"]), 3),
                "text": region.get("text", ""),
                "words": [],
                "suspected": [region["id"]] if region in suspected else [],
                "protected": [region["id"]] if region in protected else [],
                "withhold": region in protected
                or region.get("reason") == "possible_transliterated_scripture",
            }
        )

    cues.sort(key=lambda c: c["start"])
    return cues


# --- the effect plan -------------------------------------------------------
#
# The editing identity says DYNAMIC camera: intentional framing and subtle
# punch-ins, and explicitly NO random zoom. So every move below has to come
# from something in the material, not from a timer.

# A frame held still for longer than this goes dead on a phone screen.
STATIC_STRETCH_SECONDS = 14.0
# How far the slow push travels. Small on purpose: it should be felt, not seen.
PUSH_ZOOM = 1.10

# A pause this long was the speaker taking a beat before making a point, so
# the line after it is worth leaning into. Loosened at the presenter's
# request: one punch-in in two minutes read as nothing happening.
BEAT_SECONDS = 2.5
PUNCH_ZOOM = 1.18
PUNCH_SECONDS = 1.8
# Caps, so "a punch-in where he made a point" cannot become a tic.
MAX_PUNCHES = 9
PUNCH_SPACING_SECONDS = 8.0


def plan_effects(keep_ranges: list[dict], duration: float) -> list[dict[str, Any]]:
    """Turn what the cut did into camera moves and a scrim.

    Every entry is justified by something measured:

    - the scrim runs throughout, because the subtitles sit low over footage
      that can be any brightness;
    - a slow push covers stretches the cut left untouched for a long time,
      where the frame would otherwise sit dead;
    - a punch-in lands where a long pause was removed, because that pause was
      the speaker taking a beat before a point.
    """
    joins: list[dict[str, float]] = []
    elapsed = 0.0
    for index, keep in enumerate(keep_ranges):
        length = float(keep["end"]) - float(keep["start"])
        elapsed += length
        if index + 1 < len(keep_ranges):
            removed = float(keep_ranges[index + 1]["start"]) - float(keep["end"])
            joins.append({"at": elapsed, "removed": removed})

    # Punch-ins first: where they overlap a push, the punch should win, and
    # the stage takes the first camera effect it finds.
    effects: list[dict[str, Any]] = []
    chosen: list[float] = []
    # Strongest beats first, so the best moments win the spacing budget.
    for join in sorted(joins, key=lambda j: -j["removed"]):
        if len(effects) >= MAX_PUNCHES:
            break
        if join["removed"] < BEAT_SECONDS:
            break
        # Distance to EVERY punch already chosen, not just the last one added.
        # Comparing against the last added fails for anything earlier in time,
        # where the difference is negative and always looks too close.
        if any(abs(join["at"] - at) < PUNCH_SPACING_SECONDS for at in chosen):
            continue
        if join["at"] + PUNCH_SECONDS > duration:
            continue
        effects.append(
            {
                "fx": "lean-in",
                "start": round(join["at"], 3),
                "end": round(join["at"] + PUNCH_SECONDS, 3),
                "zoom": PUNCH_ZOOM,
                "dof": 0,
                "parallax": 0.5,
            }
        )
        chosen.append(join["at"])
    effects.sort(key=lambda e: e["start"])

    taken = sorted((e["start"], e["end"]) for e in effects)
    edges = [0.0] + [j["at"] for j in joins] + [duration]

    # A stretch is split AROUND the punches inside it rather than abandoned.
    # A 1.8s punch should not cancel a fifteen-second push; it should divide
    # it, so the frame still moves either side instead of sitting dead.
    stretches: list[tuple[float, float]] = []
    for low, high in zip(edges, edges[1:]):
        cursor = low
        for a, b in taken:
            if b <= cursor or a >= high:
                continue
            if a - cursor > 0:
                stretches.append((cursor, min(a, high)))
            cursor = max(cursor, b)
        if high - cursor > 0:
            stretches.append((cursor, high))

    for low, high in stretches:
        if high - low < STATIC_STRETCH_SECONDS:
            continue
        effects.append(
            {
                "fx": "slow-push",
                "start": round(low, 3),
                "end": round(high, 3),
                "zoom": PUSH_ZOOM,
                # No defocus: this is one person against a plain wall, and
                # melting the wall would only draw attention to it.
                "blur": 0,
                "parallax": 1,
            }
        )

    effects.append(
        {
            "fx": "bottom-fade",
            "start": 0.0,
            "end": round(duration, 3),
            "amount": 0.55,
            "from": 0.55,
        }
    )
    return effects


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
    parser.add_argument(
        "--source",
        action="store_true",
        help=(
            "Prepare the UNCUT recording instead of the rough cut, with every "
            "proposed cut marked by its number from the decision sheet. For "
            "checking what a number refers to before approving it."
        ),
    )
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
    if not args.source and not cut_artefact.is_file():
        raise SystemExit(
            f"No rough cut for {args.slug!r}. Approve the EDL and run --only cut "
            "first, or pass --source to review the uncut recording."
        )

    transcript = read_json(data / "02-transcript.json")
    edl = read_json(data / "04-edl.json")

    if args.source:
        # The decision sheet numbers refer to the UNCUT recording, so reviewing
        # them against a cut would be showing the wrong timeline. One keep-range
        # covering everything makes the re-timing an identity.
        metadata = read_json(data / "01-metadata.json")
        video = metadata.get("video") or {}
        duration = float(edl["durationSeconds"])
        cut = {
            "roughCut": metadata["source"]["path"],
            "keepRanges": [{"start": 0.0, "end": duration}],
            "actualDurationSeconds": duration,
            "width": video.get("displayWidth") or video.get("width"),
            "height": video.get("displayHeight") or video.get("height"),
            "soundFrom": metadata["source"]["path"],
        }
    else:
        cut = read_json(cut_artefact)
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

    # Every proposed cut, numbered as the decision sheet numbers it, so a
    # number on the sheet can be looked at rather than imagined.
    numbers = {}
    number_file = data / "09-decision-numbers.json"
    if number_file.is_file():
        numbers = {v: k for k, v in read_json(number_file)["numbers"].items()}
    marks = []
    for proposal in sorted(edl["proposals"], key=lambda p: float(p["start"])):
        span = retime.clamp_to_cut(
            keep_ranges, float(proposal["start"]), float(proposal["end"])
        )
        if span is None:
            continue
        marks.append(
            {
                "number": numbers.get(proposal["id"]),
                "id": proposal["id"],
                "kind": proposal.get("kind"),
                "status": proposal["status"],
                "start": round(span[0], 3),
                "end": round(span[1], 3),
            }
        )
    payload = {
        "slug": args.slug,
        "video": f"{args.slug}/video.mp4",
        "fps": 30,
        "width": cut["width"],
        "height": cut["height"],
        "durationSeconds": cut["actualDurationSeconds"],
        "soundFrom": Path(cut.get("soundFrom", "")).name or None,
        "cues": cues,
        "marks": marks,
        "effects": plan_effects(keep_ranges, float(cut["actualDurationSeconds"])),
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
