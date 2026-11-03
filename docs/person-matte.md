# Person matte

The `matte` stage writes `cache/matte.mp4` and `data/07-person-matte.json`.
The matte is what makes a graphic go **behind** the presenter rather than
across them. Without it, `text-behind` puts a large word over a face — so
this pass is not a visual nicety, it is the thing that makes one of the six
effects permissible at all.

```bash
python -m scripts.run_analysis --input "input/kajian-01.mp4" --only ingest,matte
```

```bash
python -m tests.test_matte   # 33 checks
```

## The matte is greyscale, and deliberately not a transparent video

A transparent video would carry the presenter's colour as well as their
alpha. That means re-encoding the presenter's pixels a second time and
storing them twice, while the source already holds them at full quality.

So the matte stores one thing — **where the presenter is** — as a greyscale
video whose luma is the alpha. The renderer composites the original source
through it, and the source stays the only place the presenter's colour lives.

This forced a detail that would otherwise have gone unnoticed. H.264 normally
stores luma in the broadcast 16–235 range. A matte squeezed into that range
comes back with solid alpha at about 0.92 and empty alpha at about 0.06: the
presenter renders slightly see-through, with the background faintly visible
through them, in a way that looks like a bad matte rather than a bad encode.
The stage therefore writes full-range H.264, and `test_matte.py` encodes a
known pattern and decodes it back to prove it — empty returns below 6/255,
solid above 249/255.

## RobustVideoMatting

| | |
| --- | --- |
| Model | `rvm_mobilenetv3_fp32.onnx`, 14.3 MB |
| Licence | **GPL-3.0** — see [`NOTICE`](../NOTICE) |
| Runtime | onnxruntime, CPU |

RVM is **recurrent**: each frame's result feeds into the next, which is what
stops the matte's edge crawling between frames. Two consequences are load
bearing. Frames must be processed strictly in order, and a session's state
must never be carried across clips — `Matter.reset()` exists for that.

Measured on this machine, CPU only:

| Working size | ms/frame | per minute of 30 fps video |
| --- | --- | --- |
| 512 x 288 | 11 | 20 s |
| 640 x 360 | 15 | 28 s |
| 960 x 540 | 19 | 34 s |
| 1080 x 1920 | 75 | 136 s |

The default is `longEdge: 1280`, which puts a 1080x1920 source at 720x1280.
A forty-minute kajian is then roughly half an hour of matting. Raise it for
quality, lower it for speed; the alpha is upscaled to the output size either
way.

## Why not something permissive

PPHumanSeg in opencv_zoo is Apache-2.0 and would have matched the licence of
everything else here. Its input is 192x192, which gives a soft blob rather
than an edge — adequate for hiding a word behind a torso, not for hair.

The choice between a clean licence and a usable edge was put to the
repository owner, who chose RVM knowing the licence. `NOTICE` records what
that does and does not mean, and the model is a config value: point
`analysis.personMatte.model` at something else and the stage uses it.

## What is verified

`test_matte.py` covers the arithmetic (sizing, quantising, coverage, gap
summarising, and the refusal of nonsensical input), the video round-trip
described above, and a real run.

The real run matters, and it works differently from the face-track test. A
**drawn** stand-in is useless here: RVM is trained on photographs, and on a
cartoon it returns almost nothing — alpha peaking at 0.8 with half a percent
of pixels solid, against a real frame's full 0-to-1 range. So the test runs
against talking-head footage in `_ref/`, checks the presenter occupies a
plausible share of the frame, then reads the matte video back and asserts
that a frame corner is background and the middle of the body is solid.

`_ref/` is a reference checkout and is not committed, so this group skips on
a fresh clone. The arithmetic and round-trip groups still run.

## On the presenter's own footage

A 2.6-minute recording — a white peci against a pale wall, glasses, a dark
satin garment, a hand held up near the chin — came back clean: 4,665 frames,
mean coverage 51.0% (min 50.4%, max 52.3%), no empty stretches, no warnings.
Checked by eye at three moments, composited over a flat colour: the cap edge,
the spectacle frames, the beard and the raised hand all cut correctly.

The steadiness of that coverage figure is itself worth noting — it varies by
under two points across the whole clip, which is what a stable matte looks
like.

The matte also turned out to be good enough to **calibrate the face track**:
its topmost solid pixel is the real top of the head, which is how the crown
estimate was corrected from a guess to a measurement. See
[`docs/face-tracking.md`](face-tracking.md).

## What is still not verified

Backlighting, a dark garment against a dark wall, a busy background, hands
crossing the face, a second person in shot, and any other room. The artefact
reports `meanCoverage`, gaps and warnings precisely so a new recording can be
judged quickly rather than trusted.

Inside a gap the matte found nobody. A Behind layer is not behind anything
there, and `coveredAt()` in [`src/lib/matte.ts`](../src/lib/matte.ts) is how a
composition asks before placing something.
