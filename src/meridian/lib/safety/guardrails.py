"""Script-based post-run guardrails."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from meridian.lib.config.settings import MeridianConfig

if TYPE_CHECKING:
    from meridian.lib.types import SpawnId


DEFAULT_GUARDRAIL_TIMEOUT_SECONDS = MeridianConfig().guardrail_timeout_minutes * 60.0


@dataclass(frozen=True, slots=True)
class GuardrailFailure:
    """One failed guardrail execution."""

    script: str
    exit_code: int
    stderr: str


@dataclass(frozen=True, slots=True)
class GuardrailResult:
    """Aggregate result for a post-run guardrail pass."""

    ok: bool
    failures: tuple[GuardrailFailure, ...] = ()


def normalize_guardrail_paths(paths: tuple[str, ...], *, repo_root: Path) -> tuple[Path, ...]:
    """Resolve and validate guardrail script paths."""

    resolved: list[Path] = []
    for raw in paths:
        for candidate in raw.split(","):
            normalized = candidate.strip()
            if not normalized:
                continue
            path = Path(normalized)
            absolute = path if path.is_absolute() else (repo_root / path)
            absolute = absolute.expanduser().resolve()
            if not absolute.is_file():
                raise FileNotFoundError(f"Guardrail script not found: {normalized}")
            resolved.append(absolute)
    return tuple(resolved)


def run_guardrails(
    guardrails: tuple[Path, ...],
    *,
    spawn_id: SpawnId,
    cwd: Path,
    env: Mapping[str, str] | None,
    report_path: Path | None,
    output_log_path: Path,
    timeout_seconds: float = DEFAULT_GUARDRAIL_TIMEOUT_SECONDS,
) -> GuardrailResult:
    """Execute post-run guardrail scripts and collect failures."""

    if not guardrails:
        return GuardrailResult(ok=True)

    child_env = os.environ.copy()
    if env is not None:
        child_env.update(env)
    # Guardrails run untrusted repo scripts, so never pass Meridian secrets through.
    for key in tuple(child_env):
        if key.startswith("MERIDIAN_SECRET_"):
            child_env.pop(key, None)

    child_env["MERIDIAN_GUARDRAIL_RUN_ID"] = str(spawn_id)
    child_env["MERIDIAN_GUARDRAIL_OUTPUT_LOG"] = output_log_path.as_posix()
    if report_path is not None:
        child_env["MERIDIAN_GUARDRAIL_REPORT_PATH"] = report_path.as_posix()

    failures: list[GuardrailFailure] = []
    for script in guardrails:
        command = [str(script)]
        if not os.access(script, os.X_OK):
            command = ["bash", str(script)]

        try:
            try:
                completed = subprocess.run(
                    command,
                    cwd=cwd,
                    env=child_env,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=timeout_seconds,
                )
            except OSError:
                if command[0] == "bash":
                    raise
                completed = subprocess.run(
                    ["bash", str(script)],
                    cwd=cwd,
                    env=child_env,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=timeout_seconds,
                )
            if completed.returncode != 0:
                failures.append(
                    GuardrailFailure(
                        script=script.as_posix(),
                        exit_code=completed.returncode,
                        stderr=completed.stderr.strip() or completed.stdout.strip(),
                    )
                )
        except subprocess.TimeoutExpired as exc:
            failures.append(
                GuardrailFailure(
                    script=script.as_posix(),
                    exit_code=124,
                    stderr=f"Guardrail timed out after {timeout_seconds:.1f}s: {exc}",
                )
            )

    return GuardrailResult(ok=not failures, failures=tuple(failures))
