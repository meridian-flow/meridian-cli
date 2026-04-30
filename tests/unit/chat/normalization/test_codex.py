from meridian.lib.chat.normalization.codex import CodexNormalizer
from meridian.lib.harness.connections.base import HarnessEvent


def event(event_type, payload):
    return HarnessEvent(event_type=event_type, payload=payload, harness_id="codex")


def test_codex_text_sequence_normalizes_turn_content_and_usage():
    n = CodexNormalizer("c1", "s1")

    started = n.normalize(event("turn/started", {"turn_id": "t1", "model": "gpt"}))[0]
    delta = n.normalize(event("agent_message_chunk", {"text": "hi"}))[0]
    completed = n.normalize(event("turn/completed", {"usage": {"input_tokens": 1}}))[0]

    assert started.type == "turn.started"
    assert started.turn_id == "t1"
    assert delta.type == "content.delta"
    assert delta.turn_id == "t1"
    assert delta.payload == {"stream_kind": "assistant_text", "text": "hi"}
    assert completed.type == "turn.completed"
    assert completed.payload["usage"] == {"input_tokens": 1}


def test_codex_content_does_not_synthesize_turn_start_before_explicit_turn_started():
    n = CodexNormalizer("c1", "s1")

    delta = n.normalize(event("agent_message_chunk", {"message": {"content": "hi"}}))[0]
    started = n.normalize(event("turn/started", {"id": "t-late", "session_id": "sess-1"}))[0]

    assert delta.type == "content.delta"
    assert delta.turn_id is None
    assert delta.payload == {"stream_kind": "assistant_text", "text": "hi"}
    assert started.type == "turn.started"
    assert started.turn_id == "t-late"
    assert started.payload == {"session_id": "sess-1"}


def test_codex_request_and_user_input_events_preserve_payload_fidelity():
    n = CodexNormalizer("c1", "s1")

    opened = n.normalize(
        event(
            "request/opened",
            {
                "id": "r1",
                "request_type": "approval",
                "method": "apply_patch",
                "params": {"path": "a.txt"},
            },
        )
    )[0]
    resolved = n.normalize(
        event("request.resolved", {"request_id": "r1", "decision": "accept"})
    )[0]
    user_input = n.normalize(
        event("user_input/requested", {"request_id": "r2", "questions": [{"id": "q1"}]})
    )[0]

    assert opened.type == "request.opened"
    assert opened.request_id == "r1"
    assert opened.payload == {
        "id": "r1",
        "request_type": "approval",
        "method": "apply_patch",
        "params": {"path": "a.txt"},
    }
    assert resolved.type == "request.resolved"
    assert resolved.request_id == "r1"
    assert resolved.payload["decision"] == "accept"
    assert user_input.type == "user_input.requested"
    assert user_input.request_id == "r2"
    assert user_input.payload == {
        "request_id": "r2",
        "questions": [{"id": "q1"}],
        "request_type": "user_input",
    }


def test_codex_item_and_file_extraction_cover_nested_payload_shapes():
    n = CodexNormalizer("c1", "s1")
    n.normalize(event("turn/started", {"turn_id": "t1"}))

    started = n.normalize(
        event(
            "item/tool/started",
            {"tool": {"id": "i-file", "type": "patch", "name": "apply_patch"}},
        )
    )[0]
    completed, files = n.normalize(
        event(
            "item/tool/completed",
            {
                "item_id": "i-file",
                "files": ["a.txt", {"path": "b.txt", "operation": "write"}],
            },
        )
    )

    assert started.type == "item.started"
    assert started.item_id == "i-file"
    assert started.payload["item_type"] == "file_change"
    assert started.payload["raw_type"] == "patch"
    assert started.payload["name"] == "apply_patch"
    assert completed.type == "item.completed"
    assert completed.item_id == "i-file"
    assert files.type == "files.persisted"
    assert files.payload == {
        "files": [
            {"path": "a.txt"},
            {"path": "b.txt", "operation": "write"},
        ]
    }


def test_codex_reasoning_warning_and_synthetic_completion_boundary():
    n = CodexNormalizer("c1", "s1")
    started = n.normalize(event("turn/started", {"turn_id": "t1", "thread_id": "thr"}))[0]
    reasoning = n.normalize(event("agent_thought_chunk", {"text": "hmm"}))[0]
    warning = n.normalize(event("warning/approvalRejected", {"reason": "blocked"}))[0]
    completed = n.normalize(
        event("meridian/turn_completed", {"status": "cancelled", "synthetic": True})
    )[0]

    assert started.payload == {"thread_id": "thr"}
    assert reasoning.turn_id == "t1"
    assert reasoning.payload == {"stream_kind": "reasoning_text", "text": "hmm"}
    assert warning.type == "runtime.warning"
    assert warning.payload == {"reason": "blocked"}
    assert completed.type == "turn.completed"
    assert completed.turn_id == "t1"
    assert completed.payload == {"status": "cancelled", "synthetic": True}
