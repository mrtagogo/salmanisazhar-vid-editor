"""Stage 1 — input validation and FFprobe metadata extraction.

Produces data/01-metadata.json. Hard problems become `errors` and stop the
pipeline; anything that merely constrains later creative choices becomes a
`warning` so the editor sees it in the review report.
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path
from typing import Any

from ..lib import media, sync
from ..lib.config import get
from ..lib.jsonio import rounded, utc_now, write_json
from ..lib.paths import ProjectPaths

SCHEMA = "tadabbur-motion/metadata@1"

# Containers we are willing to decode for a talking-head source.
ACCEPTED_SUFFIXES = {".mp4", ".mov", ".mkv", ".m4v", ".avi", ".mts", ".webm"}

MIN_DURATION_SECONDS = 0.5


def _parse_rate(value: str | None) -> float | None:
    """Convert an ffprobe rate string like '30000/1001' to a float."""
    if not value or value in ("0/0", "N/A"):
        return None
    try:
        return float(Fraction(value))
    except (ValueError, ZeroDivisionError):
        return None


def _rotation(stream: dict) -> int:
    """Read rotation from side data or legacy tags; 0 when upright."""
    for side in stream.get("side_data_list", []) or []:
        if "rotation" in side:
            try:
                return int(round(float(side["rotation"]))) % 360
            except (TypeError, ValueError):
                pass
    tag = (stream.get("tags") or {}).get("rotate")
    if tag:
        try:
            return int(round(float(tag))) % 360
        except (TypeError, ValueError):
            pass
    return 0


def _pick_stream(streams: list[dict], kind: str) -> dict | None:
    """Return the first stream of a kind, preferring a non-attachment video."""
    candidates = [s for s in streams if s.get("codec_type") == kind]
    if kind == "video":
        # Cover art is stored as a video stream; it is not the footage.
        real = [s for s in candidates if s.get("disposition", {}).get("attached_pic") != 1]
        candidates = real or candidates
    return candidates[0] if candidates else None


def _video_block(stream: dict) -> dict[str, Any]:
    width = stream.get("width")
    height = stream.get("height")
    r_fps = _parse_rate(stream.get("r_frame_rate"))
    avg_fps = _parse_rate(stream.get("avg_frame_rate"))

    frames = stream.get("nb_frames")
    try:
        frame_count = int(frames) if frames not in (None, "N/A") else None
    except (TypeError, ValueError):
        frame_count = None

    rotation = _rotation(stream)

    # The stored frame and the displayed picture are not the same thing. A
    # phone held upright records 1920x1080 with a 90-degree display matrix,
    # and ffmpeg applies that matrix on decode — so everything downstream sees
    # 1080x1920. Recording only the stored size made the face track and the
    # matte squash a portrait frame into a landscape box.
    quarter_turn = rotation is not None and abs(int(rotation)) % 180 == 90
    display_width = height if quarter_turn else width
    display_height = width if quarter_turn else height

    return {
        "codec": stream.get("codec_name"),
        "profile": stream.get("profile"),
        "width": width,
        "height": height,
        # What a decoder hands you, rotation already applied. Use THESE for
        # anything that works on pixels.
        "displayWidth": display_width,
        "displayHeight": display_height,
        "aspectRatio": (
            rounded(display_width / display_height, 4)
            if display_width and display_height
            else None
        ),
        "orientation": (
            None
            if not (display_width and display_height)
            else "portrait"
            if display_height > display_width
            else "landscape"
        ),
        "rFrameRate": rounded(r_fps, 4) if r_fps else None,
        "avgFrameRate": rounded(avg_fps, 4) if avg_fps else None,
        "pixelFormat": stream.get("pix_fmt"),
        "colorSpace": stream.get("color_space"),
        "rotationDegrees": _rotation(stream),
        "bitRate": stream.get("bit_rate"),
        "frameCount": frame_count,
    }


def _audio_block(stream: dict) -> dict[str, Any]:
    sample_rate = stream.get("sample_rate")
    return {
        "codec": stream.get("codec_name"),
        "sampleRate": int(sample_rate) if sample_rate else None,
        "channels": stream.get("channels"),
        "channelLayout": stream.get("channel_layout"),
        "bitRate": stream.get("bit_rate"),
    }


def _validate(
    source: Path,
    container: dict,
    video: dict | None,
    audio: dict | None,
    config: dict,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    if source.suffix.lower() not in ACCEPTED_SUFFIXES:
        warnings.append(
            f"Unusual container extension '{source.suffix}'. FFprobe read it, "
            "but confirm this is the intended master file."
        )

    duration = container.get("durationSeconds")
    if duration is None:
        errors.append("FFprobe reported no duration; the file may be truncated.")
    elif duration < MIN_DURATION_SECONDS:
        errors.append(f"Source is only {duration:.2f}s long; nothing to edit.")

    if video is None:
        errors.append(
            "No video stream found. This engine edits talking-head footage and "
            "needs a picture."
        )
    if audio is None:
        errors.append(
            "No audio stream found. Transcription and silence analysis are "
            "impossible without speech."
        )

    if audio and audio.get("sampleRate") and audio["sampleRate"] < 16000:
        warnings.append(
            f"Audio is {audio['sampleRate']} Hz, below Whisper's 16 kHz working "
            "rate. Transcription accuracy will suffer."
        )

    if video:
        r_fps, avg_fps = video.get("rFrameRate"), video.get("avgFrameRate")
        if r_fps and avg_fps and abs(r_fps - avg_fps) > 0.3:
            warnings.append(
                f"Frame rate looks variable (r={r_fps}, avg={avg_fps}). Cut points "
                "may drift; consider re-encoding to constant frame rate first."
            )
        if video.get("rotationDegrees"):
            warnings.append(
                f"Rotation metadata is {video['rotationDegrees']}°, so the stored "
                f"{video.get('width')}x{video.get('height')} frame displays as "
                f"{video.get('displayWidth')}x{video.get('displayHeight')}. Stages that "
                "work on pixels use the displayed size."
            )

        # Measured against the DISPLAYED picture: a phone-shot portrait video
        # stored as landscape needs no crop at all, and warning that it does
        # would send someone looking for a problem that is not there.
        width, height = video.get("displayWidth"), video.get("displayHeight")
        portrait = get(config, "output.portrait", {})
        target_w, target_h = portrait.get("width", 1080), portrait.get("height", 1920)
        if width and height and height < target_h:
            # A 9:16 crop out of a landscape master has to be scaled up.
            crop_width = height * target_w / target_h
            factor = target_w / crop_width if crop_width else 0
            warnings.append(
                f"Source is {width}x{height}; a {target_w}x{target_h} portrait crop "
                f"needs roughly {factor:.2f}x upscaling of the cropped region. "
                "Punch-ins will cost visible sharpness."
            )

    return {"ok": not errors, "errors": errors, "warnings": warnings}


def _align_external_audio(
    config: dict,
    source: Path,
    sound: Path,
    paths: ProjectPaths,
    duration: float,
    validation: dict,
) -> dict[str, Any]:
    """Line a separately recorded soundtrack up with the picture.

    Dual-system sound: the camera's own track is a guide, and the real sound
    comes from a recorder closer to the speaker. They start at different
    moments, so the offset is measured rather than asked for — and if the
    measurement is not trustworthy the audio is NOT used. Guessing an offset
    would desynchronise every word while still looking like it worked.
    """
    if not sound.exists():
        raise FileNotFoundError(f"Audio file not found: {sound}")

    paths.ensure()
    alignment = sync.measure(config, source, sound, paths.cache)

    block: dict[str, Any] = {
        "path": str(sound),
        "alignment": alignment.as_dict(),
        "used": alignment.confident,
        "alignedFile": None,
    }

    if not alignment.confident:
        validation["warnings"].append(
            f"A separate audio file was given but is NOT being used: "
            f"{alignment.reason}. The camera's own track is used instead."
        )
        return block

    media.align_audio(
        config,
        sound,
        paths.aligned_audio,
        offset=alignment.offsetSeconds,
        duration=duration,
    )
    # A wav extracted from the camera track on an earlier run would be
    # silently reused; it describes different sound.
    paths.audio_wav.unlink(missing_ok=True)
    block["alignedFile"] = str(paths.aligned_audio)
    validation["warnings"].append(
        f"Using the separate recording for sound, offset {alignment.offsetSeconds:+.3f}s "
        f"(match {alignment.correlation:.2f}). Transcription, silence and the cut all "
        "read it instead of the camera track."
    )
    return block


def run(
    config: dict,
    source: Path,
    paths: ProjectPaths,
    external_audio: Path | None = None,
) -> dict[str, Any]:
    """Probe the source and write the metadata artefact."""
    if not source.exists():
        raise FileNotFoundError(f"Source video not found: {source}")
    if source.stat().st_size == 0:
        raise ValueError(f"Source video is empty (0 bytes): {source}")

    raw = media.probe(config, source)
    fmt = raw.get("format", {}) or {}
    streams = raw.get("streams", []) or []

    try:
        duration = float(fmt["duration"])
    except (KeyError, TypeError, ValueError):
        duration = None

    container = {
        "formatName": fmt.get("format_name"),
        "formatLongName": fmt.get("format_long_name"),
        "durationSeconds": rounded(duration) if duration is not None else None,
        "bitRate": fmt.get("bit_rate"),
        "streamCount": len(streams),
    }

    video_stream = _pick_stream(streams, "video")
    audio_stream = _pick_stream(streams, "audio")
    video = _video_block(video_stream) if video_stream else None
    audio = _audio_block(audio_stream) if audio_stream else None

    payload = {
        "schema": SCHEMA,
        "generatedAt": utc_now(),
        "source": {
            "path": str(source.resolve()),
            "filename": source.name,
            "sizeBytes": source.stat().st_size,
            "projectSlug": paths.slug,
        },
        "container": container,
        "video": video,
        "audio": audio,
        "validation": _validate(source, container, video, audio, config),
        "ffprobe": raw,
    }

    paths.ensure()
    if external_audio is not None:
        payload["externalAudio"] = _align_external_audio(
            config, source, external_audio, paths, duration or 0.0, payload["validation"]
        )

    write_json(paths.metadata, payload)
    return payload
