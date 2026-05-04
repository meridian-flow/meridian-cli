"""Read-only bootstrap config loading helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from meridian.lib.config.settings import MeridianConfig
from meridian.lib.config.settings import load_config as _load_config
from meridian.lib.state.paths import load_context_config


def load_config(project_root: Path) -> MeridianConfig | None:
    """Load Meridian config for startup bootstrap without state mutation."""

    return _load_config(project_root)


def load_context_snapshot(project_root: Path) -> dict[str, Any] | None:
    """Load merged context config as serializable snapshot data, if configured."""

    context_config = load_context_config(project_root)
    if context_config is None:
        return None
    return context_config.model_dump(mode="json")
