"""Tests for DebugTracer and shared trace helpers."""

from __future__ import annotations

import json
import sys
import threading
import time
from collections.abc import Sequence
from pathlib import Path
from unittest.mock import patch

from meridian.lib.observability.debug_tracer import DebugTracer
from meridian.lib.observability.trace_helpers import (
    trace_parse_error,
    trace_state_change,
    trace_wire_recv,
    trace_wire_send,
)
from meridian.lib.telemetry import init_telemetry
from meridian.lib.telemetry.events import TelemetryEnvelope


class RecordingTelemetrySink:
    def __init__(self) -> None:
        self.events: list[TelemetryEnvelope] = []

    def write_batch(self, events: Sequence[TelemetryEnvelope]) -> None:
        self.events.extend(events)

    def close(self) -> None:
        pass


def wait_for_telemetry(predicate: object, timeout: float = 1.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():  # type: ignore[operator]
            return
        time.sleep(0.01)
    raise AssertionError("telemetry event not observed")


class TestDebugTracer:
    def test_emit_writes_jsonl_line(self, tmp_path: Path) -> None:
        debug_path = tmp_path / "debug.jsonl"
        tracer = DebugTracer(spawn_id="p42", debug_path=debug_path)
        tracer.emit("wire", "stdin_write", direction="outbound", data={"payload": "hello"})
        tracer.close()

        lines = debug_path.read_text().strip().split("\n")
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["spawn_id"] == "p42"
        assert record["layer"] == "wire"
        assert record["direction"] == "outbound"
        assert record["event"] == "stdin_write"
        assert record["data"]["payload"] == "hello"
        assert isinstance(record["ts"], float)

    def test_emit_truncates_long_strings(self, tmp_path: Path) -> None:
        debug_path = tmp_path / "debug.jsonl"
        tracer = DebugTracer(spawn_id="p1", debug_path=debug_path, max_payload_bytes=32)
        long_payload = "x" * 100
        tracer.emit("wire", "test", data={"payload": long_payload})
        tracer.close()

        record = json.loads(debug_path.read_text().strip())
        truncated = record["data"]["payload"]
        assert truncated.startswith("x" * 32)
        assert "truncated" in truncated
        assert "100B total" in truncated

    def test_emit_serializes_dict_values(self, tmp_path: Path) -> None:
        debug_path = tmp_path / "debug.jsonl"
        tracer = DebugTracer(spawn_id="p1", debug_path=debug_path)
        tracer.emit("wire", "test", data={"payload": {"key": "value"}})
        tracer.close()

        record = json.loads(debug_path.read_text().strip())
        # Dict values are serialized to JSON string, then stored
        payload = record["data"]["payload"]
        assert isinstance(payload, str)
        assert '"key"' in payload

    def test_emit_serializes_list_values(self, tmp_path: Path) -> None:
        debug_path = tmp_path / "debug.jsonl"
        tracer = DebugTracer(spawn_id="p1", debug_path=debug_path)
        tracer.emit("wire", "test", data={"items": [1, 2, 3]})
        tracer.close()

        record = json.loads(debug_path.read_text().strip())
        assert isinstance(record["data"]["items"], str)
        assert "[1, 2, 3]" in record["data"]["items"]

    def test_emit_passes_through_scalars(self, tmp_path: Path) -> None:
        debug_path = tmp_path / "debug.jsonl"
        tracer = DebugTracer(spawn_id="p1", debug_path=debug_path)
        tracer.emit("wire", "test", data={"count": 42, "flag": True, "empty": None})
        tracer.close()

        record = json.loads(debug_path.read_text().strip())
        assert record["data"]["count"] == 42
        assert record["data"]["flag"] is True
        assert record["data"]["empty"] is None

    def test_emit_handles_non_serializable_values(self, tmp_path: Path) -> None:
        debug_path = tmp_path / "debug.jsonl"
        tracer = DebugTracer(spawn_id="p1", debug_path=debug_path)
        # A set is not JSON-serializable; should fall back to repr()
        tracer.emit("wire", "test", data={"bad": {"inner": object()}})
        tracer.close()

        record = json.loads(debug_path.read_text().strip())
        assert isinstance(record["data"]["bad"], str)

    def test_first_failure_disables_tracer(self, tmp_path: Path) -> None:
        debug_path = tmp_path / "debug.jsonl"
        tracer = DebugTracer(spawn_id="p1", debug_path=debug_path)

        # First emit succeeds
        tracer.emit("wire", "good")
        assert not tracer._disabled

        # Force a write failure by closing the handle
        with tracer._lock:
            if tracer._handle is not None:
                tracer._handle.close()
                tracer._handle = None
            # Make the path unwriteable
            debug_path.chmod(0o000)

        tracer.emit("wire", "bad")
        assert tracer._disabled

        # Subsequent emits are silently no-ops
        tracer.emit("wire", "also_bad")
        debug_path.chmod(0o644)

    def test_first_failure_emits_runtime_telemetry(self, tmp_path: Path) -> None:
        sink = RecordingTelemetrySink()
        init_telemetry(sink=sink)
        debug_path = tmp_path / "debug.jsonl"
        tracer = DebugTracer(spawn_id="p1", debug_path=debug_path)

        with patch.object(Path, "open", side_effect=OSError("disk full")):
            tracer.emit("wire", "bad")

        assert tracer._disabled
        wait_for_telemetry(lambda: len(sink.events) == 1)
        assert [event.event for event in sink.events] == ["runtime.debug_tracer_disabled"]
        event = sink.events[0]
        assert event.scope == "observability.debug_tracer"
        assert event.severity == "warning"
        assert event.ids == {"spawn_id": "p1"}
        assert event.data["error"]["type"] == "OSError"
        assert event.data["error"]["message"] == "disk full"

    def test_close_is_idempotent(self, tmp_path: Path) -> None:
        debug_path = tmp_path / "debug.jsonl"
        tracer = DebugTracer(spawn_id="p1", debug_path=debug_path)
        tracer.emit("wire", "test")
        tracer.close()
        tracer.close()  # Should not raise
        tracer.close()  # Should not raise

    def test_lazy_file_creation(self, tmp_path: Path) -> None:
        debug_path = tmp_path / "sub" / "deep" / "debug.jsonl"
        tracer = DebugTracer(spawn_id="p1", debug_path=debug_path)

        # File should not exist yet
        assert not debug_path.exists()

        tracer.emit("wire", "test")

        # Now it should exist
        assert debug_path.exists()
        tracer.close()

    def test_echo_stderr(self, tmp_path: Path) -> None:
        debug_path = tmp_path / "debug.jsonl"
        tracer = DebugTracer(spawn_id="p1", debug_path=debug_path, echo_stderr=True)

        with patch.object(sys, "stderr") as mock_stderr:
            mock_stderr.write = lambda s: None
            mock_stderr.flush = lambda: None
            tracer.emit("wire", "test")

        tracer.close()
        assert debug_path.exists()

    def test_no_data_field_when_none(self, tmp_path: Path) -> None:
        debug_path = tmp_path / "debug.jsonl"
        tracer = DebugTracer(spawn_id="p1", debug_path=debug_path)
        tracer.emit("connection", "state_change")
        tracer.close()

        record = json.loads(debug_path.read_text().strip())
        assert "data" not in record

    def test_close_then_reopen_on_emit(self, tmp_path: Path) -> None:
        """Tracer supports close-then-reopen for retry scenarios."""
        debug_path = tmp_path / "debug.jsonl"
        tracer = DebugTracer(spawn_id="p1", debug_path=debug_path)
        tracer.emit("wire", "first")
        tracer.close()
        tracer.emit("wire", "second")
        tracer.close()

        lines = debug_path.read_text().strip().split("\n")
        assert len(lines) == 2

    def test_thread_safety(self, tmp_path: Path) -> None:
        """Concurrent emits from multiple threads do not interleave or crash."""
        debug_path = tmp_path / "debug.jsonl"
        tracer = DebugTracer(spawn_id="p1", debug_path=debug_path)

        def emit_many(tid: int) -> None:
            for i in range(50):
                tracer.emit("wire", f"event_{tid}_{i}", data={"tid": tid, "i": i})

        threads = [threading.Thread(target=emit_many, args=(t,)) for t in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        tracer.close()
        lines = debug_path.read_text().strip().split("\n")
        assert len(lines) == 200
        # Each line must be valid JSON
        for line in lines:
            json.loads(line)


class TestTraceHelpers:
    def test_trace_state_change_with_none(self) -> None:
        # Should be a no-op and not raise
        trace_state_change(None, "claude", "created", "starting")

    def test_trace_state_change_emits(self, tmp_path: Path) -> None:
        debug_path = tmp_path / "debug.jsonl"
        tracer = DebugTracer(spawn_id="p1", debug_path=debug_path)
        trace_state_change(tracer, "claude", "created", "starting")
        tracer.close()

        record = json.loads(debug_path.read_text().strip())
        assert record["layer"] == "connection"
        assert record["event"] == "state_change"
        assert record["data"]["from_state"] == "created"
        assert record["data"]["to_state"] == "starting"
        assert record["data"]["harness"] == "claude"

    def test_trace_wire_send_with_none(self) -> None:
        trace_wire_send(None, "stdin_write", "payload")

    def test_trace_wire_send_emits(self, tmp_path: Path) -> None:
        debug_path = tmp_path / "debug.jsonl"
        tracer = DebugTracer(spawn_id="p1", debug_path=debug_path)
        trace_wire_send(tracer, "stdin_write", '{"type":"user"}', method="test")
        tracer.close()

        record = json.loads(debug_path.read_text().strip())
        assert record["layer"] == "wire"
        assert record["direction"] == "outbound"
        assert record["data"]["method"] == "test"

    def test_trace_wire_recv_with_none(self) -> None:
        trace_wire_recv(None, "stdout_line", "data")

    def test_trace_wire_recv_emits(self, tmp_path: Path) -> None:
        debug_path = tmp_path / "debug.jsonl"
        tracer = DebugTracer(spawn_id="p1", debug_path=debug_path)
        trace_wire_recv(tracer, "stdout_line", '{"type":"assistant"}')
        tracer.close()

        record = json.loads(debug_path.read_text().strip())
        assert record["layer"] == "wire"
        assert record["direction"] == "inbound"

    def test_trace_parse_error_with_none(self) -> None:
        trace_parse_error(None, "claude", "bad data")

    def test_trace_parse_error_emits(self, tmp_path: Path) -> None:
        debug_path = tmp_path / "debug.jsonl"
        tracer = DebugTracer(spawn_id="p1", debug_path=debug_path)
        trace_parse_error(tracer, "codex", "malformed", error="invalid JSON")
        tracer.close()

        record = json.loads(debug_path.read_text().strip())
        assert record["layer"] == "wire"
        assert record["event"] == "parse_error"
        assert record["data"]["error"] == "invalid JSON"
        assert record["data"]["harness"] == "codex"
