"""Runtime and media-layer checks.

Run from the engine root:

    python -m tests.test_runtime

These guard the three failures found while building milestone 1:
  * ffmpeg/ffprobe discovery when the binaries are not on PATH;
  * reading the extracted WAV ourselves instead of letting faster-whisper
    decode through PyAV, whose current release rejects the arguments it passes;
  * registering the pip-installed CUDA DLL directories, where `nvidia` is a
    namespace package and therefore has no `__file__`.

It also checks the silencedetect parser against audio with known silence,
including a file that ends in silence — the case where ffmpeg emits
`silence_start` with no matching `silence_end`.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from scripts.lib import media
from scripts.lib.config import load_config
from scripts.lib.cuda import enable_bundled_cuda
from scripts.stages.s02_transcribe import _load_pcm

RATE = 16000

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


def _build_wav(config: dict, path: Path, parts: list[str]) -> None:
    """Concatenate lavfi audio sources into a 16 kHz mono WAV."""
    args = [str(media.ffmpeg_bin(config)), "-hide_banner", "-nostdin", "-y"]
    for part in parts:
        args += ["-f", "lavfi", "-i", part]
    labels = "".join(f"[{i}]" for i in range(len(parts)))
    args += [
        "-filter_complex", f"{labels}concat=n={len(parts)}:v=0:a=1",
        "-ar", str(RATE), "-ac", "1", "-c:a", "pcm_s16le",
        str(path),
    ]
    media.run(args)


def main() -> int:
    config = load_config()

    print("\nTool discovery")
    ffmpeg = media.ffmpeg_bin(config)
    ffprobe = media.ffprobe_bin(config)
    check("ffmpeg resolves to a real file", ffmpeg.is_file(), str(ffmpeg))
    check("ffprobe resolves to a real file", ffprobe.is_file(), str(ffprobe))

    print("\nCUDA library registration")
    try:
        dirs = enable_bundled_cuda()
        raised = None
    except Exception as exc:  # noqa: BLE001
        dirs, raised = None, exc
    # The important guarantee is that this never throws: `nvidia` is a
    # namespace package, so reading its __file__ would hand back None.
    check("enable_bundled_cuda() does not raise", raised is None, repr(raised))
    check("enable_bundled_cuda() returns a list", isinstance(dirs, list))
    if dirs:
        check("every registered directory exists",
              all(Path(d).is_dir() for d in dirs))
        names = {p.name.lower() for d in dirs for p in Path(d).glob("*.dll")}
        check("cuBLAS 12 is present", "cublas64_12.dll" in names)
        check("cuDNN 9 is present (ctranslate2 4.x requires 9, not 10)",
              "cudnn64_9.dll" in names, str(sorted(n for n in names if "cudnn64" in n)))
    else:
        print("  SKIP  no bundled CUDA libraries installed; GPU checks skipped")

    with tempfile.TemporaryDirectory(prefix="tadabbur-runtime-") as tmp:
        work = Path(tmp)

        print("\nAudio decoding")
        tone = work / "tone.wav"
        _build_wav(config, tone, [f"sine=f=440:r={RATE}:d=2"])
        samples = _load_pcm(tone, RATE)
        check("decoded sample count matches duration",
              abs(len(samples) - 2 * RATE) <= RATE // 100,
              f"{len(samples)} samples")
        check("decoded audio is float32",
              samples.dtype.name == "float32", samples.dtype.name)
        check("decoded audio is normalised to [-1, 1]",
              float(abs(samples).max()) <= 1.0, str(float(abs(samples).max())))

        wrong_rate = work / "wrong-rate.wav"
        media.run([
            str(ffmpeg), "-hide_banner", "-nostdin", "-y",
            "-f", "lavfi", "-i", "sine=f=440:r=8000:d=1",
            "-ar", "8000", "-ac", "1", "-c:a", "pcm_s16le", str(wrong_rate),
        ])
        try:
            _load_pcm(wrong_rate, RATE)
            rejected = False
        except RuntimeError:
            rejected = True
        check("a wrong sample rate is rejected, not silently resampled", rejected)

        print("\nSilence detection")
        # 1 s tone, 2 s silence, 1 s tone.
        interior = work / "interior.wav"
        _build_wav(config, interior, [
            f"sine=f=440:r={RATE}:d=1",
            f"anullsrc=r={RATE}:cl=mono:d=2",
            f"sine=f=440:r={RATE}:d=1",
        ])
        duration = float(media.probe(config, interior)["format"]["duration"])
        spans = media.detect_silence(config, interior, duration)
        check("one silent span is found in the middle", len(spans) == 1,
              f"got {len(spans)}: {spans}")
        if spans:
            span = spans[0]
            check("silent span starts about 1.0s in",
                  abs(span["start"] - 1.0) < 0.15, str(span["start"]))
            check("silent span is about 2.0s long",
                  abs((span["end"] - span["start"]) - 2.0) < 0.2,
                  str(span["end"] - span["start"]))

        # 1 s tone then 2 s silence: ffmpeg reports silence_start with no
        # silence_end, so the parser has to close the span at the duration.
        trailing = work / "trailing.wav"
        _build_wav(config, trailing, [
            f"sine=f=440:r={RATE}:d=1",
            f"anullsrc=r={RATE}:cl=mono:d=2",
        ])
        duration = float(media.probe(config, trailing)["format"]["duration"])
        spans = media.detect_silence(config, trailing, duration)
        check("silence running to end of file is reported", len(spans) == 1,
              f"got {len(spans)}: {spans}")
        if spans:
            check("unterminated silence is closed at the file duration",
                  abs(spans[-1]["end"] - duration) < 0.05,
                  f"{spans[-1]['end']} vs {duration}")

        print("\nFailure reporting")
        try:
            media.probe(config, work / "does-not-exist.mp4")
            failed_loudly = False
        except media.MediaToolError:
            failed_loudly = True
        check("a missing file raises MediaToolError", failed_loudly)

    print(f"\n{_checks - len(_failures)}/{_checks} checks passed")
    if _failures:
        print("\nFailed:")
        for failure in _failures:
            print(f"  - {failure}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
