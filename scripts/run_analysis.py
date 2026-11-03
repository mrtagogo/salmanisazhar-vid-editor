"""Analysis pipeline orchestrator (milestone 1: ingestion and analysis).

Run from the engine root:

    python -m scripts.run_analysis --input "input/talk.mp4"

Stages, in order: ingest -> assets -> transcribe -> silence -> edl -> report.
The pipeline stops at the review report. It never cuts video, and it refuses
to continue past ingest if validation found a blocking problem.
"""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path
from typing import Any, Callable

from .lib.config import ENGINE_ROOT, load_config
from .lib.jsonio import read_json
from .lib.media import MediaToolError
from .lib.paths import INPUT_DIR, ProjectPaths, project_paths
from .stages import assets as stage_assets
from .stages import s01_ingest, s02_transcribe, s03_silence, s04_edl, s05_report

STAGE_ORDER = ("ingest", "assets", "transcribe", "silence", "edl", "report")

MEDIA_SUFFIXES = {".mp4", ".mov", ".mkv", ".m4v", ".avi", ".mts", ".webm"}


def _resolve_source(given: str | None) -> Path:
    """Use the given path, or the single video sitting in input/."""
    if given:
        candidate = Path(given)
        if not candidate.is_absolute():
            candidate = (ENGINE_ROOT / candidate).resolve()
        return candidate

    if not INPUT_DIR.is_dir():
        raise SystemExit(
            f"No --input given and the input folder does not exist yet: {INPUT_DIR}\n"
            "Create it and put the source video there."
        )

    found = sorted(
        p for p in INPUT_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in MEDIA_SUFFIXES
    )
    if not found:
        raise SystemExit(
            f"No --input given and no video found in {INPUT_DIR}.\n"
            "Put the source video there, or pass --input with a path."
        )
    if len(found) > 1:
        names = "\n".join(f"  - {p.name}" for p in found)
        raise SystemExit(
            f"{len(found)} videos found in {INPUT_DIR}; pass --input to choose:\n{names}"
        )
    return found[0]


def _summarize(stage: str, result: dict[str, Any]) -> str:
    """One readable line per completed stage."""
    if stage == "ingest":
        validation = result["validation"]
        return (
            f"duration {result['container']['durationSeconds']}s, "
            f"validation {'ok' if validation['ok'] else 'FAILED'}, "
            f"{len(validation['errors'])} error(s), "
            f"{len(validation['warnings'])} warning(s)"
        )
    if stage == "assets":
        return f"{result['stats']['assetCount']} asset(s) listed"
    if stage == "transcribe":
        stats, engine = result["stats"], result["engine"]
        return (
            f"{stats['wordCount']} words, {stats['segmentCount']} segments, "
            f"lang {result['detectedLanguage']['code']} "
            f"(p={result['detectedLanguage']['probability']}), "
            f"{engine['device']}/{engine['computeType']}"
        )
    if stage == "silence":
        stats = result["stats"]
        return (
            f"{stats['spanCount']} silent span(s), {stats['silentSeconds']}s "
            f"({(stats['silentRatio'] or 0) * 100:.1f}%)"
        )
    if stage == "edl":
        stats = result["stats"]
        return (
            f"{stats['proposalCount']} proposal(s): {stats['autoApproved']} auto, "
            f"{stats['needsReview']} review, {stats['blocked']} blocked; "
            f"{stats['protectedRegionCount']} protected region(s)"
        )
    if stage == "report":
        return (
            f"{result['reportPath']} "
            f"({result['autoApproved']} auto, {result['needsReview']} to review)"
        )
    return "done"


def _selected_stages(args: argparse.Namespace) -> list[str]:
    if args.only:
        requested = [s.strip() for s in args.only.split(",") if s.strip()]
        unknown = [s for s in requested if s not in STAGE_ORDER]
        if unknown:
            raise SystemExit(
                f"Unknown stage(s): {', '.join(unknown)}. "
                f"Valid stages: {', '.join(STAGE_ORDER)}"
            )
        return requested

    start = 0
    if args.start_from:
        if args.start_from not in STAGE_ORDER:
            raise SystemExit(
                f"Unknown stage '{args.start_from}'. "
                f"Valid stages: {', '.join(STAGE_ORDER)}"
            )
        start = STAGE_ORDER.index(args.start_from)
    return list(STAGE_ORDER[start:])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="run_analysis",
        description="Tadabbur Motion — ingestion and analysis pipeline.",
    )
    parser.add_argument("--input", help="Source video. Defaults to the single file in input/.")
    parser.add_argument("--slug", help="Project folder name. Defaults to the filename.")
    parser.add_argument("--only", help=f"Comma-separated subset of: {','.join(STAGE_ORDER)}")
    parser.add_argument("--start-from", help="Run from this stage to the end.")
    parser.add_argument(
        "--reuse",
        action="store_true",
        help="Skip a stage when its output file already exists.",
    )
    # Transcription overrides. The config file stays the source of truth for
    # production; these exist so a smoke test can run a small model quickly
    # without editing the engine definition. Whatever is used is recorded in
    # the transcript artefact.
    parser.add_argument("--model", help="Override analysis.transcription.model.")
    parser.add_argument("--language", help="Override analysis.transcription.language.")
    parser.add_argument(
        "--device", choices=("auto", "cuda", "cpu"),
        help="Override analysis.transcription.device.",
    )
    args = parser.parse_args(argv)

    config = load_config()
    for flag, key in (
        (args.model, "model"),
        (args.language, "language"),
        (args.device, "device"),
    ):
        if flag:
            config["analysis"]["transcription"][key] = flag
    source = _resolve_source(args.input)
    paths = project_paths(source, args.slug)
    paths.ensure()

    stages: dict[str, tuple[Callable[..., dict], Path]] = {
        "ingest": (lambda: s01_ingest.run(config, source, paths), paths.metadata),
        "assets": (lambda: stage_assets.run(config, paths, source), paths.asset_manifest),
        "transcribe": (lambda: s02_transcribe.run(config, paths), paths.transcript),
        "silence": (lambda: s03_silence.run(config, paths), paths.silence),
        "edl": (lambda: s04_edl.run(config, paths), paths.edl),
        "report": (lambda: s05_report.run(config, paths), paths.review_report),
    }

    selected = _selected_stages(args)

    print(f"Tadabbur Motion — analysis")
    print(f"  source : {source}")
    print(f"  project: {paths.root}")
    print(f"  stages : {', '.join(selected)}")
    print()

    for stage in selected:
        runner, output = stages[stage]

        if args.reuse and output.exists():
            print(f"[{stage}] skipped (output exists: {output.name})")
            continue

        print(f"[{stage}] running...")
        try:
            result = runner()
        except MediaToolError as exc:
            print(f"[{stage}] FAILED — media tool error:\n{exc}", file=sys.stderr)
            return 2
        except Exception as exc:  # noqa: BLE001 - report, never swallow
            print(f"[{stage}] FAILED — {type(exc).__name__}: {exc}", file=sys.stderr)
            traceback.print_exc()
            return 1

        print(f"[{stage}] ok — {_summarize(stage, result)}")

        # Hard stop: do not spend a transcription pass on an unusable file.
        if stage == "ingest" and not result["validation"]["ok"]:
            print(file=sys.stderr)
            print("Validation failed. Fix the source before continuing:", file=sys.stderr)
            for error in result["validation"]["errors"]:
                print(f"  - {error}", file=sys.stderr)
            return 3

    print()
    if paths.edl.exists():
        edl = read_json(paths.edl)
        print(
            f"Approval checkpoint: {edl['approval']['status']}. "
            f"{edl['stats']['needsReview']} proposal(s) need a decision."
        )
    if paths.review_report.exists():
        print(f"Review report: {paths.review_report}")
    print("No video has been cut. Cutting stages are not implemented yet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
