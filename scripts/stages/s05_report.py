"""Stage 5 — human review report.

Produces review/review-report.md. This is the approval checkpoint: the
pipeline stops here until a person has read it and marked the EDL approved.
"""

from __future__ import annotations

from typing import Any

from ..lib.jsonio import read_json, rounded
from ..lib.paths import ProjectPaths


def _clock(seconds: float | None) -> str:
    """Format seconds as mm:ss.mmm for scrubbing against a timeline."""
    if seconds is None:
        return "–"
    total = max(0.0, float(seconds))
    minutes = int(total // 60)
    rest = total - minutes * 60
    return f"{minutes:02d}:{rest:06.3f}"


def _bullet_list(items: list[str], empty: str) -> str:
    return "\n".join(f"- {item}" for item in items) if items else f"_{empty}_"


def _proposal_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "_None._"
    lines = [
        "| ID | At | Length | Kind | Action | Why |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        reason = row["reason"].replace("|", "\\|")
        lines.append(
            f"| `{row['id']}` | {_clock(row['start'])} | "
            f"{row['durationSeconds']:.2f}s | {row['kind']} | {row['action']} | {reason} |"
        )
    return "\n".join(lines)


def build(paths: ProjectPaths) -> str:
    """Render the report from the four analysis artefacts."""
    metadata = read_json(paths.metadata)
    transcript = read_json(paths.transcript)
    silence = read_json(paths.silence)
    edl = read_json(paths.edl)

    validation = metadata["validation"]
    video = metadata.get("video") or {}
    audio = metadata.get("audio") or {}
    duration = metadata["container"].get("durationSeconds") or 0.0

    t_stats = transcript["stats"]
    s_stats = silence["stats"]
    e_stats = edl["stats"]
    plan_auto = edl["plans"]["autoApprovedOnly"]
    plan_all = edl["plans"]["allProposals"]

    auto_rows = [p for p in edl["proposals"] if p["status"] == "auto"]
    review_rows = [p for p in edl["proposals"] if p["status"] == "review"]
    blocked_rows = [p for p in edl["proposals"] if p["status"] == "blocked"]

    notes_by_kind: dict[str, list[dict]] = {}
    for note in edl["speechNotes"]:
        notes_by_kind.setdefault(note["kind"], []).append(note)

    def saved(plan: dict) -> str:
        removed = plan["removedSeconds"]
        share = (removed / duration * 100) if duration else 0.0
        return (
            f"{removed:.2f}s removed ({share:.1f}%) → "
            f"{plan['resultDurationSeconds']:.2f}s"
        )

    lines: list[str] = []
    add = lines.append

    add(f"# Review report — {paths.slug}")
    add("")
    add(f"- **Source:** `{metadata['source']['filename']}`")
    add(f"- **Duration:** {_clock(duration)} ({duration:.2f}s)")
    add(f"- **Editing standard:** cutting `{edl['standard']['cutting']}`, "
        f"subtitles `{edl['standard']['subtitles']}`, "
        f"camera `{edl['standard']['camera']}`, audio `{edl['standard']['audio']}`")
    add(f"- **Analysed:** {edl['generatedAt']}")
    add("")
    add("> **Approval checkpoint.** Nothing has been cut. No rendering or cutting "
        "stage may run until `approval.status` in `data/04-edl.json` is set to "
        "`approved` by a human.")
    add("")

    # ---------------- Stage 1 ----------------
    add("## 1. Input validation")
    add("")
    add(f"**Status:** {'PASSED' if validation['ok'] else 'FAILED'}")
    add("")
    add("**Errors**")
    add("")
    add(_bullet_list(validation["errors"], "No blocking problems."))
    add("")
    add("**Warnings**")
    add("")
    add(_bullet_list(validation["warnings"], "No warnings."))
    add("")
    add(
        f"Picture: {video.get('width')}x{video.get('height')} "
        f"{video.get('orientation') or '?'}, {video.get('codec')}, "
        f"{video.get('avgFrameRate')} fps, rotation {video.get('rotationDegrees')}°. "
        f"Sound: {audio.get('codec')}, {audio.get('sampleRate')} Hz, "
        f"{audio.get('channels')} ch."
    )
    add("")

    # ---------------- Stage 2 ----------------
    add("## 2. Transcription")
    add("")
    add(
        f"- Model `{transcript['engine']['model']}` on "
        f"`{transcript['engine']['device']}` / `{transcript['engine']['computeType']}`"
    )
    add(
        f"- Detected language: `{transcript['detectedLanguage']['code']}` "
        f"(p={transcript['detectedLanguage']['probability']}), "
        f"requested `{transcript['engine']['requestedLanguage']}`"
    )
    add(
        f"- {t_stats['wordCount']} words in {t_stats['segmentCount']} segments, "
        f"{t_stats['speechSeconds']:.2f}s of speech "
        f"({(t_stats['speechRatio'] or 0) * 100:.1f}% of runtime), "
        f"{t_stats['wordsPerMinute']} wpm"
    )
    add(
        f"- Low-confidence words: {t_stats['lowConfidenceWords']}; "
        f"segments containing Arabic: {t_stats['segmentsContainingArabic']}"
    )
    if transcript["engine"]["runtimeNotes"]:
        add("")
        add("**Runtime notes**")
        add("")
        add(_bullet_list(transcript["engine"]["runtimeNotes"], ""))
    add("")

    # ---------------- Stage 3 ----------------
    add("## 3. Silence")
    add("")
    add(
        f"- {s_stats['spanCount']} silent spans, {s_stats['silentSeconds']:.2f}s total "
        f"({(s_stats['silentRatio'] or 0) * 100:.1f}% of runtime)"
    )
    add(f"- Longest single silence: {s_stats['longestSilenceSeconds']:.2f}s")
    add(
        f"- Detector: `silencedetect` at {silence['detector']['noiseFloorDb']} dB, "
        f"min {silence['detector']['minSilenceSeconds']}s"
    )
    add("")
    add("_Acoustic measurement only. Which of these is dead air and which is a "
        "deliberate pause is decided below, not here._")
    add("")

    # ---------------- Stage 4 ----------------
    add("## 4. Edit proposals")
    add("")
    add(
        f"{e_stats['proposalCount']} proposals: "
        f"**{e_stats['autoApproved']} auto**, "
        f"**{e_stats['needsReview']} need review**, "
        f"**{e_stats['blocked']} refused** as meaningful silence or protected speech."
    )
    add("")
    add(f"- Apply auto only: {saved(plan_auto)}")
    add(f"- Apply everything: {saved(plan_all)}")
    # Both plans can raise the same warning; show it once.
    for warning in dict.fromkeys(plan_auto["warnings"] + plan_all["warnings"]):
        add(f"- ⚠️ {warning}")
    add("")

    add("### 4a. Auto-approved")
    add("")
    add("_Conservative changes the BALANCED standard allows without a decision: "
        "clearly overlong dead air (air is shortened, never erased) and plain "
        "single-word stutters._")
    add("")
    add(_proposal_table(auto_rows))
    add("")

    add("### 4b. Needs your decision (REVIEW)")
    add("")
    add("_Each of these is genuinely ambiguous. Nothing here is applied until you "
        "say so._")
    add("")
    add(_proposal_table(review_rows))
    add("")

    if blocked_rows:
        add("### 4c. Refused by the engine")
        add("")
        add("_Cuts the engine considered and then refused: the silence carries "
            "meaning (a pause after a question, or silence around Arabic "
            "recitation), or the span touches protected speech. Listed so the "
            "reasoning is visible, not so it can be applied._")
        add("")
        add(_proposal_table(blocked_rows))
        add("")

    # ---------------- Protected ----------------
    add("## 5. Protected regions")
    add("")
    if edl["protectedRegions"]:
        add(
            f"{e_stats['protectedRegionCount']} region(s), "
            f"{e_stats['protectedSeconds']:.2f}s total. These are never cut."
        )
        add("")
        add("| ID | From | To | Reason | Text |")
        add("| --- | --- | --- | --- | --- |")
        for region in edl["protectedRegions"]:
            text = region["text"].replace("|", "\\|")[:120]
            add(
                f"| `{region['id']}` | {_clock(region['start'])} | "
                f"{_clock(region['end'])} | {region['reason']} | {text} |"
            )
        add("")
        add("**Arabic and Qur'anic wording must be checked against an approved "
            "source by hand.** The engine does not generate, correct or complete it.")
    else:
        add("_No Arabic or Qur'anic speech detected._")
    add("")

    # ---------------- Speech notes ----------------
    add("## 6. Speech and transcription notes")
    add("")
    add("_These never cause a cut. They are things to listen to and fix in the "
        "subtitle text._")
    add("")
    if notes_by_kind:
        for kind, notes in notes_by_kind.items():
            add(f"**{kind}** ({len(notes)})")
            add("")
            for note in notes[:25]:
                add(f"- `{_clock(note['start'])}` {note['detail']}")
            if len(notes) > 25:
                add(f"- _…and {len(notes) - 25} more; see `speechNotes` in the EDL._")
            add("")
    else:
        add("_No issues raised._")
    add("")

    # ---------------- Next step ----------------
    add("## 7. How to approve")
    add("")
    add("1. Scrub the timestamps above against the source video.")
    add("2. For each REVIEW row, decide keep or cut.")
    add("3. Record the decision in `data/04-edl.json`: set each proposal's "
        "`status` to `auto` (apply) or `blocked` (keep).")
    add("4. Set `approval.status` to `approved` and fill in `approvedBy` "
        "and `approvedAt`.")
    add("")
    add("Only then may the cutting stage run.")
    add("")

    return "\n".join(lines) + "\n"


def run(config: dict, paths: ProjectPaths) -> dict[str, Any]:
    """Write the review report and return a small summary."""
    markdown = build(paths)
    paths.ensure()
    paths.review_report.write_text(markdown, encoding="utf-8")

    edl = read_json(paths.edl)
    return {
        "reportPath": str(paths.review_report),
        "characters": len(markdown),
        "needsReview": edl["stats"]["needsReview"],
        "autoApproved": edl["stats"]["autoApproved"],
        "approvalStatus": edl["approval"]["status"],
    }
