"""Unit tests for extension observability redaction logic."""

from __future__ import annotations

from meridian.lib.extensions.observability import RedactionPipeline


def test_redaction_removes_secret_keys_case_insensitively() -> None:
    payload = {
        "name": "ok",
        "TOKEN": "abc",
        "Api_Key": "xyz",
        "password": "hidden",
    }

    redacted = RedactionPipeline.redact(payload)

    assert redacted == {"name": "ok"}


def test_redaction_handles_nested_dicts() -> None:
    payload = {
        "outer": {
            "safe": "value",
            "Authorization": "secret",
        },
        "items": [
            {"ok": 1, "secret_key": "nope"},
            "text",
        ],
    }

    redacted = RedactionPipeline.redact(payload)

    assert redacted == {
        "outer": {"safe": "value"},
        "items": [{"ok": 1}, "text"],
    }


def test_redaction_truncates_strings_over_512_bytes() -> None:
    payload = {"text": "x" * 600}

    redacted = RedactionPipeline.redact(payload)

    assert redacted["text"].startswith("x" * 512)
    assert redacted["text"].endswith("...[truncated]")
