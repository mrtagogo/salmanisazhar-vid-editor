"""Per-project directory layout.

One source video == one project folder under projects/. Analysis stages only
ever write inside that folder, so a project can be deleted or re-run in
isolation without touching the engine itself.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .config import ENGINE_ROOT

INPUT_DIR = ENGINE_ROOT / "input"
PROJECTS_DIR = ENGINE_ROOT / "projects"


def slugify(name: str) -> str:
    """Turn a filename into a filesystem-safe project slug."""
    text = unicodedata.normalize("NFKD", name)
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "project"


@dataclass(frozen=True)
class ProjectPaths:
    """Resolved locations for a single video project."""

    slug: str
    root: Path
    data: Path
    cache: Path
    review: Path

    # --- analysis artefacts (timestamps inside these files are in SECONDS) ---
    @property
    def metadata(self) -> Path:
        return self.data / "01-metadata.json"

    @property
    def transcript(self) -> Path:
        return self.data / "02-transcript.json"

    @property
    def silence(self) -> Path:
        return self.data / "03-silence.json"

    @property
    def edl(self) -> Path:
        return self.data / "04-edl.json"

    @property
    def face_track(self) -> Path:
        return self.data / "06-face-track.json"

    @property
    def person_matte(self) -> Path:
        return self.data / "07-person-matte.json"

    @property
    def asset_manifest(self) -> Path:
        return self.data / "asset-manifest.json"

    @property
    def audio_wav(self) -> Path:
        return self.cache / "audio-16k-mono.wav"

    @property
    def matte_video(self) -> Path:
        """Greyscale video: luma IS the alpha. See s07_person_matte."""
        return self.cache / "matte.mp4"

    @property
    def review_report(self) -> Path:
        return self.review / "review-report.md"

    def ensure(self) -> None:
        for directory in (self.data, self.cache, self.review):
            directory.mkdir(parents=True, exist_ok=True)


def project_paths(source: Path, slug: str | None = None) -> ProjectPaths:
    """Build the project layout for a source video."""
    resolved_slug = slug or slugify(source.stem)
    root = PROJECTS_DIR / resolved_slug
    return ProjectPaths(
        slug=resolved_slug,
        root=root,
        data=root / "data",
        cache=root / "cache",
        review=root / "review",
    )
