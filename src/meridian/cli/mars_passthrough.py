"""Mars CLI passthrough helpers for the meridian CLI."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, TextIO

from meridian.lib.ops.mars import (
    UpgradeAvailability,
    check_upgrade_availability,
    format_upgrade_availability,
    resolve_mars_executable,
)

if TYPE_CHECKING:
    from pydantic import BaseModel


@dataclass(frozen=True)
class MarsPassthroughRequest:
    command: tuple[str, ...]
    mars_args: tuple[str, ...]
    is_sync: bool
    wants_json: bool
    root_override: Path | None


@dataclass(frozen=True)
class MarsPassthroughResult:
    request: MarsPassthroughRequest
    returncode: int
    stdout_text: str = ""
    stderr_text: str = ""


def mars_requested_json(args: Sequence[str]) -> bool:
    return any(token == "--json" for token in args)


def mars_requested_root(args: Sequence[str]) -> Path | None:
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--root":
            next_value = args[index + 1].strip() if index + 1 < len(args) else ""
            if next_value:
                return Path(next_value)
            index += 2
            continue
        if token.startswith("--root="):
            candidate = token.partition("=")[2].strip()
            if candidate:
                return Path(candidate)
        index += 1
    return None


def mars_subcommand(args: Sequence[str]) -> str | None:
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--":
            return None
        if token == "--root":
            index += 2
            continue
        if token.startswith("--root="):
            index += 1
            continue
        if token.startswith("-"):
            index += 1
            continue
        return token
    return None


def inject_upgrade_hint_into_sync_json(
    raw_stdout: str,
    *,
    within_constraint: tuple[str, ...],
    beyond_constraint: tuple[str, ...],
) -> str:
    stripped = raw_stdout.strip()
    if not stripped:
        return raw_stdout
    try:
        parsed = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return raw_stdout
    if not isinstance(parsed, dict):
        return raw_stdout
    parsed["upgrade_hint"] = {
        "within_constraint": list(within_constraint),
        "beyond_constraint": list(beyond_constraint),
    }
    rendered = json.dumps(parsed)
    if raw_stdout.endswith("\n"):
        rendered += "\n"
    return rendered


def decode_json_values(raw_stdout: str) -> list[object] | None:
    decoder = json.JSONDecoder()
    parsed_values: list[object] = []
    index = 0
    while index < len(raw_stdout):
        while index < len(raw_stdout) and raw_stdout[index].isspace():
            index += 1
        if index >= len(raw_stdout):
            return parsed_values
        try:
            parsed, index = decoder.raw_decode(raw_stdout, index)
        except json.JSONDecodeError:
            return None
        parsed_values.append(parsed)
    return parsed_values


def parse_mars_passthrough(
    args: Sequence[str],
    *,
    output_format: str | None = None,
    executable: str,
) -> MarsPassthroughRequest:
    """Build an executable Mars passthrough request without side effects."""

    mars_args = list(args)
    is_sync = mars_subcommand(mars_args) == "sync"
    wants_json = mars_requested_json(mars_args) or output_format == "json"
    if wants_json and not mars_requested_json(mars_args):
        mars_args = ["--json", *mars_args]
    return MarsPassthroughRequest(
        command=(executable, *mars_args),
        mars_args=tuple(mars_args),
        is_sync=is_sync,
        wants_json=wants_json,
        root_override=mars_requested_root(mars_args),
    )


def execute_mars_passthrough(
    request: MarsPassthroughRequest,
    *,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    stderr: TextIO | None = None,
) -> MarsPassthroughResult:
    """Execute a prepared Mars passthrough request."""

    stderr_stream = sys.stderr if stderr is None else stderr
    try:
        if request.wants_json:
            result = run(
                list(request.command),
                check=False,
                capture_output=True,
                text=True,
            )
            return MarsPassthroughResult(
                request=request,
                returncode=result.returncode,
                stdout_text=result.stdout or "",
                stderr_text=result.stderr or "",
            )

        result = run(list(request.command), check=False)
        return MarsPassthroughResult(request=request, returncode=result.returncode)
    except FileNotFoundError:
        print(
            "error: Failed to execute 'mars'. Install meridian with dependencies and retry.",
            file=stderr_stream,
        )
        raise SystemExit(1) from None


def augment_sync_result(
    result: MarsPassthroughResult,
    *,
    output_format: str | None = None,
    check_upgrades: Callable[[Path | None], UpgradeAvailability | None] = (
        check_upgrade_availability
    ),
    format_upgrades: Callable[[UpgradeAvailability], Sequence[str]] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> None:
    """Add sync-specific upgrade availability output to passthrough results."""

    _ = output_format
    if not result.request.is_sync:
        return

    stdout_stream = sys.stdout if stdout is None else stdout
    stderr_stream = sys.stderr if stderr is None else stderr
    formatter: Callable[[UpgradeAvailability], Sequence[str]] = (
        format_upgrade_availability
        if format_upgrades is None
        else (lambda fn: lambda u: fn(u))(format_upgrades)
    )

    upgrades: UpgradeAvailability | None = None
    if result.returncode in {0, 1}:
        upgrades = check_upgrades(result.request.root_override)

    if result.request.wants_json:
        stdout_text = result.stdout_text
        if upgrades is not None and upgrades.count > 0 and stdout_text.strip():
            stdout_text = inject_upgrade_hint_into_sync_json(
                stdout_text,
                within_constraint=upgrades.within_constraint,
                beyond_constraint=upgrades.beyond_constraint,
            )
        if stdout_text:
            stdout_stream.write(stdout_text)
        if result.stderr_text:
            stderr_stream.write(result.stderr_text)
        return

    if upgrades is not None and upgrades.count > 0:
        for line in formatter(upgrades):
            print(line, file=stdout_stream)


def run_mars_passthrough(
    args: Sequence[str],
    *,
    output_format: str | None = None,
    resolve_executable: Callable[[], str | None] = resolve_mars_executable,
    parse_request: Callable[..., MarsPassthroughRequest] = parse_mars_passthrough,
    execute_request: Callable[[MarsPassthroughRequest], MarsPassthroughResult] = (
        execute_mars_passthrough
    ),
    augment_result: Callable[[MarsPassthroughResult], None] = augment_sync_result,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> None:
    stdout_stream = sys.stdout if stdout is None else stdout
    stderr_stream = sys.stderr if stderr is None else stderr
    executable = resolve_executable()
    if executable is None:
        print(
            "error: Failed to execute 'mars'. Install meridian with dependencies and retry.",
            file=stderr_stream,
        )
        raise SystemExit(1)

    request = parse_request(
        args,
        output_format=output_format,
        executable=executable,
    )
    result = execute_request(request)
    if not request.is_sync:
        if request.wants_json:
            if result.stdout_text:
                stdout_stream.write(result.stdout_text)
            if result.stderr_text:
                stderr_stream.write(result.stderr_text)
        raise SystemExit(result.returncode)

    augment_result(result)
    raise SystemExit(result.returncode)


def resolve_init_repo_root(path: str | None) -> Path:
    if path:
        return Path(path).expanduser().resolve()
    env_root = os.getenv("MERIDIAN_REPO_ROOT", "").strip()
    return Path(env_root).expanduser().resolve() if env_root else Path.cwd().resolve()


def resolve_init_link_mars_command(repo_root: Path, link: str) -> tuple[str, list[str]]:
    root_arg = repo_root.as_posix()
    if (repo_root / "mars.toml").is_file():
        return "link", ["--root", root_arg, "link", link]
    return "init", ["--root", root_arg, "init", "--link", link]


def run_init_link_flow_json(
    *,
    executable: str,
    mars_mode: str,
    mars_args: Sequence[str],
    link: str,
    config_result: BaseModel,
    emit: Callable[[object], None],
    parse_request: Callable[..., MarsPassthroughRequest] = parse_mars_passthrough,
    execute_request: Callable[[MarsPassthroughRequest], MarsPassthroughResult] = (
        execute_mars_passthrough
    ),
    decode_values: Callable[[str], list[object] | None] = decode_json_values,
) -> None:
    request = parse_request(mars_args, output_format="json", executable=executable)
    result = execute_request(request)
    parsed_events = decode_values(result.stdout_text)
    if parsed_events is None:
        mars_output: object = result.stdout_text
    elif len(parsed_events) == 1:
        mars_output = parsed_events[0]
    else:
        mars_output = parsed_events

    mars_payload: dict[str, object] = {
        "mode": mars_mode,
        "target": link,
        "exit_code": result.returncode,
        "output": mars_output,
    }
    if result.stderr_text:
        mars_payload["stderr"] = result.stderr_text
    emit(
        {
            "ok": result.returncode == 0,
            "config": config_result.model_dump(),
            "mars": mars_payload,
        }
    )
    if result.returncode != 0:
        raise SystemExit(result.returncode)
