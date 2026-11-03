# Face tracking

The `track` stage writes `data/06-face-track.json`: where the presenter's face
is, frame by frame. Two things need it — framing a punch-in, and keeping
captions and graphics off the face. The second is an editorial promise, so a
track the engine is not confident about has to say so rather than quietly
supplying plausible numbers.

```bash
python -m scripts.run_analysis --input "input/kajian-01.mp4" --only ingest,track
```

```bash
python -m tests.test_face_track      # 36 checks — the arithmetic
```

```bash
python -m tests.test_face_detection  # 16 checks — end to end, known trajectory
```

## Decisions

**YuNet, not mediapipe.** mediapipe is what the reference effects library
uses, and it was the obvious choice until it turned out that mediapipe 1.2.0
has dropped the legacy bundled solutions and ships **no model files at all** —
so it needs a download exactly like anything else. With that advantage gone,
what remained was its weight: thirteen packages, including matplotlib and
sounddevice, to find a rectangle. YuNet is one 232 KB model read through
OpenCV, which was already being pulled in anyway.

**ffmpeg stays the only decoder.** OpenCV can open a video itself, and it
would be two fewer moving parts. But the transcript side already decodes
through ffmpeg, and two decoders disagree about frame timing on
variable-frame-rate footage — which is most phone recordings. A face track
that drifts against the transcript would put a caption on the wrong word. So
frames are piped from ffmpeg as raw bytes, and `sample_frames` keeps the media
layer free of numpy by handing the caller bytes to reshape.

**Detect at 10 fps, build at 30.** A head does not move meaningfully between
two frames a thirtieth of a second apart. Detecting ten times a second and
interpolating is roughly three times faster and gives a steadier result,
because the interpolation itself removes per-frame jitter.

**Median first, then smooth.** A detector occasionally returns one badly wrong
box. Smoothing would average that error into its neighbours and spread it; a
median-of-three throws it away before anything else sees it.

**Smoothing runs forwards and then backwards.** A single exponential pass
lags, and a camera that lags behind the head looks like a late operator.
Running the filter back over its own output cancels the delay. The test for
this asserts the lag explicitly: a one-pass filter on a step lands below 0.5,
the two-pass version is centred on it.

**Gaps are recorded, not hidden.** Where the presenter turns away, the track
holds the last known position so every frame has a value — but each such
stretch is listed in `gaps`. Inside a gap the face position is held, not
known, and nothing may claim to be keeping clear of a face it cannot see. The
tail after the final detection counts as a gap too.

## The crown, and how it was measured

`top` is the crown of the head — hair, and whatever is worn on it. No
detector reports that: a face box runs from about the brow to the chin, and
everything above it is inferred. The engine places the crown
`headTopAboveCentre` face-widths above the box centre.

That started as a guess of **0.75**, flagged as the first number to check
against real footage. The first real recording showed the guess was badly
wrong, and in the predicted direction: the presenter wears a peci, and the
crown line landed **94 px inside his head**, crossing the cap instead of
clearing it.

It did not have to stay a guess, because the **matte knows**. Its topmost
solid pixel above the face is the real top of the head, cap included. Two
independent passes, one calibrating the other:

| | |
| --- | --- |
| Samples | 78, spread across 2.6 minutes |
| Measured ratio | mean 1.102, median 1.098 |
| Middle 80% | 1.063 – 1.156 |
| Error at 0.75 | +94 px mean (7.4% of frame height), inside the head |
| Error at 1.10 | +0.5 px mean |

The default is now **1.1**. Erring high is the safe direction: too high and a
word placed to straddle the crown floats slightly above the head, too low and
it lies across the face, which the rules forbid.

Re-measure for a presenter who wears nothing on their head — the method is
just the comparison above, and it needs a matte for the same clip.

The proper fix is to stop estimating: read the crown from the matte directly.
That is not done yet because the track runs before the matte, and reordering
them is a change to make deliberately rather than in passing.

## What is verified, and what is not

`test_face_track` covers the arithmetic with hand-built samples: outlier
rejection, interpolation, zero-phase smoothing, gap detection,
normalisation, the empty case, and the refusal of nonsensical inputs.

`test_face_detection` generates a clip in which a face is **drawn** along a
known path, then checks the track comes back with that path. It exists
because of one specific blind spot: if frames were reshaped wrongly, or
detections were not scaled back from the 640-wide detection frame to source
pixels, the detector would simply find nothing — which is indistinguishable
from a clip with no face in it. The test asserts the track starts at 0.35 and
ends at 0.65 of the frame width, so a missing scale-back fails loudly.

**On real footage.** A 2.6-minute recording of the presenter — glasses, a
beard, a white peci against a pale wall — gave 100% coverage, no gaps, and a
mean detection score of 0.927. The boxes were checked by eye at three moments
across the clip, not just counted.

Still unexercised: a profile turn, backlighting, a second person in shot, and
anything shot in a different room.

### Rotation, which real footage caught at once

The clip was recorded on a phone held upright: stored as 1920x1080 with a
90-degree display matrix, so ffmpeg hands out 1080x1920 on decode. Ingest
recorded only the stored size, so the stage asked ffmpeg to scale a portrait
frame into a landscape box and matted a squashed picture.

Metadata now carries `displayWidth` and `displayHeight` alongside the stored
size, and every stage that works on pixels uses those. `orientation` is
computed from them too — it previously called this portrait clip "landscape",
and the warning about needing a 1.78x upscale for a portrait crop was wrong
for the same reason. None of the synthetic fixtures had rotation metadata, so
nothing before this caught it.

## Still missing: the person matte

Face tracking was one of the two passes the composition layer needs. The other
is an alpha cut-out of the presenter, so that a `Behind` layer is actually
behind the body. Without it `text-behind` places a large word across the
presenter's face, which is why it stays refused — see
[`docs/effects.md`](effects.md).
