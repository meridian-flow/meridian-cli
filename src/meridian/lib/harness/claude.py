"""Claude CLI harness adapter."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import ClassVar, cast
from uuid import uuid4

from meridian.lib.harness._common import (
    categorize_stream_event,
    extract_claude_report,
    extract_session_id_from_artifacts,
    extract_usage_from_artifacts,
    iter_nested_dicts,
    parse_json_stream_event,
)
from meridian.lib.harness._strategies import (
    FlagEffect,
    FlagStrategy,
    PromptMode,
    StrategyMap,
    build_harness_command,
)
from meridian.lib.harness.adapter import (
    ArtifactStore,
    BaseHarnessAdapter,
    HarnessCapabilities,
    McpConfig,
    PermissionResolver,
    SpawnParams,
    StreamEvent,
)
from meridian.lib.harness.launch_types import PromptPolicy, SessionSeed
from meridian.lib.safety.permissions import PermissionConfig
from meridian.lib.types import HarnessId, SpawnId



def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _dedupe_preserving_order(items: list[str]) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return tuple(ordered)


def _merge_claude_allowed_tools(
    flags: list[str],
    mcp_allowed_tools: tuple[str, ...],
) -> list[str]:
    if not mcp_allowed_tools:
        return flags

    preserved: list[str] = []
    permission_allowed_tools: list[str] = []
    index = 0
    while index < len(flags):
        token = flags[index]
        if token != "--allowedTools":
            preserved.append(token)
            index += 1
            continue
        if index + 1 >= len(flags):
            preserved.append(token)
            index += 1
            continue
        permission_allowed_tools.extend(_split_csv(flags[index + 1]))
        index += 2

    merged_allowed_tools = _dedupe_preserving_order(
        [*permission_allowed_tools, *list(mcp_allowed_tools)]
    )
    if not merged_allowed_tools:
        return preserved
    preserved.extend(["--allowedTools", ",".join(merged_allowed_tools)])
    return preserved


def _extract_passthrough_session_id(args: tuple[str, ...]) -> str:
    """Extract --session-id value from passthrough args, or return empty string."""
    for i, token in enumerate(args):
        if token == "--session-id" and i + 1 < len(args):
            return args[i + 1].strip()
        if token.startswith("--session-id="):
            return token.partition("=")[2].strip()
    return ""


class _StaticPermissionResolver:
    def __init__(self, flags: list[str]) -> None:
        self._flags = tuple(flags)

    def resolve_flags(self, harness_id: HarnessId) -> list[str]:
        _ = harness_id
        return list(self._flags)


def _normalize_task(item: object) -> dict[str, str] | None:
    if not isinstance(item, dict):
        return None

    payload = cast("dict[str, object]", item)
    content_raw = (
        payload.get("content")
        or payload.get("task")
        or payload.get("title")
        or payload.get("text")
    )
    if content_raw is None:
        return None
    content = str(content_raw).strip()
    if not content:
        return None

    normalized: dict[str, str] = {"content": content}
    status_raw = payload.get("status")
    if status_raw is not None:
        status = str(status_raw).strip()
        if status:
            normalized["status"] = status
    id_raw = payload.get("id")
    if id_raw is not None:
        task_id = str(id_raw).strip()
        if task_id:
            normalized["id"] = task_id
    return normalized


def _extract_todowrite_tasks(metadata: dict[str, object]) -> list[dict[str, str]]:
    tasks: list[dict[str, str]] = []
    todo_tool_names = {"todowrite", "todo_write", "todo.write"}
    for payload in iter_nested_dicts(metadata):
        name = str(
            payload.get("name")
            or payload.get("tool_name")
            or payload.get("tool")
            or ""
        ).strip()
        if name.lower() not in todo_tool_names:
            continue
        input_payload = payload.get("input")
        todo_items = payload.get("todos")
        if todo_items is None and isinstance(input_payload, dict):
            input_dict = cast("dict[str, object]", input_payload)
            todo_items = input_dict.get("todos") or input_dict.get("tasks")
        if not isinstance(todo_items, list):
            continue
        for item in cast("list[object]", todo_items):
            normalized = _normalize_task(item)
            if normalized is not None:
                tasks.append(normalized)
    return tasks


class ClaudeAdapter(BaseHarnessAdapter):
    """HarnessAdapter implementation for `claude`."""

    STRATEGIES: ClassVar[StrategyMap] = {
        "model": FlagStrategy(effect=FlagEffect.CLI_FLAG, cli_flag="--model"),
        "agent": FlagStrategy(effect=FlagEffect.CLI_FLAG, cli_flag="--agent"),
        "skills": FlagStrategy(effect=FlagEffect.DROP),
        "continue_harness_session_id": FlagStrategy(effect=FlagEffect.DROP),
        "continue_fork": FlagStrategy(effect=FlagEffect.DROP),
        "appended_system_prompt": FlagStrategy(effect=FlagEffect.DROP),
    }
    PROMPT_MODE: ClassVar[PromptMode] = PromptMode.FLAG
    BASE_COMMAND: ClassVar[tuple[str, ...]] = (
        "claude",
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",  # required by Claude CLI when using stream-json with -p
    )
    PRIMARY_BASE_COMMAND: ClassVar[tuple[str, ...]] = ("claude",)
    EVENT_CATEGORY_MAP: ClassVar[dict[str, str]] = {
        "result": "lifecycle",
        "tool_use": "tool-use",
        "assistant": "assistant",
        "thinking": "thinking",
        "error": "error",
    }
    MCP_CONFIG_PREFIX: ClassVar[str] = "meridian-claude-mcp"

    @property
    def id(self) -> HarnessId:
        return HarnessId("claude")

    @property
    def capabilities(self) -> HarnessCapabilities:
        return HarnessCapabilities(
            supports_stream_events=True,
            supports_stdin_prompt=True,
            supports_session_resume=True,
            supports_session_fork=True,
            supports_native_skills=True,
            supports_native_agents=True,
            supports_programmatic_tools=False,
            supports_primary_launch=True,
        )

    def build_command(self, run: SpawnParams, perms: PermissionResolver) -> list[str]:
        mcp_config = self.mcp_config(run)
        permission_flags = perms.resolve_flags(self.id)
        if mcp_config is not None:
            permission_flags = _merge_claude_allowed_tools(
                permission_flags,
                mcp_config.claude_allowed_tools,
            )
        merged_perms = _StaticPermissionResolver(permission_flags)
        if run.interactive:
            base_command = self.PRIMARY_BASE_COMMAND
            command_run = run.model_copy(update={"prompt": ""})
        else:
            base_command = self.BASE_COMMAND
            command_run = run.model_copy(update={"prompt": "-"})
        command = build_harness_command(
            base_command=base_command,
            prompt_mode=self.PROMPT_MODE,
            run=command_run,
            strategies=self.STRATEGIES,
            perms=merged_perms,
            harness_id=self.id,
            mcp_config=mcp_config,
        )
        # Inject skill content for --append-system-prompt (workaround for issue #29902).
        if run.appended_system_prompt:
            command.extend(["--append-system-prompt", run.appended_system_prompt])
        # Ad-hoc agent JSON for native skill loading via Claude --agents flag
        adhoc_json = run.adhoc_agent_json.strip()
        if adhoc_json:
            command.extend(["--agents", adhoc_json])
        harness_session_id = (run.continue_harness_session_id or "").strip()
        if not harness_session_id:
            return command
        command.extend(["--resume", harness_session_id])
        if run.continue_fork:
            command.append("--fork-session")
        return command

    def _mcp_config_path(self, run: SpawnParams) -> Path:
        repo_root = (run.repo_root or "").strip() or "."
        fingerprint = hashlib.sha256(
            f"{repo_root}|{','.join(run.mcp_tools)}".encode("utf-8")
        ).hexdigest()[:16]
        return Path(tempfile.gettempdir()) / f"{self.MCP_CONFIG_PREFIX}-{fingerprint}.json"

    def _write_mcp_config(self, run: SpawnParams) -> Path:
        repo_root = (run.repo_root or "").strip() or "."
        payload = {
            "mcpServers": {
                "meridian": {
                    "command": "uv",
                    "args": ["run", "--directory", repo_root, "meridian", "serve"],
                }
            }
        }
        path = self._mcp_config_path(run)
        path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        return path

    def mcp_config(self, run: SpawnParams) -> McpConfig | None:
        if run.repo_root is None or not run.repo_root.strip():
            return None
        mcp_file = self._write_mcp_config(run)
        if run.mcp_tools:
            allowed_tools = tuple(f"mcp__meridian__{tool}" for tool in run.mcp_tools)
        else:
            allowed_tools = ("mcp__meridian__*",)

        # MCP sidecar crash behavior:
        # Claude surfaces MCP transport failures in-stream and the run usually exits
        # non-zero; Meridian treats this as a failed attempt and does not reconnect.
        return McpConfig(
            command_args=("--mcp-config", mcp_file.as_posix()),
            claude_allowed_tools=allowed_tools,
        )

    def env_overrides(self, config: PermissionConfig) -> dict[str, str]:
        _ = config
        return {}

    def parse_stream_event(self, line: str) -> StreamEvent | None:
        event = parse_json_stream_event(line)
        if event is None:
            return None
        return categorize_stream_event(event, exact_map=self.EVENT_CATEGORY_MAP)

    def extract_usage(self, artifacts: ArtifactStore, spawn_id: SpawnId):
        return extract_usage_from_artifacts(artifacts, spawn_id)

    def extract_session_id(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None:
        return extract_session_id_from_artifacts(artifacts, spawn_id)

    def extract_report(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None:
        return extract_claude_report(artifacts, spawn_id)

    def seed_session(
        self,
        *,
        is_resume: bool,
        harness_session_id: str,
        passthrough_args: tuple[str, ...],
    ) -> SessionSeed:
        # If user provided --session-id via passthrough, use that value
        passthrough_session_id = _extract_passthrough_session_id(passthrough_args)
        if passthrough_session_id:
            return SessionSeed(session_id=passthrough_session_id)
        session_id = harness_session_id or str(uuid4())
        # Only inject --session-id for fresh sessions
        if harness_session_id:
            return SessionSeed(session_id=session_id)
        return SessionSeed(
            session_id=session_id,
            session_args=("--session-id", session_id),
        )

    def filter_launch_content(
        self,
        *,
        prompt: str,
        skill_injection: str | None,
        is_resume: bool,
        harness_session_id: str,
    ) -> PromptPolicy:
        _ = harness_session_id
        if is_resume:
            return PromptPolicy()
        # Claude loads skills natively via --agent profile. Keep the prompt on the
        # appended-system-prompt path for interactive primary launches, but suppress
        # explicit skill injection to avoid duplicating profile-provided skills.
        _ = skill_injection
        return PromptPolicy(prompt=prompt, skill_injection="")

    def extract_tasks(self, event: StreamEvent) -> list[dict[str, str]] | None:
        tasks = _extract_todowrite_tasks(event.metadata)
        return tasks or None
