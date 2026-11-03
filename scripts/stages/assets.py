"""Asset manifest.

Produces data/asset-manifest.json. Only files that actually exist on disk are
listed. Editorial intent (which scene an asset belongs to, how it should be
cropped) is left null for a human to fill in — the engine does not guess it,
and it never writes a path for an asset that does not exist.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..lib import media
from ..lib.jsonio import rounded, utc_now, write_json
from ..lib.paths import ENGINE_ROOT, ProjectPaths

SCHEMA = "tadabbur-motion/asset-manifest@1"

ASSET_DIRS = ("input", "assets")

VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".m4v", ".avi", ".mts", ".webm"}
AUDIO_SUFFIXES = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif"}
FONT_SUFFIXES = {".ttf", ".otf", ".woff", ".woff2"}


def _asset_type(path: Path) -> str | None:
    suffix = path.suffix.lower()
    if suffix in VIDEO_SUFFIXES:
        return "video"
    if suffix in AUDIO_SUFFIXES:
        return "audio"
    if suffix in IMAGE_SUFFIXES:
        return "image"
    if suffix in FONT_SUFFIXES:
        return "font"
    return None


def _duration(config: dict, path: Path, asset_type: str) -> float | None:
    """Probe duration for time-based assets; None for stills and fonts."""
    if asset_type not in ("video", "audio"):
        return None
    try:
        probed = media.probe(config, path)
        value = probed.get("format", {}).get("duration")
        return rounded(float(value)) if value is not None else None
    except Exception:
        # A probe failure is reported as unknown rather than guessed.
        return None


def run(config: dict, paths: ProjectPaths, source: Path) -> dict[str, Any]:
    """Scan the asset directories and write the manifest."""
    entries: list[dict[str, Any]] = []
    seen: set[Path] = set()

    def add(path: Path, role: str) -> None:
        resolved = path.resolve()
        if resolved in seen or not resolved.is_file():
            return
        asset_type = _asset_type(resolved)
        if asset_type is None:
            return
        seen.add(resolved)
        entries.append(
            {
                "filename": resolved.name,
                "path": str(resolved),
                "assetType": asset_type,
                "role": role,
                "durationSeconds": _duration(config, resolved, asset_type),
                "sizeBytes": resolved.stat().st_size,
                "source": "user-provided",
                # Editorial fields: a human fills these in, the engine does not.
                "intendedScene": None,
                "intendedPurpose": None,
                "preferredCrop": None,
                "preferredPosition": None,
            }
        )

    add(source, "primary-footage")
    for directory in ASSET_DIRS:
        folder = ENGINE_ROOT / directory
        if folder.is_dir():
            for path in sorted(folder.rglob("*")):
                add(path, "supplied-asset")

    payload = {
        "schema": SCHEMA,
        "generatedAt": utc_now(),
        "projectSlug": paths.slug,
        "scannedDirectories": [
            str(ENGINE_ROOT / d) for d in ASSET_DIRS if (ENGINE_ROOT / d).is_dir()
        ],
        "note": (
            "intendedScene, intendedPurpose, preferredCrop and preferredPosition "
            "are deliberately null. Fill them in by hand; the engine will not "
            "invent editorial intent, and it will not reference an asset that is "
            "not listed here."
        ),
        "stats": {
            "assetCount": len(entries),
            "byType": {
                kind: sum(1 for e in entries if e["assetType"] == kind)
                for kind in sorted({e["assetType"] for e in entries})
            },
        },
        "assets": entries,
    }

    paths.ensure()
    write_json(paths.asset_manifest, payload)
    return payload
