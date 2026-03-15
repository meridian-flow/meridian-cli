"""CLI output formatting utilities."""

import json
import sys
from typing import Any, Literal, Protocol, TextIO, cast

from pydantic import BaseModel, ConfigDict

from meridian.lib.core.sink import NullSink, OutputSink
from meridian.lib.core.util import FormatContext, TextFormattable, to_jsonable

OutputFormat = Literal["text", "json"]
type JSONScalar = str | int | float | bool | None
type JSONValue = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]

_DEFAULT_FORMAT_CTX = FormatContext()


class OutputConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    format: OutputFormat


class _FlushableSink(Protocol):
    def flush(self) -> None: ...


def _to_json_value(value: Any) -> JSONValue:
    return cast("JSONValue", to_jsonable(value))


def normalize_output_format(
    *,
    requested: str | None,
    json_mode: bool,
) -> OutputFormat:
    """Resolve final output format from global output flags."""

    if json_mode:
        return "json"

    if requested is None or requested == "":
        return "text"

    normalized = requested.strip().lower()
    if normalized in {"text", "json"}:
        return cast("OutputFormat", normalized)
    raise SystemExit("--format must be one of: text, json")


def _render_text(value: Any) -> str:
    # "text" mode: prefer format_text() if available, fall back to indented JSON
    # for types that have not yet implemented the protocol.
    if isinstance(value, TextFormattable):
        return value.format_text(_DEFAULT_FORMAT_CTX)
    return json.dumps(_to_json_value(value), sort_keys=True, indent=2)


class TextSink:
    def __init__(
        self,
        *,
        format: OutputFormat = "text",
        stdout: TextIO | None = None,
        stderr: TextIO | None = None,
    ) -> None:
        self._format = format
        self._stdout = sys.stdout if stdout is None else stdout
        self._stderr = sys.stderr if stderr is None else stderr

    def result(self, payload: Any) -> None:
        if isinstance(payload, str):
            if payload == "":
                return
            print(payload, file=self._stdout)
            return
        rendered = _render_text(payload)
        if rendered == "":
            return
        print(rendered, file=self._stdout)

    def status(self, message: str) -> None:
        print(message, file=self._stderr)

    def warning(self, message: str) -> None:
        print(f"warning: {message}", file=self._stderr)

    def error(self, message: str, exit_code: int = 1) -> None:
        _ = exit_code
        print(f"error: {message}", file=self._stderr)

    def heartbeat(self, message: str) -> None:
        print(message, file=self._stderr, flush=True)

    def event(self, payload: dict[str, Any]) -> None:
        print(
            json.dumps(_to_json_value(payload), separators=(",", ":")),
            file=self._stdout,
            flush=True,
        )

    def flush(self) -> None:
        self._stdout.flush()
        self._stderr.flush()


class JsonSink:
    def __init__(self, *, stdout: TextIO | None = None, stderr: TextIO | None = None) -> None:
        self._stdout = sys.stdout if stdout is None else stdout
        self._stderr = sys.stderr if stderr is None else stderr
        self._result: JSONValue | str | None = None
        self._has_result = False

    def result(self, payload: Any) -> None:
        self._result = _to_json_value(payload)
        self._has_result = True

    def status(self, message: str) -> None:
        print(message, file=self._stderr)

    def warning(self, message: str) -> None:
        print(f"warning: {message}", file=self._stderr)

    def error(self, message: str, exit_code: int = 1) -> None:
        _ = exit_code
        print(f"error: {message}", file=self._stderr)

    def heartbeat(self, message: str) -> None:
        print(message, file=self._stderr, flush=True)

    def event(self, payload: dict[str, Any]) -> None:
        print(
            json.dumps(_to_json_value(payload), separators=(",", ":")),
            file=self._stderr,
            flush=True,
        )

    def flush(self) -> None:
        if self._has_result:
            print(json.dumps(self._result, sort_keys=True), file=self._stdout)
        self._stdout.flush()
        self._stderr.flush()


class AgentSink:
    def __init__(self, *, stdout: TextIO | None = None) -> None:
        self._stdout = sys.stdout if stdout is None else stdout
        self._messages: list[dict[str, JSONValue]] = []

    def _append_typed(self, message_type: str, payload: Any) -> None:
        # Prefer compact text rendering for agent mode — saves tokens.
        if isinstance(payload, TextFormattable):
            rendered = payload.format_text(_DEFAULT_FORMAT_CTX)
            if rendered == "":
                return
            self._messages.append(
                {
                    "type": message_type,
                    "text": rendered,
                }
            )
            return

        json_payload = _to_json_value(payload)
        entry: dict[str, JSONValue] = {"type": message_type}
        if isinstance(json_payload, dict):
            for key, value in cast("dict[str, JSONValue]", json_payload).items():
                if key == "type":
                    entry["payload_type"] = value
                else:
                    entry[key] = value
        else:
            entry["payload"] = json_payload
        self._messages.append(entry)

    def result(self, payload: Any) -> None:
        self._append_typed("result", payload)

    def status(self, message: str) -> None:
        _ = message

    def warning(self, message: str) -> None:
        _ = message

    def error(self, message: str, exit_code: int = 1) -> None:
        self._messages.append({"type": "error", "error": message, "exit_code": exit_code})

    def heartbeat(self, message: str) -> None:
        _ = message

    def event(self, payload: dict[str, Any]) -> None:
        self._append_typed("event", payload)

    def flush(self) -> None:
        for message in self._messages:
            print(json.dumps(message, separators=(",", ":"), sort_keys=True), file=self._stdout)
        self._stdout.flush()


_NULL_SINK = NullSink()


def create_sink(config: OutputConfig, *, agent_mode: bool = False) -> OutputSink:
    if config.format == "json":
        if agent_mode:
            return AgentSink()
        return JsonSink()
    if config.format == "text":
        return TextSink(format=config.format)
    return _NULL_SINK


def flush_sink(sink: OutputSink) -> None:
    flush = getattr(sink, "flush", None)
    if callable(flush):
        try:
            cast("_FlushableSink", sink).flush()
        except Exception:
            # Flush should never fail command execution (e.g. closed stdio on shutdown).
            return


def emit(value: Any, *, sink: OutputSink) -> None:
    """Emit one payload via an explicit output sink."""

    sink.result(value)
