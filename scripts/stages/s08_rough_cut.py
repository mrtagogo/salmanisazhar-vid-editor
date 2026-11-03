"""Stage 8 — the rough cut.

The first stage that produces a video. It applies the cuts a human approved
and nothing else.

Two rules shape everything here:

1. **It refuses to run until the EDL is approved.** Not a warning, not a
   default — a refusal. The approval checkpoint is the whole reason the
   analysis side stops where it does, and a cutting stage that could be
   talked into running without it would make the checkpoint decorative.

2. **It recomputes the keep-ranges from the current statuses** rather than
   reading `plans` out of the EDL. Those plans were built before a human
   touched the file. Approving means setting each `review` proposal to `auto`
   (apply) or `blocked` (keep), so after that edit the stored plans describe
   a decision nobody made.

Cutting is done in one ffmpeg pass with trim/concat and a re-encode. Stream
copying would be faster but can only cut at keyframes, which moves every cut
point by up to several seconds — onto words, in practice.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..lib import media
from ..lib.config import get
from ..lib.jsonio import read_json, rounded, utc_now, write_json
from ..lib.paths import ProjectPaths, audio_source
from .s04_edl import STATUS_AUTO, STATUS_REVIEW, _build_plan, cutting_profile

SCHEMA = "tadabbur-motion/rough-cut@1"

# Above this, a lossy re-encode downstream can push the signal over full
# scale. Below it, a small overshoot of the configured ceiling is harmless.
CLIPPING_RISK_DBTP = -0.5


class ApprovalError(RuntimeError):
    """Raised when the EDL has not been approved by a human."""


def _require_approval(edl: dict, edl_path: Path) -> None:
    approval = edl.get("approval") or {}
    if not approval.get("required", True):
        return
    if approval.get("status") == "approved":
        return

    pending = sum(1 for p in edl.get("proposals", []) if p["status"] == STATUS_REVIEW)
    raise ApprovalError(
        f"The EDL is not approved, so nothing will be cut.\n"
        f"  {edl_path}\n"
        f"  approval.status is {approval.get('status')!r}, and {pending} proposal(s) "
        f"still say 'review'.\n\n"
        "To approve: read review/review-report.md, set each 'review' proposal to\n"
        "'auto' (apply the cut) or 'blocked' (keep the speech), then set\n"
        "approval.status to 'approved' with approvedBy and approvedAt filled in."
    )


def _filtergraph(keep_ranges: list[dict], audio_input: int = 0) -> str:
    """One trim per kept range, video and audio, concatenated in order."""
    parts: list[str] = []
    for index, keep in enumerate(keep_ranges):
        start, end = keep["start"], keep["end"]
        parts.append(
            f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS[v{index}];"
            f"[{audio_input}:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a{index}]"
        )
    streams = "".join(f"[v{i}][a{i}]" for i in range(len(keep_ranges)))
    parts.append(f"{streams}concat=n={len(keep_ranges)}:v=1:a=1[vout][aout]")
    return ";".join(parts)


def run(config: dict, paths: ProjectPaths) -> dict[str, Any]:
    """Apply the approved cuts and write the rough cut."""
    metadata = read_json(paths.metadata)
    edl = read_json(paths.edl)
    _require_approval(edl, paths.edl)

    source = Path(metadata["source"]["path"])
    duration = float(edl.get("durationSeconds") or 0.0)
    profile = cutting_profile(config)

    # From the statuses as they stand now, not from the stored plans.
    plan = _build_plan(edl["proposals"], duration, include_review=False, profile=profile)
    keep_ranges = plan["keepRanges"]

    if not keep_ranges:
        raise ValueError(
            "The approved cuts would remove the entire recording. Nothing was written."
        )

    kept = sum(r["end"] - r["start"] for r in keep_ranges)
    if kept <= 0:
        raise ValueError("The approved keep-ranges are empty. Nothing was written.")

    settings = get(config, "output.roughCut", {})
    paths.ensure()

    # Sound may come from a separate recording, already put on the picture's
    # timeline by ingest. If it does, it is a second input and the cut takes
    # its audio from there.
    sound = audio_source(metadata, source)
    inputs = ["-i", str(source)]
    audio_input = 0
    if sound != source:
        inputs += ["-i", str(sound)]
        audio_input = 1

    media.run(
        [
            str(media.ffmpeg_bin(config)),
            "-hide_banner", "-nostdin", "-y",
            *inputs,
            "-filter_complex", _filtergraph(keep_ranges, audio_input),
            "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264",
            "-preset", str(settings.get("preset", "medium")),
            "-crf", str(settings.get("crf", 18)),
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", str(settings.get("audioBitrate", "192k")),
            "-movflags", "+faststart",
            str(paths.rough_cut),
        ],
        timeout=7200,
    )

    # Levelling comes AFTER cutting, and is measured on the cut rather than on
    # the source. That was checked rather than assumed: removing the pauses
    # from the first real recording moved its integrated loudness by 2.80 LU,
    # so a correction computed from the source would have landed nearly 3 LU
    # off. Video is copied, never re-encoded.
    loudness = get(config, "output.loudness", {})
    before: dict[str, float] | None = None
    after: dict[str, float] | None = None
    if loudness.get("enabled", True):
        before = media.measure_loudness(config, paths.rough_cut)
        levelled = paths.rough_cut.with_name("rough-cut.levelled.mp4")
        media.normalise_loudness(config, paths.rough_cut, levelled, before)
        levelled.replace(paths.rough_cut)
        after = media.measure_loudness(config, paths.rough_cut)

    # Trust the file, not the arithmetic: probe what was actually written.
    probe = media.probe(config, paths.rough_cut)
    actual = float(probe["format"].get("duration") or 0.0)
    video_stream = next(
        (s for s in probe["streams"] if s["codec_type"] == "video"), {}
    )

    warnings = list(plan.get("warnings") or [])

    if after is not None:
        target = float(loudness.get("targetI", -14))
        ceiling = float(loudness.get("truePeak", -1.5))
        if abs(after["input_i"] - target) > 1.0:
            warnings.append(
                f"Levelled to {after['input_i']:.1f} LUFS, {abs(after['input_i'] - target):.1f} "
                f"LU from the {target} LUFS target. Very wide dynamics can stop loudnorm "
                "reaching a target without squashing the speech."
            )
        # loudnorm in linear mode applies one steady gain and limits peaks only
        # approximately, so landing a few tenths above the ceiling is normal and
        # harmless. What is worth a warning is getting close to full scale,
        # where a lossy re-encode downstream can push it over.
        if after["input_tp"] > CLIPPING_RISK_DBTP:
            warnings.append(
                f"True peak is {after['input_tp']:.1f} dBTP, close enough to full scale "
                f"that a re-encode downstream could clip. Lower output.loudness.truePeak."
            )

    drift = abs(actual - kept)
    if drift > 0.5:
        warnings.append(
            f"The rough cut is {actual:.2f}s but the plan expected {kept:.2f}s "
            f"({drift:.2f}s out). Check the cut points before using it."
        )

    payload = {
        "schema": SCHEMA,
        "generatedAt": utc_now(),
        "approvedBy": (edl.get("approval") or {}).get("approvedBy"),
        "approvedAt": (edl.get("approval") or {}).get("approvedAt"),
        "source": metadata["source"],
        "roughCut": str(paths.rough_cut),
        "soundFrom": str(sound),
        "loudness": (
            None
            if before is None or after is None
            else {
                "targetI": loudness.get("targetI", -14),
                "truePeak": loudness.get("truePeak", -1.5),
                "beforeI": rounded(before["input_i"], 2),
                "beforeTruePeak": rounded(before["input_tp"], 2),
                "afterI": rounded(after["input_i"], 2),
                "afterTruePeak": rounded(after["input_tp"], 2),
                "gainApplied": rounded(after["input_i"] - before["input_i"], 2),
            }
        ),
        "sourceDurationSeconds": rounded(duration),
        "expectedDurationSeconds": rounded(kept),
        "actualDurationSeconds": rounded(actual),
        "removedSeconds": rounded(duration - kept),
        "width": video_stream.get("width"),
        "height": video_stream.get("height"),
        "appliedProposalIds": plan["acceptedProposalIds"],
        "keepRanges": keep_ranges,
        "warnings": warnings,
        # Said plainly, because this file is the first thing that looks like a
        # finished product and is not one.
        "note": (
            "Cuts only. No subtitles, no camera moves, no graphics, no audio "
            "cleanup. Those belong to the composition layer."
        ),
    }

    write_json(paths.data / "08-rough-cut.json", payload)
    return payload
