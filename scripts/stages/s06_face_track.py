"""Stage 6 — face tracking.

Produces data/06-face-track.json: where the presenter's face is, frame by
frame, so the composition layer can frame a shot and keep graphics off the
face.

Like the silence stage, this one carries no editorial judgement. It reports
where the face is and how confident it is; deciding what to do about a stretch
where the face was lost belongs to whatever uses the track.

The track is built at the OUTPUT frame rate, not the source's. Both output
formats share 30 fps, so one track serves portrait and landscape alike, and
the composition layer never has to resample it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..lib import faces
from ..lib.config import get
from ..lib.jsonio import read_json, rounded, utc_now, write_json
from ..lib.paths import ProjectPaths

SCHEMA = "tadabbur-motion/face-track@1"


def _warnings(track: dict[str, Any], min_coverage: float, duration: float) -> list[str]:
    """Plain statements of what is wrong with this track, if anything."""
    notes: list[str] = []
    stats = track["stats"]

    if not track["ok"]:
        notes.append(
            "No face was detected anywhere. Nothing may use this track for framing "
            "or for keeping graphics clear of the face."
        )
        return notes

    coverage = stats["coverage"]
    if coverage < min_coverage:
        notes.append(
            f"The face was only tracked for {coverage * 100:.1f}% of the video "
            f"(threshold {min_coverage * 100:.0f}%). Check for a presenter who turns "
            "away, leaves frame, or is lit from behind."
        )

    longest = max(
        (g["endSeconds"] - g["startSeconds"] for g in track["gaps"]),
        default=0.0,
    )
    if longest >= 1.0:
        notes.append(
            f"Longest stretch with no detected face: {longest:.2f}s. Inside a gap the "
            "face position is held, not known — an effect that promises to stay off "
            "the face cannot keep that promise there."
        )

    if stats["meanScore"] is not None and stats["meanScore"] < 0.75:
        notes.append(
            f"Mean detection confidence is {stats['meanScore']:.2f}, which is low. "
            "The boxes may be loose even where coverage looks fine."
        )

    if duration and track["frames"] / track["fps"] < duration - 0.5:
        notes.append(
            "The track is shorter than the video. Frames after its end hold the last "
            "known position."
        )

    return notes


def run(config: dict, paths: ProjectPaths) -> dict[str, Any]:
    """Detect the presenter's face across the video and write the artefact."""
    metadata = read_json(paths.metadata)
    source = Path(metadata["source"]["path"])
    video = metadata.get("video") or {}

    # The DISPLAYED size, not the stored one: a phone-shot portrait clip is
    # stored landscape with a rotation matrix, and ffmpeg applies that matrix
    # on decode. Asking for the stored size squashes every frame.
    width = video.get("displayWidth") or video.get("width")
    height = video.get("displayHeight") or video.get("height")
    if not width or not height:
        raise faces.FaceTrackError(
            "01-metadata.json records no video size, so there is no video stream "
            "to track a face in."
        )

    duration = metadata["container"].get("durationSeconds") or 0.0
    fps = float(get(config, "output.portrait.fps", 30))
    frames = max(1, int(round(duration * fps))) if duration else 1

    settings = get(config, "analysis.faceTrack", {})

    samples = faces.detect(config, source, width=int(width), height=int(height))

    track = faces.build_track(
        samples,
        frames=frames,
        fps=fps,
        width=int(width),
        height=int(height),
        smoothing_seconds=float(settings.get("smoothingSeconds", 0.25)),
        max_gap_seconds=float(settings.get("maxGapSeconds", 0.5)),
        head_top_above_centre=float(
            settings.get("headTopAboveCentre", faces.DEFAULT_HEAD_TOP_ABOVE_CENTRE)
        ),
    )

    attention = settings.get("attention", {}) or {}
    looking_away = (
        faces.attention_spans(
            samples,
            min_seconds=float(attention.get("minSeconds", 0.6)),
            threshold=float(attention.get("threshold", 1.6)),
        )
        if attention.get("enabled", True)
        else []
    )

    # A glance away while talking has to be COVERED; one during silence can
    # simply be removed. That is the whole difference between needing B-roll
    # and needing a cut, so it is decided here rather than left to a person
    # cross-referencing two files.
    if looking_away and paths.transcript.exists():
        spoken = [
            (float(seg["start"]), float(seg["end"]))
            for seg in read_json(paths.transcript).get("segments", [])
            if (seg.get("text") or "").strip()
        ]
        for span in looking_away:
            talking = any(
                e > span["start"] and s0 < span["end"] for s0, e in spoken
            )
            span["speaking"] = talking
            span["suggest"] = "cover" if talking else "trim"
            span["note"] = (
                "Looking away while speaking: cover it with B-roll, since the words "
                "are needed."
                if talking
                else "Looking away with nothing being said: this can simply be cut."
            )

    min_coverage = float(settings.get("minCoverage", 0.8))
    warnings = _warnings(track, min_coverage, duration)

    payload = {
        "schema": SCHEMA,
        "generatedAt": utc_now(),
        "detector": {
            "name": "opencv FaceDetectorYN (YuNet)",
            "model": str(faces.model_path(config)),
            "sampleFps": settings.get("sampleFps", 10),
            "detectWidth": settings.get("detectWidth", 640),
            "scoreThreshold": settings.get("scoreThreshold", 0.6),
        },
        "ok": track["ok"],
        "reason": track["reason"],
        # Everything below is normalised: x and w by width, y and top by
        # height. Seconds, never frames, in every other artefact — but a face
        # track IS per frame by nature, so this one carries fps and a frame
        # count and says so.
        "fps": track["fps"],
        "frames": track["frames"],
        "sourceWidth": track["width"],
        "sourceHeight": track["height"],
        "headTopAboveCentre": float(
            settings.get("headTopAboveCentre", faces.DEFAULT_HEAD_TOP_ABOVE_CENTRE)
        ),
        "stats": {
            "sampleCount": track["stats"]["sampleCount"],
            "coverage": rounded(track["stats"]["coverage"], 4),
            "meanScore": rounded(track["stats"]["meanScore"], 4)
            if track["stats"]["meanScore"] is not None
            else None,
            "gapCount": len(track["gaps"]),
            "lookingAwayCount": len(looking_away),
            "lookingAwaySeconds": rounded(
                sum(a["durationSeconds"] for a in looking_away)
            ),
            "lookingAwayToCover": sum(
                1 for a in looking_away if a.get("suggest") == "cover"
            ),
            "lookingAwayToTrim": sum(
                1 for a in looking_away if a.get("suggest") == "trim"
            ),
        },
        "warnings": warnings,
        # Where the eyes left the lens. Said plainly: this reports direction,
        # never intent, and it is a prompt to look rather than an instruction.
        "lookingAway": looking_away,
        "gaps": [
            {
                "startFrame": g["startFrame"],
                "endFrame": g["endFrame"],
                "startSeconds": rounded(g["startSeconds"]),
                "endSeconds": rounded(g["endSeconds"]),
            }
            for g in track["gaps"]
        ],
        "face": [[rounded(x, 5), rounded(y, 5), rounded(w, 5)] for x, y, w in track["face"]],
        "top": [rounded(t, 5) for t in track["top"]],
    }

    write_json(paths.face_track, payload)
    return payload
