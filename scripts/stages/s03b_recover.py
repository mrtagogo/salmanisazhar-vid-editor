"""Stage 3b — recovering speech the main transcription pass dropped.

Forcing a language is what makes the main pass reliable on Indonesian. It is
also what makes it blind to anything spoken in another one: on the presenter's
second recording, thirteen and a half seconds of Qur'anic recitation at full
speaking level produced no words at all, because the decoder was told the talk
was Indonesian and that passage is not.

The same audio, transcribed on its own with the language left free, comes back
as Arabic script. That matters beyond tidiness — the rule that Arabic is never
cut looks for Arabic CHARACTERS, so a recitation written out in Latin letters,
or dropped entirely, is a recitation the engine cannot protect.

So this takes the gaps where the microphone heard something and the transcript
has nothing, transcribes each one alone with the language left free, and folds
what comes back into the transcript. It is cheap because it only ever runs on
those gaps.

Recovered segments are marked `recovered: true`. They are not as trustworthy
as the main pass — a fragment decoded without surrounding context — and
anything that comes back as Arabic still needs checking against an approved
source before it reaches the screen.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from ..lib import gaps, media
from ..lib.config import get
from ..lib.cuda import enable_bundled_cuda
from ..lib.jsonio import read_json, rounded, utc_now, write_json
from ..lib.paths import ProjectPaths, audio_source
from ..lib.textutil import contains_arabic
from .s02_transcribe import _load_pcm

SCHEMA = "tadabbur-motion/recovered-speech@1"

# Shorter than this and there is not enough audio to decode anything useful.
MIN_SPAN_SECONDS = 0.45
# A little audio either side, so the decoder does not start mid-syllable.
PADDING_SECONDS = 0.25

# A short fragment decoded without context can invent a plausible sentence.
# Below this language confidence the result is recorded but kept OUT of the
# transcript, so a hallucination cannot become a word the engine believes in.
#
# Arabic script is the exception: it is let through even when confidence is
# low, because the cost of the two mistakes is not symmetrical. A spurious
# protected region means a cut is refused; a missed one means scripture is
# cut. Err toward refusing.
MIN_LANGUAGE_PROBABILITY = 0.5


def _build_model(config: dict, notes: list[str]):
    """The same model as the main pass, with the same device fallback."""
    from faster_whisper import WhisperModel

    model_name = get(config, "analysis.transcription.model", "large-v3")
    try:
        notes.extend(enable_bundled_cuda())
    except Exception as exc:  # noqa: BLE001 - degrade loudly, never silently
        notes.append(f"CUDA setup skipped: {type(exc).__name__}: {exc}")

    for device, compute in (("cuda", "int8_float16"), ("cpu", "int8")):
        try:
            return WhisperModel(model_name, device=device, compute_type=compute), device
        except Exception as exc:  # noqa: BLE001
            notes.append(f"{device} unavailable: {type(exc).__name__}: {exc}")
            print(f"  {device} unavailable: {exc}", file=sys.stderr)
    raise RuntimeError("No usable device for transcription; see runtimeNotes.")


def run(config: dict, paths: ProjectPaths) -> dict[str, Any]:
    """Re-transcribe the gaps that hold sound, and fold them into the transcript."""
    import numpy as np

    metadata = read_json(paths.metadata)
    transcript = read_json(paths.transcript)
    silence = read_json(paths.silence)

    min_gap = float(get(config, "cutting.balanced.unheardSpeechSeconds", 0.4))
    words = sorted(
        (w for s in transcript.get("segments", []) for w in (s.get("words") or [])),
        key=lambda w: w["start"],
    )
    found = [
        span
        for span in gaps.unheard_spans(words, silence.get("spans", []), min_gap)
        if span["end"] - span["start"] >= MIN_SPAN_SECONDS
    ]

    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "generatedAt": utc_now(),
        "spansExamined": len(found),
        "recovered": [],
        "runtimeNotes": [],
        "note": (
            "The main pass is told the talk is Indonesian, which is what makes it "
            "reliable and also what makes it blind to other languages. These spans "
            "were decoded with the language left free."
        ),
    }

    if not found:
        write_json(paths.data / "03b-recovered.json", payload)
        return payload

    if not paths.audio_wav.exists():
        source = Path(metadata["source"]["path"])
        media.extract_audio(config, audio_source(metadata, source), paths.audio_wav)

    rate = int(get(config, "analysis.audioExtract.sampleRate", 16000))
    samples = _load_pcm(paths.audio_wav, rate)
    duration = len(samples) / rate

    model, device = _build_model(config, payload["runtimeNotes"])
    payload["device"] = device

    recovered: list[dict[str, Any]] = []
    for index, span in enumerate(found, start=1):
        start = max(0.0, span["start"] - PADDING_SECONDS)
        end = min(duration, span["end"] + PADDING_SECONDS)
        slice_ = np.asarray(samples[int(start * rate) : int(end * rate)], dtype=np.float32)
        if slice_.size < int(MIN_SPAN_SECONDS * rate):
            continue

        # Language left free. Forcing Indonesian here would reproduce exactly
        # the failure this stage exists to undo.
        segments, info = model.transcribe(
            slice_,
            beam_size=int(get(config, "analysis.transcription.beamSize", 5)),
            vad_filter=bool(get(config, "analysis.transcription.vadFilter", True)),
            word_timestamps=True,
        )
        text = " ".join(s.text.strip() for s in segments).strip()
        if not text:
            continue

        arabic = contains_arabic(text)
        confidence = float(info.language_probability)
        trusted = arabic or confidence >= MIN_LANGUAGE_PROBABILITY

        recovered.append(
            {
                "id": f"rec-{index:04d}",
                "trusted": trusted,
                "start": rounded(start),
                "end": rounded(end),
                "text": text,
                "detectedLanguage": info.language,
                "languageProbability": rounded(confidence, 3),
                "containsArabic": arabic,
            }
        )

    payload["recovered"] = recovered
    payload["arabicFound"] = sum(1 for r in recovered if r["containsArabic"])
    payload["distrusted"] = sum(1 for r in recovered if not r["trusted"])

    # Fold into the transcript so every rule downstream sees them, marked so
    # nobody mistakes a context-free fragment for the main pass.
    trusted_items = [r for r in recovered if r["trusted"]]
    if trusted_items:
        segments = list(transcript.get("segments", []))
        for item in trusted_items:
            segments.append(
                {
                    "id": item["id"],
                    "start": item["start"],
                    "end": item["end"],
                    "text": item["text"],
                    "words": [],
                    "containsArabic": item["containsArabic"],
                    "recovered": True,
                    "detectedLanguage": item["detectedLanguage"],
                }
            )
        segments.sort(key=lambda s: float(s["start"]))
        transcript["segments"] = segments
        transcript["recoveredSegmentCount"] = len(trusted_items)
        write_json(paths.transcript, transcript)

    write_json(paths.data / "03b-recovered.json", payload)
    return payload
