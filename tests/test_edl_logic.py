"""Deterministic checks on the editorial reasoning in stage 4.

Run from the engine root:

    python -m tests.test_edl_logic

These tests use a hand-built Indonesian transcript (including an Arabic
segment) instead of real audio, so the editorial rules can be verified exactly
without depending on transcription quality. No dependencies beyond the
standard library.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from scripts.lib.config import load_config
from scripts.lib.jsonio import write_json
from scripts.lib.paths import ProjectPaths
from scripts.stages import s04_edl, s05_report

DURATION = 32.0

# A transcript laid out so that every editorial rule has exactly one case.
SEGMENTS = [
    # Normal speech, then a 4.2 s dead-air gap -> should be trimmed automatically.
    (0, 1.0, 3.0, "Hari ini kita bahas tiga hal.", False, [
        ("Hari", 1.0, 1.3), ("ini", 1.35, 1.6), ("kita", 1.65, 1.95),
        ("bahas", 2.0, 2.35), ("tiga", 2.4, 2.7), ("hal.", 2.75, 3.0),
    ]),
    (1, 7.2, 9.0, "Yang pertama adalah niat.", False, [
        ("Yang", 7.2, 7.5), ("pertama", 7.55, 8.1), ("adalah", 8.15, 8.6),
        ("niat.", 8.65, 9.0),
    ]),
    # Single-word stutter -> auto-approved.
    (2, 9.2, 10.6, "niat niat itu penting.", False, [
        ("niat", 9.2, 9.5), ("niat", 9.55, 9.9), ("itu", 9.95, 10.2),
        ("penting.", 10.25, 10.6),
    ]),
    # Hesitation sound -> proposed, but review only.
    (3, 11.0, 12.4, "Eee, kita lanjutkan.", False, [
        ("Eee,", 11.0, 11.5), ("kita", 11.55, 11.8), ("lanjutkan.", 11.85, 12.4),
    ]),
    # Question, then a 3.6 s pause -> rhetorical, must be blocked.
    (4, 12.6, 13.9, "Apakah antum paham?", False, [
        ("Apakah", 12.6, 13.0), ("antum", 13.05, 13.4), ("paham?", 13.45, 13.9),
    ]),
    # Arabic -> protected region; the 3.5 s pause after it must be blocked too.
    (5, 17.5, 20.5, "إِنَّ مَعَ الْعُسْرِ يُسْرًا", True, [
        ("إِنَّ", 17.5, 18.1), ("مَعَ", 18.2, 18.7),
        ("الْعُسْرِ", 18.8, 19.6), ("يُسْرًا", 19.7, 20.5),
    ]),
    # Three-word phrase said twice -> review, not auto.
    (6, 24.0, 27.1, "Itu pelajaran pertama. Itu pelajaran pertama.", False, [
        ("Itu", 24.0, 24.3), ("pelajaran", 24.35, 24.9), ("pertama.", 24.95, 25.5),
        ("Itu", 25.6, 25.9), ("pelajaran", 25.95, 26.5), ("pertama.", 26.55, 27.1),
    ]),
    (7, 28.0, 28.6, "Sekian.", False, [("Sekian.", 28.0, 28.6)]),
]

# Acoustic silence backing the long gaps, so corroboration passes.
SILENCE_SPANS = [
    (0.0, 1.0), (3.05, 7.15), (13.95, 17.45), (20.55, 23.95), (28.65, 32.0),
]

LOW_CONFIDENCE_WORD = "Sekian."


def _build_artefacts(paths: ProjectPaths) -> None:
    paths.ensure()

    write_json(paths.metadata, {
        "schema": "tadabbur-motion/metadata@1",
        "generatedAt": "1970-01-01T00:00:00Z",
        "source": {
            "path": str(paths.root / "fixture.mp4"),
            "filename": "fixture.mp4",
            "sizeBytes": 1,
            "projectSlug": paths.slug,
        },
        "container": {"formatName": "mp4", "durationSeconds": DURATION,
                      "bitRate": "1", "streamCount": 2},
        "video": {"width": 1920, "height": 1080, "orientation": "landscape",
                  "codec": "h264", "avgFrameRate": 30.0, "rotationDegrees": 0},
        "audio": {"codec": "aac", "sampleRate": 48000, "channels": 2},
        "validation": {"ok": True, "errors": [], "warnings": []},
        "ffprobe": {},
    })

    segments = []
    for seg_id, start, end, text, arabic, words in SEGMENTS:
        word_entries = []
        for word, w_start, w_end in words:
            probability = 0.31 if word == LOW_CONFIDENCE_WORD else 0.95
            word_entries.append({
                "start": w_start, "end": w_end, "word": word,
                "probability": probability,
                "lowConfidence": probability < 0.55,
            })
        segments.append({
            "id": seg_id, "start": start, "end": end, "text": text,
            "avgLogprob": -0.2, "noSpeechProb": 0.01, "compressionRatio": 1.4,
            "containsArabic": arabic, "words": word_entries,
        })

    write_json(paths.transcript, {
        "schema": "tadabbur-motion/transcript@1",
        "generatedAt": "1970-01-01T00:00:00Z",
        "engine": {"library": "fixture", "libraryVersion": "0",
                   "model": "fixture", "device": "cpu", "computeType": "int8",
                   "beamSize": 5, "vadFilter": True, "requestedLanguage": "id",
                   "runtimeNotes": []},
        "detectedLanguage": {"code": "id", "probability": 0.99},
        "durationSeconds": DURATION,
        "stats": {"segmentCount": len(segments),
                  "wordCount": sum(len(s["words"]) for s in segments),
                  "speechSeconds": 16.0, "speechRatio": 0.5,
                  "wordsPerMinute": 120.0, "lowConfidenceWords": 1,
                  "segmentsContainingArabic": 1},
        "segments": segments,
    })

    write_json(paths.silence, {
        "schema": "tadabbur-motion/silence@1",
        "generatedAt": "1970-01-01T00:00:00Z",
        "detector": {"filter": "fixture", "noiseFloorDb": -32,
                     "minSilenceSeconds": 0.3, "audioFile": "fixture.wav"},
        "durationSeconds": DURATION,
        "stats": {"spanCount": len(SILENCE_SPANS), "silentSeconds": 15.0,
                  "silentRatio": 0.47, "longestSilenceSeconds": 4.1},
        "spans": [
            {"id": f"sil-{i:04d}", "start": s, "end": e,
             "durationSeconds": round(e - s, 3),
             "position": "leading" if s <= 0.05 else "trailing" if e >= DURATION - 0.05 else "interior"}
            for i, (s, e) in enumerate(SILENCE_SPANS, start=1)
        ],
    })


# --------------------------------------------------------------------------

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


def _at(proposals: list[dict], start: float, tolerance: float = 0.3) -> list[dict]:
    """Proposals whose removal begins near a given time."""
    return [p for p in proposals if abs(p["start"] - start) <= tolerance]


def main() -> int:
    config = load_config()

    with tempfile.TemporaryDirectory(prefix="tadabbur-test-") as tmp:
        root = Path(tmp) / "fixture"
        paths = ProjectPaths(
            slug="fixture", root=root, data=root / "data",
            cache=root / "cache", review=root / "review",
        )
        _build_artefacts(paths)

        edl = s04_edl.run(config, paths)
        proposals = edl["proposals"]
        protected = edl["protectedRegions"]
        profile = edl["standard"]["parameters"]
        keep_air = profile["keepPauseSeconds"]

        print("\nProtected speech")
        check("Arabic segment becomes a protected region", len(protected) == 1,
              f"got {len(protected)}")
        if protected:
            region = protected[0]
            check("protected region covers the whole recitation",
                  abs(region["start"] - 17.5) < 0.01 and abs(region["end"] - 20.5) < 0.01,
                  f"{region['start']}–{region['end']}")
        check("no cut or trim overlaps protected speech",
              not any(
                  p["action"] in ("cut", "trim")
                  and any(r["start"] < p["end"] and p["start"] < r["end"] for r in protected)
                  for p in proposals
              ))

        print("\nPauses")
        long_gap = _at(proposals, 3.0, tolerance=0.5)
        check("4.2s dead air is proposed for trimming", len(long_gap) == 1,
              f"got {len(long_gap)}")
        if long_gap:
            pause = long_gap[0]
            check("overlong dead air is auto-approved", pause["status"] == "auto",
                  pause["status"])
            check("trim shortens rather than erases the pause",
                  abs(pause["evidence"]["airKeptSeconds"] - keep_air) < 0.02,
                  f"kept {pause['evidence']['airKeptSeconds']}s, expected {keep_air}s")

        after_question = [
            p for p in proposals
            if p["kind"] == "pause" and abs(p["start"] - 13.9) < 0.1
        ]
        check("pause after a question is blocked",
              len(after_question) == 1 and after_question[0]["status"] == "blocked",
              str([(p["start"], p["status"]) for p in after_question]))

        after_arabic = [
            p for p in proposals
            if p["kind"] == "pause" and abs(p["start"] - 20.5) < 0.1
        ]
        check("pause touching Arabic speech is blocked",
              len(after_arabic) == 1 and after_arabic[0]["status"] == "blocked",
              str([(p["start"], p["status"]) for p in after_arabic]))

        check("0.9s pause between sentences is left alone",
              not _at(proposals, 27.1, tolerance=0.4))

        leading = [p for p in proposals if p.get("evidence", {}).get("position") == "leading"]
        trailing = [p for p in proposals if p.get("evidence", {}).get("position") == "trailing"]
        check("head dead air is proposed for review",
              len(leading) == 1 and leading[0]["status"] == "review")
        check("tail dead air is proposed for review",
              len(trailing) == 1 and trailing[0]["status"] == "review")

        print("\nRepetition and hesitation")
        repetitions = [p for p in proposals if p["kind"] == "repetition"]
        stutter = [p for p in repetitions if p["evidence"]["ngramSize"] == 1]
        phrase = [p for p in repetitions if p["evidence"]["ngramSize"] == 3]
        check("single-word stutter is found", len(stutter) == 1, f"got {len(stutter)}")
        check("stutter is auto-approved",
              bool(stutter) and stutter[0]["status"] == "auto")
        check("repeated three-word phrase is found as one phrase",
              len(phrase) == 1, f"got {len(phrase)}")
        check("repeated phrase needs review, not auto",
              bool(phrase) and phrase[0]["status"] == "review")
        check("repetition keeps the second occurrence",
              bool(phrase) and abs(phrase[0]["end"] - 25.6) < 0.01,
              str(phrase[0]["end"]) if phrase else "none")

        hesitations = [p for p in proposals if p["kind"] == "hesitation"]
        check("hesitation sound is found", len(hesitations) == 1, f"got {len(hesitations)}")
        check("hesitation is never auto-approved",
              all(p["status"] != "auto" for p in hesitations))

        print("\nPlans")
        auto_plan = edl["plans"]["autoApprovedOnly"]
        all_plan = edl["plans"]["allProposals"]
        check("applying everything removes more than auto alone",
              all_plan["removedSeconds"] > auto_plan["removedSeconds"],
              f"{all_plan['removedSeconds']} vs {auto_plan['removedSeconds']}")
        check("auto plan never removes protected or question pauses",
              auto_plan["removedSeconds"] < 6.0, f"{auto_plan['removedSeconds']}s")

        for name, plan in (("auto", auto_plan), ("all", all_plan)):
            ranges = plan["keepRanges"]
            ordered = all(
                ranges[i]["end"] <= ranges[i + 1]["start"] + 1e-6
                for i in range(len(ranges) - 1)
            )
            check(f"{name} plan keep-ranges are ordered and disjoint", ordered)
            check(f"{name} plan stays inside the source duration",
                  all(0 <= r["start"] < r["end"] <= DURATION + 1e-6 for r in ranges))
            check(f"{name} plan arithmetic is consistent",
                  abs(sum(r["end"] - r["start"] for r in ranges)
                      - plan["resultDurationSeconds"]) < 0.02,
                  f"{sum(r['end'] - r['start'] for r in ranges)} vs "
                  f"{plan['resultDurationSeconds']}")

        print("\nApproval and notes")
        check("approval starts pending", edl["approval"]["status"] == "pending")
        check("approval is required by config", edl["approval"]["required"] is True)
        kinds = {n["kind"] for n in edl["speechNotes"]}
        check("low-confidence word raises a note", "low_confidence_word" in kinds)
        check("Arabic raises a verification note", "arabic_needs_verification" in kinds)
        check("notes never carry an action",
              all("action" not in n for n in edl["speechNotes"]))

        print("\nReview report")
        summary = s05_report.run(config, paths)
        markdown = paths.review_report.read_text(encoding="utf-8")
        check("report is written", paths.review_report.exists())
        check("report states nothing has been cut", "Nothing has been cut" in markdown)
        check("report lists the review queue",
              "Needs your decision" in markdown)
        check("report counts match the EDL",
              summary["needsReview"] == edl["stats"]["needsReview"])

    print(f"\n{_checks - len(_failures)}/{_checks} checks passed")
    if _failures:
        print("\nFailed:")
        for failure in _failures:
            print(f"  - {failure}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
