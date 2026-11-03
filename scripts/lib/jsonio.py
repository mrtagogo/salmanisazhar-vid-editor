"""JSON helpers shared by the analysis stages."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    """ISO-8601 UTC stamp, recorded in every artefact for traceability."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return path


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(
            f"Required analysis artefact is missing: {path}\n"
            "Run the earlier pipeline stage first."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def rounded(value: float, digits: int = 3) -> float:
    """Round a seconds value; keeps JSON readable without losing frame accuracy."""
    return round(float(value), digits)
