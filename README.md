# Tadabbur Motion — editing engine

An intelligent editing pipeline for Indonesian talking-head video. This
repository is a reusable production engine, not a single video project.

**Current state: analysis, plus the first cut.**
The engine inspects footage, transcribes it, finds silence, reasons about what
could be cut, and produces a review report. Once a human approves that report
it will apply the cuts. **It does not compose or render anything yet** — no
subtitles, camera moves, graphics or audio cleanup.

---

## Editing identity

The defaults, set in `engine.config.json` under `editingIdentity`:

| Aspect | Standard | What it means here |
| --- | --- | --- |
| Cutting | `balanced` | Dead air is shortened, never erased. Rhetorical, thinking and emotional pauses survive. Slow speech is never cut for being slow. |
| Subtitles | `hybrid` | Complete spoken subtitles, selective keyword highlights, max two lines. *(not yet implemented)* |
| Camera | `dynamic` | Intentional medium/close framing, subtle punch-ins. *(not yet implemented)* |
| Audio | `clean` | Intelligible voice first, conservative processing. *(not yet implemented)* |

### Editorial safety, as enforced in code

- Arabic script becomes a **protected region**. Nothing inside it is ever
  proposed for a cut, and silence *touching* it is protected too.
- A pause after a question is refused as a cut — it is rhetorical weight.
- A word gap that detected silence does not corroborate (breath, room tone,
  quiet speech) is downgraded to REVIEW instead of trimmed.
- Repetitions and hesitation sounds are *proposed*, never auto-applied,
  because repetition can be deliberate emphasis.
- Low transcription confidence never causes a cut; it raises a note.
- Spoken words are never rewritten. The transcript is a record, not a script.

---

## Layout

```
engine.config.json          Editing standards and every tunable threshold
engine.config.local.json    Machine-specific overrides (ffmpeg paths)
input/                      Source videos you supply
models/                     Third-party model files (not committed; see its README)
scripts/
  lib/        config, paths, ffmpeg/ffprobe access, face tracking, text helpers
  stages/     one module per pipeline stage
  run_analysis.py           Orchestrator
tests/
  test_edl_logic.py         Deterministic checks on the editorial rules
  test_face_track.py        Face-track arithmetic, hand-built samples
  test_face_detection.py    Detection end to end, against a known trajectory
  test_matte.py             Matting arithmetic, video round-trip, a real run
  make_test_clip.py         Generates a synthetic clip for end-to-end testing
projects/<slug>/
  data/       01-metadata, 02-transcript, 03-silence, 04-edl,
              06-face-track, 07-person-matte, 08-rough-cut, asset-manifest
  cache/      extracted 16 kHz mono audio, audio-aligned.m4a, matte.mp4
  review/     review-report.md
  output/     rough-cut.mp4
```

All timestamps in project data are **seconds**. Conversion to frames happens
only at the composition layer (not built yet).

---

## Prerequisites

- **FFmpeg / FFprobe.** `winget install Gyan.FFmpeg`. If it is not on PATH,
  pin the absolute paths in `engine.config.local.json` under `tools`.
- **Python** with `faster-whisper`, `opencv-python` and `onnxruntime`:
  `python -m pip install faster-whisper opencv-python onnxruntime`.
- **Two model files**, for the `track` and `matte` stages. Neither is
  committed; see [`models/README.md`](models/README.md) for the downloads and
  their checksums. The matting model is GPL-3.0 — [`NOTICE`](NOTICE) explains
  what that does and does not mean here.
- **Node 22+** for the composition layer: `npm install`. Remotion and React
  are pinned to exact versions (`remotion` 4.0.534, `react` 19.1.1) so they
  stay aligned with the effects library this project borrows from. There are
  four dependencies and no others: no three.js, and deliberately no GSAP —
  see [`docs/effects.md`](docs/effects.md).

### GPU

CUDA is used when it works and is skipped loudly when it does not. The GPU
libraries come from pip rather than a system CUDA install:

```bash
python -m pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
```

ctranslate2 4.8.5 needs **cuBLAS 12 and cuDNN 9** specifically — a cuDNN 10
wheel will not load. Verified working here with cuBLAS 12.9.2 and
cuDNN 9.27.0 on an RTX 2050.

`large-v3` at `int8_float16` fits in that card's 4 GB and runs without
falling back. That compute type is chosen deliberately: plain `float16` would
need roughly 3 GB of weights and leaves too little headroom.

On Windows those wheels unpack into `site-packages/nvidia/*/bin`, which the
DLL loader does not search. `scripts/lib/cuda.py` registers those directories
with `os.add_dll_directory()` before ctranslate2 is imported; without it the
GPU attempt fails with `cublas64_12.dll is not found`. Note that `nvidia` is a
namespace package, so its roots come from `__path__`, not `__file__`.

The device actually used is always recorded in `02-transcript.json` under
`engine.device`, with `engine.cudaLibraryDirs` listing what was registered and
`engine.runtimeNotes` holding any fallback reason. GPU and CPU runs were
checked against each other and produced identical transcripts and proposals.

---

## Running the analysis

Put a video in `input/`, then from the engine root:

```bash
python -m scripts.run_analysis
```

Or name the file explicitly:

```bash
python -m scripts.run_analysis --input "input/kajian-01.mp4"
```

If the sound was recorded separately — a phone or recorder closer to the
speaker, while the camera track is only a guide — give it too:

```bash
python -m scripts.run_analysis --input "input/kajian-01.mp4" --audio "input/kajian-01-voice.m4a"
```

The offset is **measured, not asked for**, by matching the shape of loud and
quiet in both recordings. If the two are not the same take, or the clocks
drift, the audio is refused and the camera track is used instead — a
plausible-but-wrong offset would desynchronise every word while still looking
like it worked. Transcription, silence detection and the cut all then read the
aligned soundtrack.

Useful flags:

| Flag | Purpose |
| --- | --- |
| `--audio FILE` | A separately recorded soundtrack for the same take |
| `--slug NAME` | Project folder name (defaults to the filename) |
| `--only ingest,silence` | Run a subset of stages |
| `--start-from edl` | Re-run from one stage to the end |
| `--reuse` | Skip stages whose output already exists |
| `--model`, `--language`, `--device` | Override transcription settings for a test run; the config file stays the production source of truth |

Stages run in order:
`ingest → assets → transcribe → silence → edl → report → track → matte`.

`cut` is deliberately NOT in that default run. It needs a human approval
first, so it is asked for by name:

```bash
python -m scripts.run_analysis --only cut
```

It refuses, with exit code 5, while `approval.status` is anything but
`approved`.
The two video stages run last because they need only the video, and they are
the slowest — the approval checkpoint is ready to read while frames are still
being chewed.
The run stops immediately if validation finds a blocking problem, so a broken
file never costs a transcription pass.

---

## The approval checkpoint

`04-edl.json` starts with `approval.status: "pending"`. Every proposal carries
a status:

| Status | Meaning |
| --- | --- |
| `auto` | Conservative enough to apply without a decision |
| `review` | Genuinely ambiguous — yours to decide |
| `blocked` | The engine considered it and refused |

To approve: read `review/review-report.md`, set each `review` proposal to
`auto` (apply) or `blocked` (keep), then set `approval.status` to `approved`
with `approvedBy` and `approvedAt` filled in. No cutting stage may read the
EDL while the status is `pending`.

The EDL also carries two ready-made plans — `plans.autoApprovedOnly` and
`plans.allProposals` — each with keep-ranges, so you can see the runtime
impact of either choice before deciding.

---

## Tests

```bash
python -m tests.test_edl_logic       # 35 checks — editorial rules
```

```bash
python -m tests.test_runtime         # 17 checks — media and GPU plumbing
```

```bash
python -m tests.test_face_track      # 36 checks — face-track arithmetic
```

```bash
python -m tests.test_face_detection  # 16 checks — detection, end to end
```

```bash
python -m tests.test_matte           # 33 checks — matting, round-trip, real run
```

```bash
python -m tests.test_transliteration # 40 checks — scripture the transcript loses
```

```bash
python -m tests.test_rough_cut       # 22 checks — the approval gate and the cut
```

```bash
python -m tests.test_sync            # 16 checks — aligning a separate soundtrack
```

`test_edl_logic` runs 35 deterministic checks over a hand-built Indonesian
transcript containing an Arabic verse, a stutter, a repeated phrase, a
hesitation sound, a question followed by a long pause, and head/tail dead air.
No audio and no model needed, so the editorial rules are verified exactly
rather than approximately.

`test_runtime` generates audio with known silence and checks binary discovery,
the WAV decoder, the CUDA directory registration, and the silencedetect
parser — including a file that ends in silence, where ffmpeg emits
`silence_start` with no matching `silence_end`. Each of these guards a bug
that actually occurred while building this milestone.

For an end-to-end run against real media:

```bash
python -m tests.make_test_clip
python -m scripts.run_analysis --input "tests/fixtures/test-clip.mp4" --slug test-clip-en --model small --language en
```

The generated clip is **English**: this machine has only `en-US` speech
voices, so it exercises the media and transcription plumbing, not Indonesian
accuracy. Indonesian and Arabic behaviour is covered by `test_edl_logic.py`
and awaits a real recording.

---

## Composition layer (Remotion)

The groundwork and six effects exist. Compositions for the actual video come
later and depend on an approved EDL.

```bash
npm run check          # tsc --noEmit
```

```bash
npm run proof:arabic   # Arabic shaping
```

```bash
npm run proof:caption  # a full-size subtitle frame, Indonesian + Arabic
```

```bash
npm run proof:effects  # all six effects, plus 14 numeric checks
```

| Path | Purpose |
| --- | --- |
| `src/config/fonts.ts` | The three brand faces, the type scale, and the rules on where each may be used |
| `src/config/theme.ts` | The brand palette, the contrast rulings, and the only place a colour may be defined |
| `src/lib/` | Easing, the effect contract, layout zones, text measurement |
| `src/effects/` | The six vendored effects and the registry |
| `src/proofs/` | Compositions that exist to be looked at, not published |

Arabic rendering is **verified**, not assumed — see
[`docs/arabic-shaping.md`](docs/arabic-shaping.md). The short version: a font
without an Arabic subset still renders Arabic by falling back to a system
face, so missing coverage never looks broken, it just differs per machine.

The effects are derived from facecammaxxing, rewritten rather than copied —
see [`docs/effects.md`](docs/effects.md) for what was wrong in the original
for this use (Arabic laid out left-to-right, measurement that breaks React's
rules of hooks, a layout hard-coded to a vertical feed) and what each effect
still needs. `NOTICE` carries both upstream MIT notices.

Frame sizes come from `engine.config.json`, so the Python and TypeScript sides
cannot drift. The composition layer is the only place that deals in frames.

### The passes the effects depend on

Both now exist:

- **Face track** — where the face is, frame by frame, for framing and for
  keeping graphics off it. See [`docs/face-tracking.md`](docs/face-tracking.md).
- **Person matte** — the presenter separated from the room, so a `Behind`
  layer is genuinely behind them. See [`docs/person-matte.md`](docs/person-matte.md).

Capability is not the same as a usable result on one recording, and the code
keeps those apart. Every effect declares what it needs and `AVAILABLE` in
`src/effects/index.ts` records what the engine can produce — but
`fromArtefact()` in `src/lib/track.ts` and `src/lib/matte.ts` each refuse an
artefact whose `ok` is false, and `coveredAt()` answers whether the presenter
was actually found at a given moment. A gap is not a detail: a Behind layer
is not behind anything there.

## Not implemented yet

Stages 5–12 of the pipeline: rough cut, applying approved cuts, subtitles and
keyword highlights, B-roll and motion graphics planning, portrait and
landscape Remotion compositions, audio cleanup, rendering and final
inspection. Portrait (1080×1920) and landscape (1920×1080) will be separate
compositions — landscape will never be a crop of the portrait render.

The renderer that puts footage, matte and effects on one timeline: subtitles
and keyword highlights, camera moves, graphics, audio cleanup, and separate
portrait and landscape compositions. Everything it depends on now exists —
the face track, the matte, the effects and a cut to work from.
