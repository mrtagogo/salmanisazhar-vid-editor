# input/

Put source videos here. One video per analysis run.

With exactly one video in this folder you can run the pipeline without
arguments:

```bash
python -m scripts.run_analysis
```

With more than one, name the file:

```bash
python -m scripts.run_analysis --input "input/kajian-01.mp4"
```

Anything you put here is also picked up by the asset manifest as a
user-provided asset. The engine never references an asset that is not
actually on disk.
