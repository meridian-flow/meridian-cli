"""Alias parsing and merge helpers for the model catalog.

Model aliases are resolved exclusively via mars packages.
Meridian has ZERO builtin alias definitions — all aliases come from
mars dependency packages (via .mars/models-merged.json) and consumer
config (via mars.toml [models]).
"""

from __future__ import annotations

import contextlib
import json
import logging
import shutil
import subprocess
import sys
from pathlib import Path
from typing import cast

from pydantic import BaseModel, ConfigDict, Field

from meridian.lib.catalog.model_policy import pattern_fallback_harness
from meridian.lib.core.types import HarnessId, ModelId

logger = logging.getLogger(__name__)


class AliasEntry(BaseModel):
    """Alias entry for model lookup."""

    model_config = ConfigDict(frozen=True)

    alias: str
    model_id: ModelId
    resolved_harness: HarnessId | None = Field(default=None, exclude=True)
    description: str | None = Field(default=None, exclude=True)

    @property
    def harness(self) -> HarnessId:
        if self.resolved_harness is not None:
            return self.resolved_harness
        return pattern_fallback_harness(str(self.model_id))

    def format_text(self, ctx: object | None = None) -> str:
        _ = ctx
        from meridian.cli.format_helpers import kv_block

        pairs: list[tuple[str, str | None]] = [
            ("Model", str(self.model_id)),
            ("Harness", str(self.harness)),
            ("Alias", self.alias or None),
        ]
        return kv_block(pairs)


def entry(
    *,
    alias: str,
    model_id: str,
    harness: str | None = None,
    description: str | None = None,
) -> AliasEntry:
    resolved_harness: HarnessId | None = None
    if harness:
        with contextlib.suppress(ValueError):
            resolved_harness = HarnessId(harness)
    return AliasEntry(
        alias=alias,
        model_id=ModelId(model_id),
        resolved_harness=resolved_harness,
        description=description,
    )


# ---------------------------------------------------------------------------
# Mars integration
# ---------------------------------------------------------------------------

def _resolve_mars_binary() -> str | None:
    """Find the mars binary, preferring the one from the same install environment."""
    scripts_dir = Path(sys.executable).parent
    for name in ("mars", "mars.exe"):
        candidate = scripts_dir / name
        if candidate.is_file():
            return str(candidate)
    return shutil.which("mars")


def _run_mars_models_list(repo_root: Path | None = None) -> list[dict[str, object]] | None:
    """Call ``mars models list --json`` and return the alias entries.

    Returns *None* when the mars binary is unavailable or the command fails,
    so the caller can fall back to reading the cached merged file.
    """
    mars_bin = _resolve_mars_binary()
    if mars_bin is None:
        return None

    cmd = [mars_bin, "models", "list", "--json"]
    if repo_root is not None:
        cmd.extend(["--root", str(repo_root)])

    try:
        # mars may do a cold models.dev fetch in ensure_fresh(Auto); mars caps each HTTP
        # phase at 15s (connect + recv-response + recv-body), so worst-case cold fetch is
        # ~45s. 60s leaves a small headroom for first-boot DNS, slow disks, and startup.
        # Use the same timeout as run_mars_models_resolve since both paths can refresh.
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        logger.debug("mars binary not available or timed out", exc_info=True)
        return None

    if result.returncode != 0:
        logger.debug("mars models list failed (rc=%d): %s", result.returncode, result.stderr)
        return None

    try:
        payload = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        logger.debug("mars models list returned invalid JSON")
        return None

    aliases = payload.get("aliases")
    if not isinstance(aliases, list):
        return None
    return cast("list[dict[str, object]]", aliases)


def _extract_mars_error_message(raw_output: str) -> str | None:
    """Extract a readable error message from mars stdout/stderr text."""
    output = raw_output.strip()
    if not output:
        return None

    try:
        payload = json.loads(output)
    except (json.JSONDecodeError, ValueError):
        return output

    if isinstance(payload, dict):
        typed_payload = cast("dict[str, object]", payload)
        error = typed_payload.get("error")
        if isinstance(error, str) and error.strip():
            return error.strip()
        message = typed_payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()

    return output


def _is_unknown_alias_error(message: str | None) -> bool:
    if message is None:
        return False
    return "unknown alias" in message.lower()


def run_mars_models_resolve(
    name: str,
    repo_root: Path | None = None,
) -> dict[str, object] | None:
    """Call ``mars models resolve <name> --json`` and return the resolved entry.

    Returns ``None`` when the alias is unknown (mars exit code 1).
    Raises ``RuntimeError`` when mars is unavailable or broken - mars is
    always bundled with meridian, so absence is a hard error.
    """
    mars_bin = _resolve_mars_binary()
    if mars_bin is None:
        raise RuntimeError(
            "Mars binary not found. Mars is required for model resolution. "
            "Run 'meridian doctor' to diagnose."
        )
    cmd = [mars_bin, "models", "resolve", name, "--json"]
    if repo_root is not None:
        cmd.extend(["--root", str(repo_root)])
    try:
        # mars may do a cold models.dev fetch in ensure_fresh(Auto); mars caps each HTTP
        # phase at 15s (connect + recv-response + recv-body), so worst-case cold fetch is
        # ~45s. 60s leaves a small headroom for first-boot DNS, slow disks, and startup.
        # Use the same timeout as _run_mars_models_list since both paths can refresh.
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Mars binary not found. Mars is required for model resolution. "
            "Run 'meridian doctor' to diagnose."
        ) from exc
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.debug("mars models resolve failed: %s", exc, exc_info=True)
        raise RuntimeError(
            "Mars model resolution failed. Run 'meridian doctor' to diagnose."
        ) from exc
    if result.returncode != 0:
        stderr_message = _extract_mars_error_message(result.stderr)
        stdout_message = _extract_mars_error_message(result.stdout)
        error_message = stderr_message or stdout_message
        logger.debug(
            "mars models resolve '%s' exited %d: stderr=%r stdout=%r",
            name,
            result.returncode,
            result.stderr,
            result.stdout,
        )
        if _is_unknown_alias_error(error_message):
            return None

        if error_message:
            raise RuntimeError(f"Mars model resolution failed: {error_message}")
        raise RuntimeError(
            f"Mars model resolution failed: mars exited with status {result.returncode}."
        )
    try:
        payload = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        logger.debug("mars models resolve returned invalid JSON for '%s'", name)
        return None
    if not isinstance(payload, dict):
        logger.debug("mars models resolve returned non-object JSON for '%s'", name)
        return None
    return cast("dict[str, object]", payload)


def _read_mars_merged_file(repo_root: Path | None = None) -> dict[str, object]:
    """Read ``.mars/models-merged.json`` directly (dep-only aliases).

    Falls back to empty dict if the file doesn't exist or is invalid.
    """
    search_dirs: list[Path] = []
    if repo_root is not None:
        search_dirs.append(repo_root)
    search_dirs.append(Path.cwd())

    for root in search_dirs:
        merged_path = root / ".mars" / "models-merged.json"
        if merged_path.is_file():
            try:
                raw = json.loads(merged_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    return cast("dict[str, object]", raw)
            except (OSError, json.JSONDecodeError, ValueError):
                logger.debug("Failed to read %s", merged_path, exc_info=True)
    return {}


def _mars_list_to_entries(aliases_list: list[dict[str, object]]) -> list[AliasEntry]:
    """Convert mars ``models list --json`` alias entries to :class:`AliasEntry` objects."""
    entries: list[AliasEntry] = []
    for item in aliases_list:
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            continue

        resolved_model = item.get("model_id") or item.get("resolved_model")
        harness = item.get("harness")
        description = item.get("description")

        # Skip aliases that didn't resolve to a concrete model ID
        if not isinstance(resolved_model, str) or not resolved_model.strip():
            continue

        entries.append(entry(
            alias=name.strip(),
            model_id=resolved_model.strip(),
            harness=str(harness) if isinstance(harness, str) else None,
            description=str(description) if isinstance(description, str) else None,
        ))

    return entries


def _mars_merged_to_entries(merged: dict[str, object]) -> list[AliasEntry]:
    """Convert ``.mars/models-merged.json`` raw data to :class:`AliasEntry` objects.

    For pinned aliases, the model ID is stored directly.  For auto-resolve aliases,
    only the harness and description are available — the model ID is unknown
    without the models cache, so these are skipped.
    """
    entries: list[AliasEntry] = []
    for alias_name, alias_data in merged.items():
        if not isinstance(alias_data, dict):
            continue
        typed_data = cast("dict[str, object]", alias_data)

        # Pinned alias: has a "model" key
        model_id = typed_data.get("model")
        if isinstance(model_id, str) and model_id.strip():
            harness = typed_data.get("harness")
            description = typed_data.get("description")
            entries.append(entry(
                alias=alias_name,
                model_id=model_id.strip(),
                harness=str(harness) if isinstance(harness, str) else None,
                description=str(description) if isinstance(description, str) else None,
            ))
        # Auto-resolve aliases without the cache can't be resolved here
        # — they need mars models list which runs auto-resolve against the cache

    return entries


def load_mars_aliases(repo_root: Path | None = None) -> list[AliasEntry]:
    """Load model aliases from mars.

    Prefers ``mars models list --json`` for the full resolved view
    (includes consumer overrides + auto-resolution).  Falls back to
    reading ``.mars/models-merged.json`` if the mars binary isn't available.
    """
    # Try mars CLI first — it returns fully resolved aliases
    mars_list = _run_mars_models_list(repo_root)
    if mars_list is not None:
        entries = _mars_list_to_entries(mars_list)
        if entries:
            return sorted(entries, key=lambda e: e.alias)

    # Fallback: read the cached dependency file directly
    merged = _read_mars_merged_file(repo_root)
    if merged:
        entries = _mars_merged_to_entries(merged)
        if entries:
            return sorted(entries, key=lambda e: e.alias)

    return []


def load_mars_descriptions(repo_root: Path | None = None) -> dict[str, str]:
    """Load model descriptions from mars aliases.

    Returns a dict keyed by model_id with description values.
    """
    descriptions: dict[str, str] = {}

    # Try mars CLI first
    mars_list = _run_mars_models_list(repo_root)
    if mars_list is not None:
        for item in mars_list:
            resolved_model = item.get("model_id") or item.get("resolved_model")
            description = item.get("description")
            if (
                isinstance(resolved_model, str)
                and resolved_model.strip()
                and isinstance(description, str)
                and description.strip()
            ):
                descriptions[resolved_model.strip()] = description.strip()
        return descriptions

    # Fallback: read merged file
    merged = _read_mars_merged_file(repo_root)
    for alias_data in merged.values():
        if not isinstance(alias_data, dict):
            continue
        typed_data = cast("dict[str, object]", alias_data)
        model_id = typed_data.get("model")
        description = typed_data.get("description")
        if (
            isinstance(model_id, str)
            and model_id.strip()
            and isinstance(description, str)
            and description.strip()
        ):
            descriptions[model_id.strip()] = description.strip()

    return descriptions
