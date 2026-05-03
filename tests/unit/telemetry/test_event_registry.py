from __future__ import annotations

from meridian.lib.launch.context import normalize_usage_model_family
from meridian.lib.telemetry import (
    EVENT_REGISTRY,
    TelemetryEnvelope,
    concerns_for_event,
    make_error_data,
)
from meridian.lib.telemetry.events import VALID_CONCERNS, VALID_DOMAINS, validate_event

EXPECTED_CONCERNS = {
    "spawn.process_exited": ("operational",),
    "spawn.succeeded": ("operational",),
    "spawn.failed": ("operational", "error"),
    "spawn.cancelled": ("operational",),
    "chat.http.request_completed": ("operational",),
    "chat.ws.connected": ("operational", "usage"),
    "chat.ws.disconnected": ("operational",),
    "chat.ws.rejected": ("operational", "error"),
    "chat.command.dispatched": ("operational", "usage"),
    "chat.runtime.stopping": ("operational",),
    "chat.runtime.stopped": ("operational",),
    "dev_frontend.launched": ("operational", "usage"),
    "dev_frontend.ready": ("operational", "usage"),
    "dev_frontend.readiness_timeout": ("operational", "error"),
    "dev_frontend.exited": ("operational",),
    "mcp.command.invoked": ("operational", "usage"),
    "work.started": ("operational", "usage"),
    "work.updated": ("operational",),
    "work.done": ("operational", "usage"),
    "work.deleted": ("operational",),
    "work.reopened": ("operational", "usage"),
    "work.renamed": ("operational",),
    "runtime.telemetry.dropped": ("operational", "error"),
    "runtime.telemetry.sink_failed": ("operational", "error"),
    "runtime.telemetry.consumer_data_lost": ("operational", "error"),
    "runtime.debug_tracer_disabled": ("operational", "error"),
    "runtime.stream_event_dropped": ("operational", "error"),
    "usage.command.invoked": ("usage",),
    "usage.model.selected": ("usage",),
    "usage.spawn.launched": ("usage",),
}


def test_registered_events_have_valid_domains_and_concerns() -> None:
    assert EVENT_REGISTRY
    for event, definition in EVENT_REGISTRY.items():
        assert event
        assert definition["domain"] in VALID_DOMAINS
        assert definition["concerns"]
        assert set(definition["concerns"]).issubset(VALID_CONCERNS)


def test_concern_tag_lookup_for_known_events() -> None:
    assert concerns_for_event("spawn.failed") == ("operational", "error")
    assert concerns_for_event("usage.command.invoked") == ("usage",)


def test_registry_concern_tags_match_normative_mapping() -> None:
    assert set(EVENT_REGISTRY) == set(EXPECTED_CONCERNS)
    for event, expected_concerns in EXPECTED_CONCERNS.items():
        assert concerns_for_event(event) == expected_concerns


def test_envelope_to_dict_omits_none_optional_fields() -> None:
    envelope = TelemetryEnvelope(
        v=1,
        ts="2026-05-02T12:00:00Z",
        domain="chat",
        event="chat.ws.connected",
        scope="chat.server.ws",
    )
    assert envelope.to_dict() == {
        "v": 1,
        "ts": "2026-05-02T12:00:00Z",
        "domain": "chat",
        "event": "chat.ws.connected",
        "scope": "chat.server.ws",
    }


def test_validate_event_rejects_invalid_domain_pair() -> None:
    validate_event("spawn", "spawn.failed", "error")
    try:
        validate_event("chat", "spawn.failed", "error")
    except ValueError as exc:
        assert "belongs to domain" in str(exc)
    else:
        raise AssertionError("expected invalid event/domain pair to fail")


def test_make_error_data_shape() -> None:
    exc = RuntimeError("boom")
    data = make_error_data(exc)
    assert data["error"]["type"] == "RuntimeError"
    assert data["error"]["message"] == "boom"
    assert "RuntimeError: boom" in data["error"]["stack"]
    assert make_error_data(message="plain") == {
        "error": {"type": "UnknownError", "message": "plain"}
    }
    assert make_error_data() == {
        "error": {"type": "UnknownError", "message": "Unknown error"}
    }


def test_usage_model_family_normalization_omits_raw_model_ids() -> None:
    assert normalize_usage_model_family("gpt-5") == "gpt-5"
    assert normalize_usage_model_family("gpt-5.5") == "gpt-5.5"
    assert normalize_usage_model_family("gpt-55") == "gpt-5.5"
    assert normalize_usage_model_family("gpt-5-mini") == "gpt-5-mini"
    assert normalize_usage_model_family("gpt-5.4-mini") == "gpt-5.4-mini"
    assert normalize_usage_model_family("gpt-5.4-mini-2026-01-01") == "gpt-5.4-mini"
    assert normalize_usage_model_family("gpt_4o_mini_2026_01_01") == "gpt-4o-mini"
    assert normalize_usage_model_family("claude-sonnet-4-6") == "claude-sonnet"
    assert normalize_usage_model_family("claude-opus-4-6") == "claude-opus"
    assert normalize_usage_model_family("claude-haiku-4-6") == "claude-haiku"
    assert normalize_usage_model_family("vendor-codex-model") == "codex"
    assert normalize_usage_model_family("codex-latest") == "codex"
    assert normalize_usage_model_family("o4-mini") == "openai-o"
    assert normalize_usage_model_family("o3-2026-01-01") == "openai-o"
    assert normalize_usage_model_family("vendor-custom-model") == "other"
    assert normalize_usage_model_family("") == "other"
