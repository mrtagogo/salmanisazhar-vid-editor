"""FFmpeg / FFprobe access layer.

Every media call in the engine goes through here, so binary discovery and
failure reporting are defined in exactly one place. A failing command raises
with the tool's own stderr attached rather than being silently skipped.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .config import get


class MediaToolError(RuntimeError):
    """Raised when ffmpeg/ffprobe is missing or exits non-zero."""


# Common install locations checked before giving up, so the engine works on a
# machine where winget installed ffmpeg without putting it on PATH.
_FALLBACK_GLOBS = (
    r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*\ffmpeg-*\bin",
    r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\BtbN.FFmpeg*\ffmpeg-*\bin",
    r"C:\ffmpeg\bin",
)


def _discover(tool: str, configured: str | None) -> Path:
    """Locate ffmpeg or ffprobe: explicit config, then PATH, then known folders."""
    if configured:
        candidate = Path(os.path.expandvars(configured))
        if candidate.is_file():
            return candidate
        raise MediaToolError(
            f"tools.{tool}Path is set to a file that does not exist: {candidate}"
        )

    on_path = shutil.which(tool)
    if on_path:
        return Path(on_path)

    exe = f"{tool}.exe" if os.name == "nt" else tool
    for pattern in _FALLBACK_GLOBS:
        expanded = Path(os.path.expandvars(pattern))
        root, _, tail = str(expanded).partition("*")
        base = Path(root).parent if tail else Path(root)
        if not base.exists():
            continue
        for found in base.glob(f"**/{exe}"):
            return found

    raise MediaToolError(
        f"{tool} not found. Install it (e.g. 'winget install Gyan.FFmpeg') or set "
        f"tools.{tool}Path in engine.config.local.json."
    )


def ffmpeg_bin(config: dict) -> Path:
    return _discover("ffmpeg", get(config, "tools.ffmpegPath"))


def ffprobe_bin(config: dict) -> Path:
    return _discover("ffprobe", get(config, "tools.ffprobePath"))


def run(args: list[str], *, timeout: int = 3600) -> subprocess.CompletedProcess:
    """Run a media command, raising with captured stderr when it fails."""
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError as exc:  # binary vanished between discovery and use
        raise MediaToolError(f"Cannot execute {args[0]}: {exc}") from exc

    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or "").strip().splitlines()[-20:])
        raise MediaToolError(
            f"Command failed (exit {proc.returncode}):\n  {' '.join(args)}\n\n{tail}"
        )
    return proc


def probe(config: dict, source: Path) -> dict[str, Any]:
    """Full ffprobe dump: format block plus every stream."""
    proc = run(
        [
            str(ffprobe_bin(config)),
            "-v", "error",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(source),
        ]
    )
    return json.loads(proc.stdout)


def extract_audio(config: dict, source: Path, destination: Path) -> Path:
    """Decode the source to 16 kHz mono PCM — the format Whisper expects.

    Transcribing from this intermediate file keeps transcription reproducible
    and avoids re-decoding the video for every analysis re-run.
    """
    settings = get(config, "analysis.audioExtract", {})
    destination.parent.mkdir(parents=True, exist_ok=True)

    run(
        [
            str(ffmpeg_bin(config)),
            "-hide_banner",
            "-nostdin",
            "-y",
            "-i", str(source),
            "-vn",
            "-ac", str(settings.get("channels", 1)),
            "-ar", str(settings.get("sampleRate", 16000)),
            "-acodec", settings.get("codec", "pcm_s16le"),
            str(destination),
        ]
    )
    return destination


_SILENCE_START = re.compile(r"silence_start:\s*(-?[\d.]+)")
_SILENCE_END = re.compile(r"silence_end:\s*(-?[\d.]+)")


def detect_silence(
    config: dict, audio: Path, duration: float
) -> list[dict[str, float]]:
    """Run ffmpeg's silencedetect and return silent spans in seconds.

    Note: this reports *acoustic* silence only. It carries no editorial
    meaning — deciding which silence may be shortened happens in the EDL
    stage, never here.
    """
    noise_db = get(config, "analysis.silence.noiseFloorDb", -32)
    min_seconds = get(config, "analysis.silence.minSilenceSeconds", 0.3)

    proc = subprocess.run(
        [
            str(ffmpeg_bin(config)),
            "-hide_banner",
            "-nostdin",
            "-i", str(audio),
            "-af", f"silencedetect=noise={noise_db}dB:d={min_seconds}",
            "-f", "null",
            "-",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    # silencedetect writes to stderr; a non-zero exit here is a real failure.
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or "").strip().splitlines()[-20:])
        raise MediaToolError(f"silencedetect failed (exit {proc.returncode}):\n{tail}")

    spans: list[dict[str, float]] = []
    pending_start: float | None = None

    for line in (proc.stderr or "").splitlines():
        start_match = _SILENCE_START.search(line)
        if start_match:
            pending_start = max(0.0, float(start_match.group(1)))
            continue
        end_match = _SILENCE_END.search(line)
        if end_match and pending_start is not None:
            end = float(end_match.group(1))
            spans.append({"start": pending_start, "end": end})
            pending_start = None

    # A file that ends in silence never emits silence_end; close it at duration.
    if pending_start is not None and duration > pending_start:
        spans.append({"start": pending_start, "end": duration})

    return spans
