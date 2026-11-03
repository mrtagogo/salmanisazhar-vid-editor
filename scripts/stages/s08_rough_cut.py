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
from ..lib.paths import ProjectPaths
from .s04_edl import STATUS_AUTO, STATUS_REVIEW, _build_plan, cutting_profile

SCHEMA = "tadabbur-motion/rough-cut@1"


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


def _filtergraph(keep_ranges: list[dict]) -> str:
    """One trim per kept range, video and audio, concatenated in order."""
    parts: list[str] = []
    for index, keep in enumerate(keep_ranges):
        start, end = keep["start"], keep["end"]
        parts.append(
            f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS[v{index}];"
            f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a{index}]"
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

    media.run(
        [
            str(media.ffmpeg_bin(config)),
            "-hide_banner", "-nostdin", "-y",
            "-i", str(source),
            "-filter_complex", _filtergraph(keep_ranges),
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

    # Trust the file, not the arithmetic: probe what was actually written.
    probe = media.probe(config, paths.rough_cut)
    actual = float(probe["format"].get("duration") or 0.0)
    video_stream = next(
        (s for s in probe["streams"] if s["codec_type"] == "video"), {}
    )

    warnings = list(plan.get("warnings") or [])
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
