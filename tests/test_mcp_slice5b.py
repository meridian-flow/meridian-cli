"""Slice 5b MCP integration checks via SDK stdio client."""

from __future__ import annotations

import json
import sys
from typing import Any

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from meridian.lib.space.space_file import create_space


def _payload_from_call_result(result: Any) -> dict[str, Any]:
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured

    for block in getattr(result, "content", []):
        text = getattr(block, "text", None)
        if isinstance(text, str) and text.strip():
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload

    raise AssertionError("Call result did not include a JSON object payload")


@pytest.mark.asyncio
async def test_mcp_tools_registered_and_callable(package_root, cli_env, tmp_path) -> None:
    env = dict(cli_env)
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    env["MERIDIAN_REPO_ROOT"] = repo_root.as_posix()
    space = create_space(repo_root, name="mcp")
    env["MERIDIAN_SPACE_ID"] = space.id

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "meridian", "serve"],
        env=env,
        cwd=package_root,
    )

    async with stdio_client(params) as (read_stream, write_stream), ClientSession(
        read_stream, write_stream
    ) as session:
        await session.initialize()

        listed = await session.list_tools()
        names = {tool.name for tool in listed.tools}
        expected = {
            "spawn_create",
            "spawn_continue",
            "spawn_list",
            "spawn_show",
            "spawn_stats",
            "spawn_wait",
            "report_create",
            "report_show",
            "report_search",
            "skills_list",
            "skills_show",
            "models_list",
            "models_show",
            "doctor",
        }
        assert names == expected

        doctor = await session.call_tool("doctor", {})
        assert doctor.isError is False
        doctor_payload = _payload_from_call_result(doctor)
        assert isinstance(doctor_payload["ok"], bool)

        created = await session.call_tool(
            "spawn_create",
            {
                "prompt": "MCP non-blocking spawn_create verification",
                "model": "gpt-5.3-codex",
                "timeout_secs": 5,
                "dry_run": True,
            },
        )
        assert created.isError is False
        created_payload = _payload_from_call_result(created)
        assert created_payload["status"] == "dry-run"
