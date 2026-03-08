"""Direct Anthropic adapter with programmatic tool calling."""

# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportArgumentType=false


import asyncio
import json
import os
from typing import Any
from urllib import error, request

from meridian.lib.core.domain import TokenUsage
from meridian.lib.harness.adapter import (
    ArtifactStore,
    BaseHarnessAdapter,
    HarnessCapabilities,
    McpConfig,
    PermissionResolver,
    SpawnParams,
    SpawnResult,
    StreamEvent,
)
from meridian.lib.core.codec import (
    coerce_input_payload,
    normalize_optional,
    schema_from_type,
)
from meridian.lib.ops.manifest import OperationSpec, get_operations_for_surface
from meridian.lib.safety.permissions import PermissionConfig
from meridian.lib.core.util import to_jsonable
from meridian.lib.core.types import HarnessId, ModelId, SpawnId

_normalize_optional = normalize_optional


def _usage_from_response(response: dict[str, object]) -> TokenUsage:
    usage = response.get("usage")
    if not isinstance(usage, dict):
        return TokenUsage()
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    try:
        input_count = int(input_tokens) if input_tokens is not None else None
    except (TypeError, ValueError):
        input_count = None
    try:
        output_count = int(output_tokens) if output_tokens is not None else None
    except (TypeError, ValueError):
        output_count = None
    total_cost = usage.get("total_cost_usd")
    try:
        parsed_cost = float(total_cost) if total_cost is not None else None
    except (TypeError, ValueError):
        parsed_cost = None
    return TokenUsage(
        input_tokens=input_count,
        output_tokens=output_count,
        total_cost_usd=parsed_cost,
    )


def _extract_text_blocks(content: object) -> str:
    if not isinstance(content, list):
        return ""
    text_parts = [
        str(block.get("text", ""))
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    return "\n".join(part for part in text_parts if part).strip()


class DirectAdapter(BaseHarnessAdapter):
    """HarnessAdapter implementation for Anthropic Messages API mode."""

    @property
    def id(self) -> HarnessId:
        return HarnessId("direct")

    @property
    def capabilities(self) -> HarnessCapabilities:
        return HarnessCapabilities(
            supports_stream_events=False,
            supports_session_resume=False,
            supports_native_skills=False,
            supports_programmatic_tools=True,
        )

    def build_command(self, run: SpawnParams, perms: PermissionResolver) -> list[str]:
        _ = (run, perms)
        return ["direct"]

    def mcp_config(self, run: SpawnParams) -> McpConfig | None:
        _ = run
        # Direct mode calls Meridian operations in-process via the API/tool loop, so
        # there is no external MCP sidecar to configure or reconnect.
        return None

    def env_overrides(self, config: PermissionConfig) -> dict[str, str]:
        _ = config
        return {}

    def parse_stream_event(self, line: str) -> StreamEvent | None:
        _ = line
        return None

    def extract_usage(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> TokenUsage:
        _ = (artifacts, spawn_id)
        return TokenUsage()

    def extract_session_id(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None:
        _ = (artifacts, spawn_id)
        return None

    @staticmethod
    def build_tool_definitions() -> list[dict[str, object]]:
        """Generate Anthropic tool definitions from the explicit ops manifest."""

        tools: list[dict[str, object]] = [
            {"type": "code_execution_20260120", "name": "code_execution"}
        ]
        for operation in get_operations_for_surface("mcp"):
            if operation.mcp_name is None:
                raise ValueError(f"Operation '{operation.name}' is missing MCP tool name")
            tools.append(
                {
                    "name": operation.mcp_name,
                    "description": operation.description,
                    "input_schema": schema_from_type(operation.input_type),
                    "allowed_callers": ["code_execution_20260120"],
                }
            )
        return tools

    def _operation_by_mcp_name(self) -> dict[str, OperationSpec[Any, Any]]:
        return {
            operation.mcp_name: operation
            for operation in get_operations_for_surface("mcp")
            if operation.mcp_name is not None
        }

    async def _invoke_operation_tool(self, tool_name: str, raw_input: object) -> object:
        operation_map = self._operation_by_mcp_name()
        operation = operation_map.get(tool_name)
        if operation is None:
            raise KeyError(f"Unknown tool '{tool_name}'")

        payload = coerce_input_payload(operation.input_type, raw_input)
        return await operation.handler(payload)

    def _request_messages(
        self,
        *,
        api_key: str,
        model: str,
        messages: list[dict[str, object]],
        max_tokens: int,
    ) -> dict[str, object]:
        body = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
            "tools": self.build_tool_definitions(),
        }
        req = request.Request(
            url="https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            data=json.dumps(body).encode("utf-8"),
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=60) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:  # pragma: no cover - network/credential dependent.
            details = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Anthropic API error {exc.code}: {details}") from exc
        except error.URLError as exc:  # pragma: no cover - network dependent.
            raise RuntimeError(f"Anthropic API request failed: {exc.reason}") from exc

        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise RuntimeError("Anthropic API returned a non-object JSON payload.")
        return payload

    async def execute(
        self,
        *,
        prompt: str,
        model: ModelId,
        api_key: str | None = None,
        max_tokens: int = 2048,
        max_tool_round_trips: int = 8,
    ) -> SpawnResult:
        """Execute one prompt via Anthropic Messages API with tool-calling support."""

        key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise ValueError("ANTHROPIC_API_KEY is required for direct mode.")

        messages: list[dict[str, object]] = [{"role": "user", "content": prompt}]
        final_usage = TokenUsage()
        final_response: dict[str, object] | None = None

        for _ in range(max_tool_round_trips):
            response = await asyncio.to_thread(
                self._request_messages,
                api_key=key,
                model=str(model),
                messages=messages,
                max_tokens=max_tokens,
            )
            final_response = response
            final_usage = _usage_from_response(response)

            content = response.get("content", [])
            if not isinstance(content, list):
                content = []

            messages.append({"role": "assistant", "content": content})
            tool_uses = [
                block
                for block in content
                if isinstance(block, dict) and block.get("type") == "tool_use"
            ]

            if not tool_uses:
                output = _extract_text_blocks(content)
                return SpawnResult(
                    status="succeeded",
                    output=output,
                    usage=final_usage,
                    raw_response=final_response,
                )

            tool_results: list[dict[str, object]] = []
            for block in tool_uses:
                tool_use_id = str(block.get("id", ""))
                tool_name = str(block.get("name", ""))
                tool_input = block.get("input")
                result = await self._invoke_operation_tool(tool_name, tool_input)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": json.dumps(to_jsonable(result), sort_keys=True),
                    }
                )

            messages.append({"role": "user", "content": tool_results})

        return SpawnResult(
            status="failed",
            output="Direct adapter exceeded tool-calling round-trip limit.",
            usage=final_usage,
            raw_response=final_response,
        )
