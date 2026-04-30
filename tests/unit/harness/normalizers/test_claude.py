from meridian.lib.harness.connections.base import HarnessEvent
from meridian.lib.harness.normalizers.claude import ClaudeNormalizer
from meridian.lib.streaming.drain_policy import TURN_BOUNDARY_EVENT_TYPE


def event(event_type, payload):
    return HarnessEvent(event_type=event_type, payload=payload, harness_id="claude")


def test_claude_text_sequence_normalizes_turn_and_content():
    n = ClaudeNormalizer("c1", "s1")

    started = n.normalize(
        event("message_start", {"type": "message_start", "message": {"model": "claude-opus"}})
    )[0]
    delta = n.normalize(
        event("content_block_delta", {"index": 0, "delta": {"type": "text_delta", "text": "hi"}})
    )[0]
    completed = n.normalize(
        event(
            "result", {"status": "succeeded", "usage": {"input_tokens": 1}, "total_cost_usd": 0.01}
        )
    )[0]

    assert started.type == "turn.started"
    assert started.payload["model"] == "claude-opus"
    assert delta.type == "content.delta"
    assert delta.payload == {"stream_kind": "assistant_text", "text": "hi"}
    assert delta.turn_id == started.turn_id
    assert completed.type == "turn.completed"
    assert completed.payload["cost_usd"] == 0.01


def test_claude_tool_use_normalizes_item_lifecycle():
    n = ClaudeNormalizer("c1", "s1")
    n.normalize(event("message_start", {"message": {}}))

    started = n.normalize(
        event(
            "content_block_start",
            {"index": 2, "content_block": {"type": "tool_use", "id": "toolu_1", "name": "Read"}},
        )
    )[0]
    updated = n.normalize(
        event(
            "content_block_delta",
            {"index": 2, "delta": {"type": "input_json_delta", "partial_json": '{"file"'}},
        )
    )[0]
    completed = n.normalize(event("content_block_stop", {"index": 2}))[0]

    assert started.type == "item.started"
    assert started.item_id == "toolu_1"
    assert updated.type == "item.updated"
    assert updated.payload["input_json_delta"] == '{"file"'
    assert completed.type == "item.completed"
    assert completed.payload["input_json"] == '{"file"'


def test_reasoning_and_synthetic_boundary_and_unknowns():
    n = ClaudeNormalizer("c1", "s1")
    n.normalize(event("message_start", {"message": {}}))

    reasoning = n.normalize(
        event("content_block_delta", {"delta": {"type": "thinking_delta", "thinking": "hmm"}})
    )[0]
    synthetic = n.normalize(
        HarnessEvent(
            TURN_BOUNDARY_EVENT_TYPE, {"status": "succeeded", "synthetic": True}, "meridian"
        )
    )[0]

    assert reasoning.payload == {"stream_kind": "reasoning_text", "text": "hmm"}
    assert synthetic.type == "turn.completed"
    assert synthetic.payload["synthetic"] is True
    assert n.normalize(event("surprise", {})) == []
