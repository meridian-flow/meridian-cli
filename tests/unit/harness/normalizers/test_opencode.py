from meridian.lib.harness.connections.base import HarnessEvent
from meridian.lib.harness.normalizers.opencode import OpenCodeNormalizer


def event(event_type, payload):
    return HarnessEvent(event_type=event_type, payload=payload, harness_id="opencode")


def test_opencode_stream_starts_turn_and_completes_on_idle():
    n = OpenCodeNormalizer("c1", "s1")

    started, delta = n.normalize(event("agent_message_chunk", {"text": "hi"}))
    completed = n.normalize(event("session.idle", {"usage": {"input_tokens": 1}}))[0]

    assert started.type == "turn.started"
    assert delta.type == "content.delta"
    assert delta.turn_id == started.turn_id
    assert delta.payload == {"stream_kind": "assistant_text", "text": "hi"}
    assert completed.type == "turn.completed"
    assert completed.payload["status"] == "succeeded"


def test_opencode_tool_update_and_files_persisted():
    n = OpenCodeNormalizer("c1", "s1")

    started, item = n.normalize(
        event("tool_call", {"tool": {"id": "i1", "type": "bash", "name": "shell"}})
    )
    updated, files = n.normalize(
        event("tool_call_update", {"item_id": "i1", "path": "a.txt", "operation": "write"})
    )

    assert started.type == "turn.started"
    assert item.type == "item.started"
    assert item.payload["item_type"] == "command_execution"
    assert updated.type == "item.updated"
    assert files.type == "files.persisted"
    assert files.payload == {"files": [{"path": "a.txt", "operation": "write"}]}


def test_opencode_reasoning_error_and_unknowns_without_request_events():
    n = OpenCodeNormalizer("c1", "s1")

    started, reasoning = n.normalize(event("agent_thought_chunk", {"text": "hmm"}))
    error = n.normalize(event("session.error", {"error": "boom"}))[0]

    assert started.type == "turn.started"
    assert reasoning.payload == {"stream_kind": "reasoning_text", "text": "hmm"}
    assert error.type == "runtime.error"
    assert error.payload["supports_runtime_hitl"] is False
    assert n.normalize(event("request.opened", {"request_id": "r1"})) == []
    assert n.normalize(event("surprise", {})) == []
