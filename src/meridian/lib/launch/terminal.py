"""Terminal event filtering and formatting for harness stream output."""

from __future__ import annotations

import sys
from typing import TextIO

from meridian.lib.config.settings import OutputConfig
from meridian.lib.harness.adapter import StreamEvent

ALL_EVENT_CATEGORIES = frozenset(
    {
        "lifecycle",
        "sub-run",
        "tool-use",
        "thinking",
        "assistant",
        "error",
        "progress",
        "system",
    }
)
DEFAULT_VISIBLE_CATEGORIES = frozenset({"lifecycle", "sub-run", "error"})
QUIET_VISIBLE_CATEGORIES = frozenset({"lifecycle", "error"})
VERBOSE_VISIBLE_CATEGORIES = ALL_EVENT_CATEGORIES


def resolve_visible_categories(
    *,
    verbose: bool,
    quiet: bool,
    config: OutputConfig | None = None,
) -> frozenset[str]:
    """Return terminal-visible categories from CLI verbosity flags."""

    if verbose:
        return VERBOSE_VISIBLE_CATEGORIES
    if quiet:
        return QUIET_VISIBLE_CATEGORIES
    if config is None:
        return DEFAULT_VISIBLE_CATEGORIES

    preset = (config.verbosity or "").strip().lower()
    if preset == "quiet":
        return QUIET_VISIBLE_CATEGORIES
    if preset == "normal":
        return _normalize_visible_categories(OutputConfig().show)
    if preset in {"verbose", "debug"}:
        return VERBOSE_VISIBLE_CATEGORIES
    return _normalize_visible_categories(config.show)


class TerminalEventFilter:
    """Emit categorized stream events to a terminal stream."""

    def __init__(
        self,
        *,
        visible_categories: frozenset[str] = DEFAULT_VISIBLE_CATEGORIES,
        output_stream: TextIO | None = None,
        root_depth: int = 0,
    ) -> None:
        self._visible_categories = visible_categories
        self._output_stream = output_stream or sys.stderr
        self._root_depth = max(root_depth, 0)

    def observe(self, event: StreamEvent) -> None:
        if event.category not in self._visible_categories:
            return

        rendered = self._format_event(event)
        if rendered is None:
            return
        self._output_stream.write(f"{rendered}\n")
        self._output_stream.flush()

    def _format_event(self, event: StreamEvent) -> str | None:
        text = _normalize_text(event.text) or _normalize_text(event.raw_line) or event.event_type
        if not text:
            return None
        if event.category == "sub-run":
            return f"{self._subrun_prefix(event)}{text}"
        return text

    def _subrun_prefix(self, event: StreamEvent) -> str:
        metadata_depth = _coerce_int(event.metadata.get("depth") or event.metadata.get("d"))
        event_depth = metadata_depth if metadata_depth is not None else self._root_depth + 1
        relative_depth = max(event_depth - self._root_depth, 1)
        return f"{'  ' * (relative_depth - 1)}├─ "


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    compact = " ".join(value.split())
    return compact or None


def _coerce_int(value: object) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return int(stripped)
        except ValueError:
            return None
    return None


def _normalize_visible_categories(categories: tuple[str, ...]) -> frozenset[str]:
    return frozenset(item for item in categories if item in ALL_EVENT_CATEGORIES)


def summarize_stderr(stderr_text: str, *, max_chars: int = 220) -> str | None:
    """Return one concise stderr summary line for default verbosity output."""

    lines = [" ".join(line.split()) for line in stderr_text.splitlines() if line.strip()]
    if not lines:
        return None
    preferred = next(
        (line for line in lines if any(token in line.lower() for token in ("error", "failed"))),
        lines[0],
    )
    if len(preferred) <= max_chars:
        return preferred
    return f"{preferred[: max_chars - 3].rstrip()}..."


def format_stderr_for_terminal(
    stderr_text: str,
    *,
    verbose: bool,
    quiet: bool,
) -> str | None:
    """Format harness stderr according to CLI verbosity tiers."""

    normalized = stderr_text.strip()
    if not normalized or quiet:
        return None
    if verbose:
        return normalized
    summary = summarize_stderr(normalized)
    if summary is None:
        return None
    return f"harness stderr: {summary}"
