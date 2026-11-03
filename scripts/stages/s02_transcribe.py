"""Stage 2 — Indonesian transcription with word-level timestamps.

Produces data/02-transcript.json. The transcript is the engine's record of
what was actually said; nothing downstream may alter these words, only decide
which spans of time to keep.
"""

from __future__ import annotations

import sys
import wave
from pathlib import Path
from typing import Any

from ..lib import media
from ..lib.config import get
from ..lib.cuda import enable_bundled_cuda
from ..lib.jsonio import read_json, rounded, utc_now, write_json
from ..lib.paths import ProjectPaths
from ..lib.textutil import contains_arabic

SCHEMA = "tadabbur-motion/transcript@1"


def _import_whisper():
    try:
        from faster_whisper import WhisperModel  # noqa: PLC0415
        import faster_whisper  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError(
            "faster-whisper is not installed. Run:\n"
            "  python -m pip install faster-whisper"
        ) from exc
    return WhisperModel, getattr(faster_whisper, "__version__", "unknown")


def _load_pcm(path: Path, expected_rate: int):
    """Read the ffmpeg-extracted WAV into the float32 mono array Whisper wants.

    Passing an array rather than a path matters: faster-whisper would
    otherwise decode the file itself through PyAV, and the current PyAV
    release no longer accepts the arguments faster-whisper passes to it
    (`av.open(..., metadata_errors=...)`). Decoding here keeps ffmpeg as the
    engine's single decoder and removes PyAV from the critical path.
    """
    import numpy as np  # noqa: PLC0415 - ships with ctranslate2

    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        sample_width = handle.getsampwidth()
        rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())

    if sample_width != 2:
        raise RuntimeError(
            f"Expected 16-bit PCM in {path}, found {sample_width * 8}-bit. "
            "Check analysis.audioExtract.codec."
        )
    if rate != expected_rate:
        raise RuntimeError(
            f"Expected {expected_rate} Hz in {path}, found {rate} Hz. "
            "Delete the cached WAV and re-run so it is re-extracted."
        )

    samples = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return samples


def _cuda_device_count() -> int:
    try:
        import ctranslate2  # noqa: PLC0415

        return int(ctranslate2.get_cuda_device_count())
    except Exception:
        return 0


def _resolve_runtime(config: dict) -> list[tuple[str, str]]:
    """Build an ordered list of (device, computeType) attempts.

    'auto' prefers the GPU but always keeps a CPU fallback, because CUDA on
    Windows additionally needs cuBLAS and cuDNN libraries that a driver alone
    does not provide.
    """
    device = get(config, "analysis.transcription.device", "auto")
    compute = get(config, "analysis.transcription.computeType", "auto")

    def compute_for(dev: str) -> str:
        if compute != "auto":
            return compute
        # int8_float16 keeps large-v3 inside a 4 GB card; int8 is the CPU default.
        return "int8_float16" if dev == "cuda" else "int8"

    if device != "auto":
        return [(device, compute_for(device))]

    attempts: list[tuple[str, str]] = []
    if _cuda_device_count() > 0:
        attempts.append(("cuda", compute_for("cuda")))
    attempts.append(("cpu", compute_for("cpu")))
    return attempts


def _collect(segments_iter, word_threshold: float) -> dict[str, Any]:
    """Materialise the transcription generator into plain data.

    faster-whisper is lazy: the model only touches the compute backend once
    this generator is consumed, so a missing CUDA library surfaces *here*
    rather than at construction time. The device fallback therefore has to
    wrap this call, not just the model load.
    """
    segments: list[dict[str, Any]] = []
    total_words = 0
    low_confidence_words = 0
    speech_seconds = 0.0
    arabic_segments = 0

    for index, segment in enumerate(segments_iter):
        words: list[dict[str, Any]] = []
        for word in segment.words or []:
            probability = (
                rounded(word.probability, 4) if word.probability is not None else None
            )
            low = probability is not None and probability < word_threshold
            words.append(
                {
                    "start": rounded(word.start),
                    "end": rounded(word.end),
                    "word": word.word,
                    "probability": probability,
                    "lowConfidence": bool(low),
                }
            )
            total_words += 1
            if low:
                low_confidence_words += 1

        text = segment.text.strip()
        has_arabic = contains_arabic(text)
        if has_arabic:
            arabic_segments += 1

        speech_seconds += max(0.0, segment.end - segment.start)

        segments.append(
            {
                "id": index,
                "start": rounded(segment.start),
                "end": rounded(segment.end),
                "text": text,
                "avgLogprob": rounded(segment.avg_logprob, 4),
                "noSpeechProb": rounded(segment.no_speech_prob, 4),
                "compressionRatio": rounded(segment.compression_ratio, 4),
                "containsArabic": has_arabic,
                "words": words,
            }
        )

    return {
        "segments": segments,
        "wordCount": total_words,
        "lowConfidenceWords": low_confidence_words,
        "speechSeconds": speech_seconds,
        "arabicSegments": arabic_segments,
    }


def run(config: dict, paths: ProjectPaths) -> dict[str, Any]:
    """Transcribe the project's audio and write the transcript artefact."""
    # Must happen before the first ctranslate2 import, or the GPU libraries
    # bundled in site-packages stay invisible to the loader on Windows.
    # A failure here only costs the GPU, so it degrades to CPU — loudly.
    startup_notes: list[str] = []
    try:
        cuda_dirs = enable_bundled_cuda()
    except Exception as exc:  # noqa: BLE001 - reported, never swallowed
        cuda_dirs = []
        note = (
            f"CUDA library registration failed — {type(exc).__name__}: {exc}. "
            "Continuing without the bundled GPU libraries."
        )
        startup_notes.append(note)
        print(f"  [transcribe] {note}", file=sys.stderr)

    metadata = read_json(paths.metadata)
    source = Path(metadata["source"]["path"])
    duration = metadata["container"].get("durationSeconds")

    paths.ensure()
    # Re-use the cached 16 kHz mono extraction when it is already there.
    if not paths.audio_wav.exists():
        media.extract_audio(config, source, paths.audio_wav)

    sample_rate = int(get(config, "analysis.audioExtract.sampleRate", 16000))
    audio = _load_pcm(paths.audio_wav, sample_rate)

    WhisperModel, library_version = _import_whisper()
    settings = get(config, "analysis.transcription", {})
    model_name = settings.get("model", "large-v3")
    word_threshold = settings.get("lowConfidenceWordThreshold", 0.55)

    notes: list[str] = list(startup_notes)
    outcome: tuple[str, str, Any, dict[str, Any]] | None = None

    for device, compute_type in _resolve_runtime(config):
        try:
            model = WhisperModel(model_name, device=device, compute_type=compute_type)
            segments_iter, info = model.transcribe(
                audio,
                language=settings.get("language", "id"),
                beam_size=settings.get("beamSize", 5),
                vad_filter=settings.get("vadFilter", True),
                word_timestamps=settings.get("wordTimestamps", True),
                condition_on_previous_text=settings.get(
                    "conditionOnPreviousText", False
                ),
            )
            collected = _collect(segments_iter, word_threshold)
        except Exception as exc:  # noqa: BLE001 - recorded, never swallowed
            note = f"{device}/{compute_type} failed — {type(exc).__name__}: {exc}"
            notes.append(note)
            # Loud on the console as well, so a degraded run is never quiet.
            print(f"  [transcribe] {note}", file=sys.stderr)
            continue
        outcome = (device, compute_type, info, collected)
        break

    if outcome is None:
        raise RuntimeError(
            "Transcription failed on every available device:\n  "
            + "\n  ".join(notes)
        )

    device, compute_type, info, collected = outcome
    speech_seconds = collected["speechSeconds"]
    total_words = collected["wordCount"]

    payload = {
        "schema": SCHEMA,
        "generatedAt": utc_now(),
        "engine": {
            "library": "faster-whisper",
            "libraryVersion": library_version,
            "model": model_name,
            "device": device,
            "computeType": compute_type,
            "beamSize": settings.get("beamSize", 5),
            "vadFilter": settings.get("vadFilter", True),
            "requestedLanguage": settings.get("language", "id"),
            "audioDecoder": "ffmpeg -> 16-bit PCM WAV -> numpy float32",
            "audioSampleRate": sample_rate,
            "cudaLibraryDirs": cuda_dirs,
            "runtimeNotes": notes,
        },
        "detectedLanguage": {
            "code": info.language,
            "probability": rounded(info.language_probability, 4),
        },
        "durationSeconds": duration,
        "stats": {
            "segmentCount": len(collected["segments"]),
            "wordCount": total_words,
            "speechSeconds": rounded(speech_seconds),
            "speechRatio": (
                rounded(speech_seconds / duration, 4) if duration else None
            ),
            "wordsPerMinute": (
                rounded(total_words / (speech_seconds / 60), 1)
                if speech_seconds > 0
                else None
            ),
            "lowConfidenceWords": collected["lowConfidenceWords"],
            "segmentsContainingArabic": collected["arabicSegments"],
        },
        "segments": collected["segments"],
    }

    write_json(paths.transcript, payload)
    return payload
