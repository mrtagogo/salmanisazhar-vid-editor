# Models

Third-party model files live here. **They are not committed** — `.gitignore`
excludes `*.onnx` — because they are binaries belonging to another project,
with their own licence and their own release cadence.

Get them by running the download below. Nothing in the engine downloads
anything on its own.

## face_detection_yunet_2023mar.onnx

Face detection, used by the `track` stage. YuNet, from
[opencv_zoo](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet).

| | |
| --- | --- |
| Size | 232,589 bytes |
| SHA-256 | `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4` |
| Licence | MIT (opencv_zoo) |

The file is stored in opencv_zoo with git-lfs, so the ordinary `raw.github`
URL returns a 131-byte pointer rather than the model. Use the media endpoint:

```bash
curl -L --fail -o models/face_detection_yunet_2023mar.onnx "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
```

Then check it against the hash above — a truncated or substituted model is
otherwise indistinguishable from a bad one:

```bash
python -c "import hashlib,pathlib;p=pathlib.Path('models/face_detection_yunet_2023mar.onnx');print(hashlib.sha256(p.read_bytes()).hexdigest())"
```

If the model is missing, the `track` stage fails and says so. It does not fall
back to a weaker detector, because a quietly worse face track means captions
and graphics drifting onto the presenter's face.

## rvm_mobilenetv3_fp32.onnx

Person matting, used by the `matte` stage. RobustVideoMatting, from
[PeterL1n/RobustVideoMatting](https://github.com/PeterL1n/RobustVideoMatting).

| | |
| --- | --- |
| Size | 14,975,696 bytes |
| SHA-256 | `88d4531297118f595bf2fd60f6f566aec2e559393802d1f436c380f0cbbd2828` |
| Licence | **GPL-3.0** — read the note in [`NOTICE`](../NOTICE) before relying on it |

```bash
curl -L --fail -o models/rvm_mobilenetv3_fp32.onnx "https://github.com/PeterL1n/RobustVideoMatting/releases/download/v1.0.0/rvm_mobilenetv3_fp32.onnx"
```

```bash
python -c "import hashlib,pathlib;p=pathlib.Path('models/rvm_mobilenetv3_fp32.onnx');print(hashlib.sha256(p.read_bytes()).hexdigest())"
```

A caveat about that checksum, which the YuNet one does not have: YuNet is
stored with git-lfs, and its pointer file publishes the hash upstream, so the
download can be checked against something the project itself states. This is a
release binary with no published hash. The value above is what was downloaded
and verified to work here. It protects future downloads from corruption or
substitution; it is not independent proof of what upstream intended.

Permissive alternative: `human_segmentation_pphumanseg_2023mar.onnx` in
opencv_zoo is Apache-2.0 and about 5.9 MB, but its input is 192x192, so the
silhouette is soft — enough to hide a graphic behind a body, not enough for
fine edges or background replacement.
