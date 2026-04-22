"""Interval parsing and last-success persistence for hook throttling."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from meridian.lib.state.atomic import atomic_write_text
from meridian.lib.state.paths import RuntimePaths

_INTERVAL_PATTERN = re.compile(r"^(\d+)([smhd])$")
_INTERVAL_UNITS = {
    "s": timedelta(seconds=1),
    "m": timedelta(minutes=1),
    "h": timedelta(hours=1),
    "d": timedelta(days=1),
}


def parse_interval(interval: str) -> timedelta:
    """Parse an interval string like ``10m`` or ``1h``."""

    match = _INTERVAL_PATTERN.fullmatch(interval)
    if match is None:
        raise ValueError(f"Invalid interval format: {interval!r}. Expected '\\d+[smhd]'.")

    value = int(match.group(1))
    unit = match.group(2)
    return value * _INTERVAL_UNITS[unit]


class IntervalTracker:
    """Track and persist last successful hook execution timestamps."""

    def __init__(self, runtime_root: Path) -> None:
        self._state_path = RuntimePaths.from_root_dir(runtime_root).hook_state_json
        self._state = self._load_state()

    @property
    def state_path(self) -> Path:
        """Return the backing persistence path for interval state."""

        return self._state_path

    def _load_state(self) -> dict[str, str]:
        try:
            payload = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

        if not isinstance(payload, dict):
            return {}

        payload_dict = cast("dict[str, object]", payload)
        result: dict[str, str] = {}
        for key, value in payload_dict.items():
            if isinstance(value, str):
                result[key] = value
        return result

    def _save_state(self) -> None:
        atomic_write_text(
            self._state_path,
            json.dumps(self._state, indent=2, sort_keys=True) + "\n",
        )

    def should_run(self, hook_name: str, interval: str) -> bool:
        """Return True when the hook should run for the current event."""

        last_success_raw = self._state.get(hook_name)
        if last_success_raw is None:
            return True

        try:
            last_success = datetime.fromisoformat(last_success_raw)
            if last_success.tzinfo is None:
                last_success = last_success.replace(tzinfo=UTC)
            elapsed = datetime.now(UTC) - last_success
            return elapsed >= parse_interval(interval)
        except (TypeError, ValueError):
            return True

    def mark_run(self, hook_name: str) -> None:
        """Persist the current time as last successful run for a hook."""

        self._state[hook_name] = datetime.now(UTC).isoformat()
        self._save_state()
