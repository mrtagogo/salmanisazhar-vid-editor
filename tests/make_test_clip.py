"""Generate a synthetic talking-head clip for end-to-end pipeline testing.

Run from the engine root:

    python -m tests.make_test_clip

Writes tests/fixtures/test-clip.mp4: a flat-colour 1920x1080 30 fps picture
with synthesised speech containing, on purpose, a long stretch of dead air, a
stutter, a repeated phrase, a question followed by a pause, a hesitation
sound, and dead air at the head and tail.

This exercises the media and transcription plumbing. It does NOT test
Indonesian transcription quality: this machine only has en-US voices
installed, so the speech is English. The Indonesian and Arabic editorial
rules are covered by tests/test_edl_logic.py instead.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from scripts.lib import media
from scripts.lib.config import ENGINE_ROOT, load_config

FIXTURES = ENGINE_ROOT / "tests" / "fixtures"
OUTPUT = FIXTURES / "test-clip.mp4"

WIDTH, HEIGHT, FPS = 1920, 1080, 30
BACKGROUND = "0x1e2a38"

# (text, pause in ms that follows). A leading pause is added separately.
SCRIPT: list[tuple[str, int]] = [
    ("This is a test of the Tadabbur Motion engine.", 4000),
    ("The the engine should notice that.", 900),
    ("I will say this twice. I will say this twice.", 3200),
    ("Do you understand what I mean?", 3000),
    ("Hmm, that is the end of the test.", 0),
]

LEADING_PAUSE_MS = 1200
TRAILING_PAUSE_MS = 2500


def _ssml() -> str:
    parts = [
        '<speak version="1.0" '
        'xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">',
        f'<break time="{LEADING_PAUSE_MS}ms"/>',
    ]
    for text, pause_ms in SCRIPT:
        parts.append(text)
        if pause_ms:
            parts.append(f'<break time="{pause_ms}ms"/>')
    parts.append(f'<break time="{TRAILING_PAUSE_MS}ms"/>')
    parts.append("</speak>")
    return "\n".join(parts)


def _synthesize(wav_path: Path, work: Path) -> None:
    """Drive Windows SAPI through PowerShell to render the SSML to a WAV."""
    if sys.platform != "win32":
        raise SystemExit(
            "This generator uses Windows SAPI. On another platform, supply a "
            "real clip instead and pass it with --input."
        )

    ssml_path = work / "speech.xml"
    ssml_path.write_text(_ssml(), encoding="utf-8")

    script_path = work / "speak.ps1"
    script_path.write_text(
        "Add-Type -AssemblyName System.Speech\n"
        "$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer\n"
        f'$synth.SetOutputToWaveFile("{wav_path}")\n'
        f'$ssml = Get-Content -Raw -Encoding UTF8 "{ssml_path}"\n'
        "$synth.SpeakSsml($ssml)\n"
        "$synth.Dispose()\n",
        encoding="utf-8",
    )

    proc = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(script_path)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0 or not wav_path.exists():
        raise SystemExit(
            "Speech synthesis failed.\n"
            f"exit={proc.returncode}\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )


def main() -> int:
    config = load_config()
    FIXTURES.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="tadabbur-clip-") as tmp:
        work = Path(tmp)
        wav = work / "speech.wav"

        print("Synthesising speech via Windows SAPI...")
        _synthesize(wav, work)
        print(f"  wrote {wav.stat().st_size} bytes")

        print(f"Muxing {WIDTH}x{HEIGHT} @ {FPS}fps picture with the speech...")
        media.run([
            str(media.ffmpeg_bin(config)),
            "-hide_banner", "-nostdin", "-y",
            "-f", "lavfi",
            "-i", f"color=c={BACKGROUND}:s={WIDTH}x{HEIGHT}:r={FPS}",
            "-i", str(wav),
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
            "-shortest",
            str(OUTPUT),
        ])

    probed = media.probe(config, OUTPUT)
    duration = float(probed["format"]["duration"])
    print(f"\nWrote {OUTPUT}")
    print(f"  duration {duration:.2f}s, {OUTPUT.stat().st_size} bytes")
    print("\nNext:")
    print(f'  python -m scripts.run_analysis --input "{OUTPUT}" '
          "--model small --language en")
    return 0


if __name__ == "__main__":
    sys.exit(main())
