from meridian.lib.chat.normalization.registry import get_normalizer_factory
from meridian.lib.harness.connections.base import HarnessEvent


def _event(harness_id: str, event_type: str, payload: dict[str, object]) -> HarnessEvent:
    return HarnessEvent(event_type=event_type, payload=payload, harness_id=harness_id)


def _types_for(harness_id: str, events: list[HarnessEvent]) -> set[str]:
    normalizer = get_normalizer_factory(harness_id)("chat-1", "exec-1")
    types: set[str] = set()
    for event in events:
        types.update(chat_event.type for chat_event in normalizer.normalize(event))
    return types


def test_all_harnesses_emit_core_chat_event_families_without_server_branching():
    cases = {
        "claude": [
            _event("claude", "message_start", {"message": {"model": "claude"}}),
            _event(
                "claude",
                "content_block_delta",
                {"delta": {"type": "text_delta", "text": "hi"}},
            ),
            _event("claude", "result", {"status": "succeeded"}),
        ],
        "codex": [
            _event("codex", "turn/started", {"turn_id": "t1"}),
            _event("codex", "agent_message_chunk", {"text": "hi"}),
            _event("codex", "turn/completed", {"status": "succeeded"}),
        ],
        "opencode": [
            _event("opencode", "agent_message_chunk", {"text": "hi"}),
            _event("opencode", "session.idle", {}),
        ],
    }

    for harness_id, events in cases.items():
        assert {"turn.started", "content.delta", "turn.completed"} <= _types_for(
            harness_id, events
        )


def test_all_harnesses_emit_canonical_files_persisted():
    for harness_id in ("claude", "codex", "opencode"):
        types = _types_for(harness_id, [_event(harness_id, "files.persisted", {"path": "a.txt"})])
        assert "files.persisted" in types


def test_unknown_events_drop_instead_of_crashing():
    for harness_id in ("claude", "codex", "opencode"):
        assert _types_for(harness_id, [_event(harness_id, "unknown.event", {})]) == set()
