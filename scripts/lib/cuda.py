"""Make pip-installed NVIDIA CUDA libraries loadable on Windows.

ctranslate2 loads `cublas64_12.dll` and the cuDNN DLLs through the ordinary
operating-system library search. The pip wheels (`nvidia-cublas-cu12`,
`nvidia-cudnn-cu12`) unpack them into `site-packages/nvidia/*/bin`, which
Windows does not search, and since Python 3.8 a process must register extra
DLL directories explicitly with `os.add_dll_directory()`.

On Linux the same wheels are found through RPATH, so this is a no-op there.

Call `enable_bundled_cuda()` before the first `import ctranslate2`; once that
module is loaded, adding directories no longer helps.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Kept so a second call is cheap and the directories are reported only once.
_handles: list[object] = []
_registered: list[str] = []
_done = False


def _package_roots() -> list[Path]:
    """Filesystem roots of the `nvidia` package.

    The CUDA wheels share `nvidia` as a *namespace* package, so it has no
    `__file__` (that attribute is None) and may be spread over several
    directories. `__path__` is the reliable source.
    """
    try:
        import nvidia  # noqa: PLC0415 - optional dependency
    except ImportError:
        return []

    if getattr(nvidia, "__file__", None):
        return [Path(nvidia.__file__).parent]
    return [Path(entry) for entry in getattr(nvidia, "__path__", [])]


def _library_dirs() -> list[Path]:
    """Directories inside the installed `nvidia` package that hold libraries."""
    pattern = "*.dll" if sys.platform == "win32" else "*.so*"

    found: list[Path] = []
    for root in _package_roots():
        if not root.is_dir():
            continue
        for component in sorted(root.iterdir()):
            if not component.is_dir():
                continue
            for subdir in ("bin", "lib"):
                candidate = component / subdir
                if candidate.is_dir() and any(candidate.glob(pattern)):
                    found.append(candidate)
    return found


def enable_bundled_cuda() -> list[str]:
    """Register the bundled CUDA library directories. Returns what was added.

    An empty list means either that the wheels are not installed or that the
    platform does not need this — in both cases the caller falls back to CPU
    rather than failing.
    """
    global _done
    if _done:
        return list(_registered)
    _done = True

    if sys.platform != "win32":
        return []

    for directory in _library_dirs():
        try:
            # The handle must be kept alive: dropping it un-registers the path.
            _handles.append(os.add_dll_directory(str(directory)))
        except OSError:
            continue
        _registered.append(str(directory))

        # Some loaders consult PATH instead of the DLL directory list.
        current = os.environ.get("PATH", "")
        if str(directory) not in current:
            os.environ["PATH"] = f"{directory}{os.pathsep}{current}"

    return list(_registered)
