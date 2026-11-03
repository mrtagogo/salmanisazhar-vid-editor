"""Engine configuration loading.

All tunable behaviour lives in engine.config.json so the pipeline stays
configuration-driven: no editorial threshold is hard-coded in a stage.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ENGINE_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ENGINE_ROOT / "engine.config.json"
LOCAL_CONFIG_PATH = ENGINE_ROOT / "engine.config.local.json"


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge override into base recursively, returning a new dict."""
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config() -> dict[str, Any]:
    """Load engine.config.json, overlaid by engine.config.local.json if present.

    The local file is for machine-specific values (e.g. an explicit ffmpeg
    path) that should not be part of the shared engine definition.
    """
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Engine config not found: {CONFIG_PATH}")

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    if LOCAL_CONFIG_PATH.exists():
        local = json.loads(LOCAL_CONFIG_PATH.read_text(encoding="utf-8"))
        config = _deep_merge(config, local)

    return config


def get(config: dict, dotted_path: str, default: Any = None) -> Any:
    """Read a nested config value by dotted path, e.g. 'analysis.silence.noiseFloorDb'."""
    node: Any = config
    for part in dotted_path.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def cutting_profile(config: dict) -> dict:
    """Return the cutting parameters for the active cutting standard."""
    standard = get(config, "editingIdentity.cutting", "balanced")
    profile = get(config, f"cutting.{standard}")
    if profile is None:
        raise ValueError(
            f"Cutting standard '{standard}' has no parameter block under 'cutting'."
        )
    return profile
