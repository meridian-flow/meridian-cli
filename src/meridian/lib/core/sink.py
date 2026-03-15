"""Shared output sink protocol, no-op sink, and composite fan-out sink."""

from contextlib import suppress
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class OutputSink(Protocol):
    def result(self, payload: Any) -> None: ...

    def status(self, message: str) -> None: ...

    def warning(self, message: str) -> None: ...

    def error(self, message: str, exit_code: int = 1) -> None: ...

    def heartbeat(self, message: str) -> None: ...

    def event(self, payload: dict[str, Any]) -> None: ...


class NullSink:
    def result(self, payload: Any) -> None:
        _ = payload

    def status(self, message: str) -> None:
        _ = message

    def warning(self, message: str) -> None:
        _ = message

    def error(self, message: str, exit_code: int = 1) -> None:
        _ = (message, exit_code)

    def heartbeat(self, message: str) -> None:
        _ = message

    def event(self, payload: dict[str, Any]) -> None:
        _ = payload

    def flush(self) -> None:
        return


class CompositeSink:
    """Fan-out to multiple sinks.

    Delivers each method call to every child sink in order.  Individual
    sink errors are suppressed so one failing sink cannot break the others.
    """

    def __init__(self, *sinks: OutputSink) -> None:
        self._sinks = sinks

    def result(self, payload: Any) -> None:
        for sink in self._sinks:
            with suppress(Exception):
                sink.result(payload)

    def status(self, message: str) -> None:
        for sink in self._sinks:
            with suppress(Exception):
                sink.status(message)

    def warning(self, message: str) -> None:
        for sink in self._sinks:
            with suppress(Exception):
                sink.warning(message)

    def error(self, message: str, exit_code: int = 1) -> None:
        for sink in self._sinks:
            with suppress(Exception):
                sink.error(message, exit_code)

    def heartbeat(self, message: str) -> None:
        for sink in self._sinks:
            with suppress(Exception):
                sink.heartbeat(message)

    def event(self, payload: dict[str, Any]) -> None:
        for sink in self._sinks:
            with suppress(Exception):
                sink.event(payload)

    def flush(self) -> None:
        for sink in self._sinks:
            with suppress(Exception):
                flush_fn = getattr(sink, "flush", None)
                if callable(flush_fn):
                    flush_fn()
