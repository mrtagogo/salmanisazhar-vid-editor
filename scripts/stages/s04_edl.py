"""Stage 4 — editorial analysis and EDL generation.

Produces data/04-edl.json: every proposed change to the timeline, each with a
reason and a status. This is the only stage that makes editorial judgements,
and it makes them as *proposals*. Nothing here cuts video.

The BALANCED standard, expressed concretely:
  * Dead air is shortened, never erased — a trimmed pause always keeps
    `keepPauseSeconds` of air so the delivery still breathes.
  * A pause is only trimmed automatically once it is clearly overlong
    (`autoTrimPauseSeconds`). Everything in between is marked REVIEW.
  * Pauses after a question, and pauses touching Arabic / Qur'anic speech,
    are protected outright.
  * Repetitions and hesitation sounds are proposed, not applied, because a
    repetition can be deliberate emphasis.
  * Low transcription confidence never causes a cut; it raises a note.
"""

from __future__ import annotations

from typing import Any

from ..lib.config import cutting_profile, get
from ..lib.jsonio import read_json, rounded, utc_now, write_json
from ..lib.paths import ProjectPaths
from ..lib.textutil import contains_arabic, is_hesitation, normalize_word

SCHEMA = "tadabbur-motion/edl@1"

# A removal shorter than this is not worth a visible cut.
MIN_REMOVAL_SECONDS = 0.15

STATUS_AUTO = "auto"
STATUS_REVIEW = "review"
STATUS_BLOCKED = "blocked"


def _overlaps(a0: float, a1: float, b0: float, b1: float) -> bool:
    return a0 < b1 and b0 < a1


# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------


def _flatten_words(transcript: dict) -> list[dict[str, Any]]:
    """One flat, time-ordered word list, each word remembering its segment."""
    words: list[dict[str, Any]] = []
    for segment in transcript.get("segments", []):
        for word in segment.get("words", []):
            if word.get("start") is None or word.get("end") is None:
                continue
            words.append(
                {
                    "start": float(word["start"]),
                    "end": float(word["end"]),
                    "word": word.get("word", ""),
                    "probability": word.get("probability"),
                    "lowConfidence": bool(word.get("lowConfidence")),
                    "segmentId": segment.get("id"),
                    "segmentText": segment.get("text", ""),
                }
            )
    words.sort(key=lambda w: w["start"])
    return words


def _protected_regions(transcript: dict, words: list[dict]) -> list[dict[str, Any]]:
    """Spans that may never be cut.

    Arabic and Qur'anic speech is protected because the engine is not allowed
    to alter, shorten or reassemble it. Verification against an approved
    source is a human task and is raised as a note.
    """
    regions: list[dict[str, Any]] = []

    for segment in transcript.get("segments", []):
        text = segment.get("text", "")
        if segment.get("containsArabic") or contains_arabic(text):
            regions.append(
                {
                    "start": float(segment["start"]),
                    "end": float(segment["end"]),
                    "reason": "arabic_or_quranic_speech",
                    "note": (
                        "Arabic script detected. Never cut, and verify the wording "
                        "against an approved mushaf / hadith source before publishing."
                    ),
                    "text": text,
                }
            )

    # Catch Arabic appearing in a single word of an otherwise Latin segment.
    for word in words:
        if contains_arabic(word["word"]) and not any(
            _overlaps(word["start"], word["end"], r["start"], r["end"]) for r in regions
        ):
            regions.append(
                {
                    "start": word["start"],
                    "end": word["end"],
                    "reason": "arabic_or_quranic_speech",
                    "note": "Arabic word detected; verify against an approved source.",
                    "text": word["word"].strip(),
                }
            )

    regions.sort(key=lambda r: r["start"])

    # Merge touching regions so downstream checks stay simple.
    merged: list[dict[str, Any]] = []
    for region in regions:
        if merged and region["start"] <= merged[-1]["end"] + 0.01:
            merged[-1]["end"] = max(merged[-1]["end"], region["end"])
            merged[-1]["text"] = f"{merged[-1]['text']} {region['text']}".strip()
        else:
            merged.append(dict(region))

    for index, region in enumerate(merged, start=1):
        region["id"] = f"prot-{index:03d}"
        region["start"] = rounded(region["start"])
        region["end"] = rounded(region["end"])
        region["durationSeconds"] = rounded(region["end"] - region["start"])

    return merged


# --------------------------------------------------------------------------
# Proposal builders
# --------------------------------------------------------------------------


def _silence_overlap(start: float, end: float, spans: list[dict]) -> float:
    """How much of a word gap is backed by detected acoustic silence."""
    total = 0.0
    for span in spans:
        overlap = min(end, span["end"]) - max(start, span["start"])
        if overlap > 0:
            total += overlap
    return total


def _blocked_pause(
    proposal_id: str,
    gap: dict,
    length: float,
    reasons: list[str],
    corroboration_ratio: float,
) -> dict[str, Any]:
    """A pause that carries meaning: recorded, but never offered as a cut."""
    before = gap["before"]
    return {
        "id": proposal_id,
        "kind": "pause",
        "start": rounded(gap["start"]),
        "end": rounded(gap["end"]),
        "durationSeconds": rounded(length),
        "action": "keep",
        "status": STATUS_BLOCKED,
        "reason": " ".join(reasons),
        "evidence": {
            "position": gap["position"],
            "silenceCorroborationRatio": rounded(corroboration_ratio, 3),
            "precedingWord": before["word"].strip() if before else None,
        },
    }


def _pause_proposals(
    words: list[dict],
    silence_spans: list[dict],
    duration: float,
    profile: dict,
    protected: list[dict],
) -> list[dict[str, Any]]:
    """Propose conservative trims of overlong pauses between words."""
    keep_air = float(profile.get("keepPauseSeconds", 0.6))
    review_at = float(profile.get("reviewPauseSeconds", 1.3))
    auto_at = float(profile.get("autoTrimPauseSeconds", 2.5))
    padding = float(profile.get("edgePaddingSeconds", 0.08))
    protect_question = bool(profile.get("protectPauseAfterQuestion", True))
    protect_adjacent = bool(profile.get("protectPauseBeforeProtectedRegion", True))
    # Tolerance for calling a pause "touching" a protected region.
    adjacency_tolerance = 0.05

    proposals: list[dict[str, Any]] = []

    # Gaps: before the first word, between words, after the last word.
    gaps: list[dict[str, Any]] = []
    if words:
        if words[0]["start"] > 0:
            gaps.append(
                {"start": 0.0, "end": words[0]["start"], "position": "leading",
                 "before": None, "after": words[0]}
            )
        for index in range(len(words) - 1):
            current, following = words[index], words[index + 1]
            if following["start"] > current["end"]:
                gaps.append(
                    {
                        "start": current["end"],
                        "end": following["start"],
                        "position": "interior",
                        "before": current,
                        "after": following,
                    }
                )
        if duration and words[-1]["end"] < duration:
            gaps.append(
                {"start": words[-1]["end"], "end": duration, "position": "trailing",
                 "before": words[-1], "after": None}
            )

    for index, gap in enumerate(gaps, start=1):
        length = gap["end"] - gap["start"]
        if length <= keep_air:
            continue  # Short pause: part of natural delivery, left untouched.

        before = gap["before"]
        corroborated = _silence_overlap(gap["start"], gap["end"], silence_spans)
        corroboration_ratio = corroborated / length if length else 0.0

        status = STATUS_REVIEW
        action = "trim"
        reasons: list[str] = []

        if gap["position"] in ("leading", "trailing"):
            reasons.append(
                f"{gap['position'].capitalize()} dead air of {length:.2f}s "
                "(head/tail slate)."
            )
            status = STATUS_REVIEW  # Where the piece starts and ends is the editor's call.
        elif length >= auto_at:
            reasons.append(
                f"Pause of {length:.2f}s is well beyond the {auto_at:.2f}s "
                "threshold; shortening it keeps the talk moving."
            )
            status = STATUS_AUTO
        elif length >= review_at:
            reasons.append(
                f"Pause of {length:.2f}s may be a thinking pause or dead air; "
                "too close to call automatically."
            )
            status = STATUS_REVIEW
        else:
            continue  # Between keep_air and review_at: deliberately left alone.

        # Rhetorical weight: a pause right after a question is doing work.
        # Only the *last* word of a question counts, so a word in the middle of
        # an interrogative sentence does not protect its own pause.
        after = gap["after"]
        at_segment_end = (
            before is not None
            and (after is None or after["segmentId"] != before["segmentId"])
        )
        if (
            protect_question
            and before is not None
            and (
                before["word"].rstrip().endswith(("?", "؟"))
                or (at_segment_end and before["segmentText"].rstrip().endswith(("?", "؟")))
            )
        ):
            reasons.append(
                "Pause follows a question — treated as rhetorical and protected."
            )
            proposals.append(
                _blocked_pause(
                    f"pause-{index:04d}", gap, length, reasons, corroboration_ratio
                )
            )
            continue

        # Silence touching Qur'anic / Arabic speech is contemplative weight.
        # Trimming it would change how the recitation lands, so it is protected
        # even though the pause itself sits outside the protected region.
        if protect_adjacent:
            touching = [
                r
                for r in protected
                if _overlaps(
                    gap["start"] - adjacency_tolerance,
                    gap["end"] + adjacency_tolerance,
                    r["start"],
                    r["end"],
                )
            ]
            if touching:
                reasons.append(
                    f"Pause touches protected region {touching[0]['id']} "
                    "(Arabic / Qur'anic speech); the silence around it is kept."
                )
                proposals.append(
                    _blocked_pause(
                        f"pause-{index:04d}", gap, length, reasons, corroboration_ratio
                    )
                )
                continue

        # Low corroboration means the "gap" probably contains breath or room
        # tone rather than true silence — never trim that unseen.
        if corroboration_ratio < 0.5:
            reasons.append(
                f"Only {corroboration_ratio * 100:.0f}% of this gap registers as "
                "silence; it may contain breath or quiet speech."
            )
            status = STATUS_REVIEW

        remove_start = gap["start"] + max(keep_air / 2, padding)
        remove_end = gap["end"] - max(keep_air / 2, padding)
        if gap["position"] == "leading":
            # Nothing before it to protect, so only pad the incoming word.
            remove_start = gap["start"]
            remove_end = gap["end"] - max(keep_air, padding)
        elif gap["position"] == "trailing":
            remove_start = gap["start"] + max(keep_air, padding)
            remove_end = gap["end"]

        if remove_end - remove_start < MIN_REMOVAL_SECONDS:
            continue  # Trim would be too small to be worth a cut.

        proposals.append(
            {
                "id": f"pause-{index:04d}",
                "kind": "pause",
                "start": rounded(remove_start),
                "end": rounded(remove_end),
                "durationSeconds": rounded(remove_end - remove_start),
                "action": action,
                "status": status,
                "reason": " ".join(reasons),
                "evidence": {
                    "position": gap["position"],
                    "gapStart": rounded(gap["start"]),
                    "gapEnd": rounded(gap["end"]),
                    "gapSeconds": rounded(length),
                    "airKeptSeconds": rounded(length - (remove_end - remove_start)),
                    "silenceCorroborationRatio": rounded(corroboration_ratio, 3),
                    "precedingWord": before["word"].strip() if before else None,
                },
            }
        )

    return proposals


def _repetition_proposals(
    words: list[dict], protected: list[dict], profile: dict
) -> list[dict[str, Any]]:
    """Find back-to-back repeated word sequences and propose dropping the first.

    Longest sequences are matched first, so a repeated phrase is reported as
    one phrase rather than several single-word stutters.
    """
    settings = profile.get("repetition", {})
    if not settings.get("enabled", True):
        return []

    max_ngram = int(settings.get("maxNgram", 5))
    max_gap = float(settings.get("maxGapSeconds", 0.9))
    auto_stutter = bool(settings.get("autoApproveSingleWordStutter", True))

    normalized = [normalize_word(w["word"]) for w in words]
    consumed: set[int] = set()
    proposals: list[dict[str, Any]] = []
    counter = 0

    for size in range(max_ngram, 0, -1):
        for index in range(len(words) - 2 * size + 1):
            span_a = range(index, index + size)
            span_b = range(index + size, index + 2 * size)
            if any(i in consumed for i in list(span_a) + list(span_b)):
                continue

            first = normalized[index : index + size]
            second = normalized[index + size : index + 2 * size]
            if not all(first) or first != second:
                continue

            # The two occurrences must be adjacent to be a repetition rather
            # than a callback later in the talk.
            gap = words[index + size]["start"] - words[index + size - 1]["end"]
            if gap > max_gap:
                continue

            remove_start = words[index]["start"]
            remove_end = words[index + size]["start"]
            if remove_end - remove_start < MIN_REMOVAL_SECONDS:
                continue

            phrase = " ".join(w["word"].strip() for w in words[index : index + size])

            if any(
                _overlaps(remove_start, remove_end, r["start"], r["end"])
                for r in protected
            ):
                continue  # Repetition inside Arabic speech is never touched.

            counter += 1
            single_stutter = size == 1 and gap <= 0.35
            proposals.append(
                {
                    "id": f"rep-{counter:04d}",
                    "kind": "repetition",
                    "start": rounded(remove_start),
                    "end": rounded(remove_end),
                    "durationSeconds": rounded(remove_end - remove_start),
                    "action": "cut",
                    "status": STATUS_AUTO if (single_stutter and auto_stutter) else STATUS_REVIEW,
                    "reason": (
                        f"'{phrase}' is said twice back to back"
                        + (
                            " — a clear stutter; the first attempt is dropped."
                            if single_stutter and auto_stutter
                            else " — may be deliberate emphasis, so it needs a decision."
                        )
                    ),
                    "evidence": {
                        "phrase": phrase,
                        "ngramSize": size,
                        "gapSeconds": rounded(gap),
                        "keptOccurrence": {
                            "start": rounded(words[index + size]["start"]),
                            "end": rounded(words[index + 2 * size - 1]["end"]),
                        },
                    },
                }
            )
            consumed.update(span_a)
            consumed.update(span_b)

    proposals.sort(key=lambda p: p["start"])
    return proposals


def _hesitation_proposals(
    words: list[dict], protected: list[dict], profile: dict
) -> list[dict[str, Any]]:
    """Propose removing isolated hesitation sounds ('eee', 'emm')."""
    settings = profile.get("fillers", {})
    if not settings.get("enabled", True):
        return []

    # Config may force these to review; they are never auto-approved here
    # because removing a filler mid-sentence can produce an audible jump.
    status = STATUS_REVIEW if settings.get("action", "review") == "review" else STATUS_AUTO

    proposals: list[dict[str, Any]] = []
    counter = 0

    for word in words:
        if not is_hesitation(word["word"]):
            continue
        if word["end"] - word["start"] < MIN_REMOVAL_SECONDS:
            continue
        if any(
            _overlaps(word["start"], word["end"], r["start"], r["end"]) for r in protected
        ):
            continue

        counter += 1
        proposals.append(
            {
                "id": f"fill-{counter:04d}",
                "kind": "hesitation",
                "start": rounded(word["start"]),
                "end": rounded(word["end"]),
                "durationSeconds": rounded(word["end"] - word["start"]),
                "action": "cut",
                "status": status,
                "reason": (
                    f"Hesitation sound '{word['word'].strip()}'. Removing it tightens "
                    "the line, but check the cut does not clip the next word."
                ),
                "evidence": {"word": word["word"].strip(), "probability": word["probability"]},
            }
        )

    return proposals


def _speech_notes(transcript: dict, words: list[dict], config: dict) -> list[dict[str, Any]]:
    """Problems the editor should hear for themselves. These never cause cuts."""
    notes: list[dict[str, Any]] = []
    logprob_floor = float(
        get(config, "analysis.transcription.lowConfidenceSegmentLogprob", -0.85)
    )

    for segment in transcript.get("segments", []):
        if segment.get("avgLogprob") is not None and segment["avgLogprob"] < logprob_floor:
            notes.append(
                {
                    "kind": "uncertain_transcription",
                    "start": segment["start"],
                    "end": segment["end"],
                    "detail": (
                        f"Whisper confidence is low (avgLogprob {segment['avgLogprob']}). "
                        "Check this line by ear before trusting the subtitle."
                    ),
                    "text": segment.get("text", ""),
                }
            )
        if segment.get("containsArabic"):
            notes.append(
                {
                    "kind": "arabic_needs_verification",
                    "start": segment["start"],
                    "end": segment["end"],
                    "detail": (
                        "Arabic text must be verified against an approved source; "
                        "the engine will not generate or correct it."
                    ),
                    "text": segment.get("text", ""),
                }
            )

    low_confidence = [w for w in words if w["lowConfidence"]]
    for word in low_confidence:
        notes.append(
            {
                "kind": "low_confidence_word",
                "start": rounded(word["start"]),
                "end": rounded(word["end"]),
                "detail": (
                    f"Word '{word['word'].strip()}' transcribed with probability "
                    f"{word['probability']}. Fix the subtitle text if it is wrong."
                ),
                "text": word["word"].strip(),
            }
        )

    notes.sort(key=lambda n: n["start"])
    return notes


# --------------------------------------------------------------------------
# Plan assembly
# --------------------------------------------------------------------------


def _clip_against_protected(
    proposals: list[dict], protected: list[dict]
) -> list[dict[str, Any]]:
    """Remove or shrink any proposal that reaches into protected speech."""
    resolved: list[dict[str, Any]] = []

    for proposal in proposals:
        if proposal["action"] == "keep":
            resolved.append(proposal)
            continue

        start, end = proposal["start"], proposal["end"]
        blocking = [
            r for r in protected if _overlaps(start, end, r["start"], r["end"])
        ]
        if not blocking:
            resolved.append(proposal)
            continue

        # Keep only the part of the removal that lies before the first
        # protected region and after the last one, whichever survives.
        candidates: list[tuple[float, float]] = []
        first, last = blocking[0], blocking[-1]
        if start < first["start"]:
            candidates.append((start, first["start"]))
        if end > last["end"]:
            candidates.append((last["end"], end))

        usable = [
            (a, b) for a, b in candidates if b - a >= MIN_REMOVAL_SECONDS
        ]
        if not usable:
            blocked = dict(proposal)
            blocked["action"] = "keep"
            blocked["status"] = STATUS_BLOCKED
            blocked["reason"] = (
                proposal["reason"]
                + f" Blocked: overlaps protected region {first['id']}."
            )
            resolved.append(blocked)
            continue

        for order, (a, b) in enumerate(usable, start=1):
            clipped = dict(proposal)
            clipped["id"] = f"{proposal['id']}-{order}"
            clipped["start"] = rounded(a)
            clipped["end"] = rounded(b)
            clipped["durationSeconds"] = rounded(b - a)
            clipped["status"] = STATUS_REVIEW
            clipped["reason"] = (
                proposal["reason"]
                + f" Clipped to avoid protected region {first['id']}."
            )
            resolved.append(clipped)

    resolved.sort(key=lambda p: p["start"])
    return resolved


def _build_plan(
    proposals: list[dict], duration: float, include_review: bool, profile: dict
) -> dict[str, Any]:
    """Turn accepted proposals into keep ranges over the full duration."""
    min_kept = float(profile.get("minKeptSegmentSeconds", 0.4))

    accepted = [
        p
        for p in proposals
        if p["action"] in ("cut", "trim")
        and (p["status"] == STATUS_AUTO or (include_review and p["status"] == STATUS_REVIEW))
    ]

    # Merge overlapping removals.
    merged: list[list[float]] = []
    for proposal in sorted(accepted, key=lambda p: p["start"]):
        if merged and proposal["start"] <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], proposal["end"])
        else:
            merged.append([proposal["start"], proposal["end"]])

    keep_ranges: list[dict[str, float]] = []
    cursor = 0.0
    for removal_start, removal_end in merged:
        if removal_start > cursor:
            keep_ranges.append({"start": rounded(cursor), "end": rounded(removal_start)})
        cursor = max(cursor, removal_end)
    if duration > cursor:
        keep_ranges.append({"start": rounded(cursor), "end": rounded(duration)})

    short_keeps = [
        r for r in keep_ranges if r["end"] - r["start"] < min_kept
    ]
    removed = sum(end - start for start, end in merged)

    return {
        "includesReviewProposals": include_review,
        "acceptedProposalIds": [p["id"] for p in accepted],
        "keepRanges": keep_ranges,
        "removedSeconds": rounded(removed),
        "resultDurationSeconds": rounded(max(0.0, duration - removed)),
        "warnings": (
            [
                f"{len(short_keeps)} kept segment(s) would be shorter than "
                f"{min_kept}s, which reads as a glitch. Review these before applying."
            ]
            if short_keeps
            else []
        ),
        "shortKeptSegments": short_keeps,
    }


def _timeline(proposals: list[dict], duration: float) -> list[dict[str, Any]]:
    """Contiguous keep/remove blocks covering [0, duration]."""
    marks = [
        p for p in proposals if p["action"] in ("cut", "trim")
    ]
    blocks: list[dict[str, Any]] = []
    cursor = 0.0

    for proposal in sorted(marks, key=lambda p: p["start"]):
        if proposal["start"] > cursor:
            blocks.append(
                {"start": rounded(cursor), "end": rounded(proposal["start"]), "state": "keep"}
            )
        if proposal["end"] > cursor:
            blocks.append(
                {
                    "start": rounded(max(cursor, proposal["start"])),
                    "end": rounded(proposal["end"]),
                    "state": "remove",
                    "proposalId": proposal["id"],
                    "status": proposal["status"],
                    "kind": proposal["kind"],
                }
            )
            cursor = proposal["end"]

    if duration > cursor:
        blocks.append({"start": rounded(cursor), "end": rounded(duration), "state": "keep"})

    for index, block in enumerate(blocks, start=1):
        block["index"] = index
        block["durationSeconds"] = rounded(block["end"] - block["start"])

    return blocks


def run(config: dict, paths: ProjectPaths) -> dict[str, Any]:
    """Generate the EDL from the metadata, transcript and silence artefacts."""
    metadata = read_json(paths.metadata)
    transcript = read_json(paths.transcript)
    silence = read_json(paths.silence)

    duration = float(metadata["container"].get("durationSeconds") or 0.0)
    profile = cutting_profile(config)
    standard = get(config, "editingIdentity.cutting", "balanced")

    words = _flatten_words(transcript)
    protected = _protected_regions(transcript, words)
    silence_spans = silence.get("spans", [])

    raw_proposals = (
        _pause_proposals(words, silence_spans, duration, profile, protected)
        + _repetition_proposals(words, protected, profile)
        + _hesitation_proposals(words, protected, profile)
    )
    proposals = _clip_against_protected(raw_proposals, protected)

    plan_auto = _build_plan(proposals, duration, include_review=False, profile=profile)
    plan_all = _build_plan(proposals, duration, include_review=True, profile=profile)

    review_queue = [
        {
            "id": p["id"],
            "kind": p["kind"],
            "start": p["start"],
            "end": p["end"],
            "durationSeconds": p["durationSeconds"],
            "action": p["action"],
            "reason": p["reason"],
        }
        for p in proposals
        if p["status"] == STATUS_REVIEW
    ]

    by_kind: dict[str, dict[str, int]] = {}
    for proposal in proposals:
        bucket = by_kind.setdefault(
            proposal["kind"], {STATUS_AUTO: 0, STATUS_REVIEW: 0, STATUS_BLOCKED: 0}
        )
        bucket[proposal["status"]] += 1

    payload = {
        "schema": SCHEMA,
        "generatedAt": utc_now(),
        "standard": {
            "cutting": standard,
            "subtitles": get(config, "editingIdentity.subtitles"),
            "camera": get(config, "editingIdentity.camera"),
            "audio": get(config, "editingIdentity.audio"),
            "parameters": profile,
        },
        "source": metadata["source"],
        "durationSeconds": rounded(duration),
        "approval": {
            "required": bool(get(config, "review.requireApprovalBeforeCutting", True)),
            "status": "pending",
            "approvedAt": None,
            "approvedBy": None,
            "note": (
                "No cutting stage may read this file while status is 'pending'. "
                "Set status to 'approved' only after a human has reviewed "
                "review/review-report.md."
            ),
        },
        "protectedRegions": protected,
        "proposals": proposals,
        "timeline": _timeline(proposals, duration),
        "plans": {"autoApprovedOnly": plan_auto, "allProposals": plan_all},
        "reviewQueue": review_queue,
        "speechNotes": _speech_notes(transcript, words, config),
        "stats": {
            "wordCount": len(words),
            "proposalCount": len(proposals),
            "autoApproved": sum(1 for p in proposals if p["status"] == STATUS_AUTO),
            "needsReview": len(review_queue),
            "blocked": sum(1 for p in proposals if p["status"] == STATUS_BLOCKED),
            "protectedRegionCount": len(protected),
            "protectedSeconds": rounded(
                sum(r["durationSeconds"] for r in protected)
            ),
            "byKind": by_kind,
        },
    }

    paths.ensure()
    write_json(paths.edl, payload)
    return payload
