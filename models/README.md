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
