"""Claude CLI harness adapter."""

import json
import logging
import re
from pathlib import Path
from typing import Any, ClassVar, cast
from uuid import uuid4

from meridian.lib.core.conversation import Conversation, ConversationTurn, ToolCall
from meridian.lib.core.domain import TokenUsage
from meridian.lib.core.types import ArtifactKey, HarnessId, SpawnId
from meridian.lib.harness.adapter import (
    ArtifactStore,
    BaseSubprocessHarness,
    HarnessCapabilities,
    McpConfig,
    PermissionResolver,
    RunPromptPolicy,
    SpawnParams,
)
from meridian.lib.harness.common import (
    FlagEffect,
    FlagStrategy,
    PromptMode,
    StrategyMap,
    build_harness_command,
    extract_claude_report,
    extract_session_id_from_artifacts,
    extract_usage_from_artifacts,
)
from meridian.lib.harness.launch_types import PromptPolicy, SessionSeed
from meridian.lib.safety.permissions import PermissionConfig

logger = logging.getLogger(__name__)


def build_claude_adhoc_agent_json(
    *,
    name: str,
    description: str,
    prompt: str,
) -> str:
    """Build a Claude `--agents` payload for one installed Meridian agent."""

    normalized_name = name.strip()
    if not normalized_name:
        return ""

    payload = {
        normalized_name: {
            "description": description.strip() or normalized_name,
            "prompt": prompt,
        }
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def project_slug(repo_root: Path) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "-", str(repo_root.resolve()))


def _claude_project_dir(repo_root: Path) -> Path:
    return Path.home() / ".claude" / "projects" / project_slug(repo_root)


def _read_claude_session_id(path: Path) -> str | None:
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            first_line = handle.readline().strip()
    except OSError:
        logger.debug("Failed to read Claude session file %s", path, exc_info=True)
        return None
    if not first_line:
        return None
    try:
        payload = json.loads(first_line)
    except json.JSONDecodeError:
        return path.stem.strip() or None
    if not isinstance(payload, dict):
        return path.stem.strip() or None
    payload_dict = cast("dict[str, object]", payload)
    session_id = payload_dict.get("sessionId")
    if isinstance(session_id, str) and session_id.strip():
        return session_id.strip()
    return path.stem.strip() or None


def _detect_primary_session_id(repo_root: Path, started_at_epoch: float) -> str | None:
    project_dir = _claude_project_dir(repo_root)
    if not project_dir.is_dir():
        return None

    candidates: list[tuple[float, Path]] = []
    for candidate in project_dir.glob("*.jsonl"):
        try:
            modified_at = candidate.stat().st_mtime
        except OSError:
            continue
        if modified_at + 1 < started_at_epoch:
            continue
        candidates.append((modified_at, candidate))

    for _, candidate in sorted(candidates, key=lambda item: item[0], reverse=True):
        resolved = _read_claude_session_id(candidate)
        if resolved:
            return resolved
    return None


def _extract_passthrough_session_id(args: tuple[str, ...]) -> str:
    """Extract --session-id value from passthrough args, or return empty string."""
    for i, token in enumerate(args):
        if token == "--session-id" and i + 1 < len(args):
            return args[i + 1].strip()
        if token.startswith("--session-id="):
            return token.partition("=")[2].strip()
    return ""


def _read_artifact_text(artifacts: ArtifactStore, spawn_id: SpawnId, name: str) -> str:
    key = ArtifactKey(f"{spawn_id}/{name}")
    if not artifacts.exists(key):
        return ""
    return artifacts.get(key).decode("utf-8", errors="ignore")


def _read_output_payloads(artifacts: ArtifactStore, spawn_id: SpawnId) -> list[dict[str, object]]:
    raw_output = _read_artifact_text(artifacts, spawn_id, "output.jsonl")
    payloads: list[dict[str, object]] = []
    for line in raw_output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload_obj = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(payload_obj, dict):
            payloads.append(cast("dict[str, object]", payload_obj))
    return payloads


def _tool_call_from_payload(payload: dict[str, object]) -> ToolCall | None:
    event_type = str(payload.get("type", payload.get("event", ""))).strip().lower()
    if event_type != "tool_use":
        return None

    tool_name = str(payload.get("name", "")).strip()
    if not tool_name:
        return None

    raw_input = payload.get("input")
    tool_input: dict[str, Any] = (
        cast("dict[str, Any]", raw_input) if isinstance(raw_input, dict) else {}
    )
    output_text: str | None = None
    output_value = payload.get("output")
    if isinstance(output_value, str):
        output_text = output_value.strip() or None
    return ToolCall(tool_name=tool_name, input=tool_input, output=output_text)


def _claude_thinking_transform(value: object, args: list[str]) -> None:
    normalized = str(value).strip()
    if not normalized:
        return
    mapped = {
        "low": "low",
        "medium": "medium",
        "high": "high",
        "xhigh": "max",
    }.get(normalized, normalized)
    args.extend(["--effort", mapped])


class ClaudeAdapter(BaseSubprocessHarness):
    """SubprocessHarness implementation for `claude`."""

    STRATEGIES: ClassVar[StrategyMap] = {
        "model": FlagStrategy(effect=FlagEffect.CLI_FLAG, cli_flag="--model"),
        "thinking": FlagStrategy(
            effect=FlagEffect.TRANSFORM,
            transform=_claude_thinking_transform,
        ),
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

    @property
    def id(self) -> HarnessId:
        return HarnessId.CLAUDE

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

    def run_prompt_policy(self) -> RunPromptPolicy:
        return RunPromptPolicy(
            include_agent_body=False,
            include_skills=False,
            skill_injection_mode="append-system-prompt",
        )

    def build_adhoc_agent_payload(self, *, name: str, description: str, prompt: str) -> str:
        return build_claude_adhoc_agent_json(name=name, description=description, prompt=prompt)

    def build_command(self, run: SpawnParams, perms: PermissionResolver) -> list[str]:
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
            perms=perms,
            harness_id=self.id,
        )
        # Inject skill content for --append-system-prompt (workaround for issue #29902).
        if run.appended_system_prompt:
            command.extend(["--append-system-prompt", run.appended_system_prompt])
        # Ad-hoc agent payload for native skill loading via Claude --agents flag
        adhoc_payload = run.adhoc_agent_payload.strip()
        if adhoc_payload:
            command.extend(["--agents", adhoc_payload])
        harness_session_id = (run.continue_harness_session_id or "").strip()
        if not harness_session_id:
            return command
        command.extend(["--resume", harness_session_id])
        if run.continue_fork:
            command.append("--fork-session")
        return command

    def mcp_config(self, run: SpawnParams) -> McpConfig | None:
        # MCP injection is off by default — agents use the CLI instead.
        # Users who want always-on MCP can configure it in their harness settings.
        return None

    def env_overrides(self, config: PermissionConfig) -> dict[str, str]:
        _ = config
        return {}

    def blocked_child_env_vars(self) -> frozenset[str]:
        # Meridian manages nesting limits itself; suppress Claude's parent-session
        # sentinel so child Claude spawns can run under Meridian control.
        return frozenset({"CLAUDECODE"})

    def extract_usage(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> TokenUsage:
        return extract_usage_from_artifacts(artifacts, spawn_id)

    def extract_session_id(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None:
        return extract_session_id_from_artifacts(artifacts, spawn_id)

    def extract_report(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None:
        return extract_claude_report(artifacts, spawn_id)

    def extract_conversation(
        self, artifacts: ArtifactStore, spawn_id: SpawnId
    ) -> Conversation | None:
        payloads = _read_output_payloads(artifacts, spawn_id)
        tool_calls = tuple(
            tool_call
            for payload in payloads
            if (tool_call := _tool_call_from_payload(payload)) is not None
        )

        prompt_text = _read_artifact_text(artifacts, spawn_id, "prompt.md").strip()
        report_text = _read_artifact_text(artifacts, spawn_id, "report.md").strip()
        if not report_text:
            fallback_report = extract_claude_report(artifacts, spawn_id)
            report_text = fallback_report.strip() if fallback_report else ""

        if not prompt_text and not report_text and not tool_calls:
            return None

        turns: list[ConversationTurn] = []
        if prompt_text:
            turns.append(ConversationTurn(role="user", content=prompt_text))
        if report_text or tool_calls:
            turns.append(
                ConversationTurn(
                    role="assistant",
                    content=report_text,
                    tool_calls=tool_calls,
                )
            )

        if not turns:
            return None

        return Conversation(
            spawn_id=str(spawn_id),
            harness=str(self.id),
            turns=tuple(turns),
        )

    def seed_session(
        self,
        *,
        is_resume: bool,
        harness_session_id: str,
        passthrough_args: tuple[str, ...],
    ) -> SessionSeed:
        normalized_harness_session_id = harness_session_id.strip()
        # Resume and fork both provide an explicit harness session id. Fork is
        # represented as is_resume=False with harness_session_id set.
        if normalized_harness_session_id:
            return SessionSeed(session_id=normalized_harness_session_id)

        # If user provided --session-id via passthrough, use that value.
        passthrough_session_id = _extract_passthrough_session_id(passthrough_args)
        if passthrough_session_id:
            return SessionSeed(session_id=passthrough_session_id)

        session_id = str(uuid4())
        # Only inject --session-id for truly fresh sessions.
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
            return PromptPolicy(skill_injection=skill_injection)
        # Claude does not currently expand profile skills via --agent
        # (see anthropics/claude-code#29902), so we must inject skill content
        # explicitly through Meridian's --append-system-prompt path.
        return PromptPolicy(prompt=prompt, skill_injection=skill_injection)

    def detect_primary_session_id(
        self,
        *,
        repo_root: Path,
        started_at_epoch: float,
        started_at_local_iso: str | None,
    ) -> str | None:
        _ = started_at_local_iso
        return _detect_primary_session_id(repo_root, started_at_epoch)

    def resolve_session_file(self, *, repo_root: Path, session_id: str) -> Path | None:
        normalized_session_id = session_id.strip()
        if not normalized_session_id:
            return None
        candidate = _claude_project_dir(repo_root) / f"{normalized_session_id}.jsonl"
        if not candidate.is_file():
            return None
        return candidate

    def owns_untracked_session(self, *, repo_root: Path, session_ref: str) -> bool:
        session_file = _claude_project_dir(repo_root) / f"{session_ref}.jsonl"
        return session_file.is_file()
