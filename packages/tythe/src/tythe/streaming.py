"""Streaming primitives.

``stream[T]`` is the marker the codegen looks for on a handler's return
annotation; the runtime encodes yielded values as tagged-JSON SSE frames.

Handlers can also yield ``SsePayload`` to attach an ``id:`` field per
event. The TS client tracks the last seen id and sends it as
``Last-Event-Id`` on reconnect, so production streams can resume cleanly.
On the server side, the resume cursor surfaces as ``ctx.headers.get('last-event-id')``.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterable, AsyncIterator
from dataclasses import dataclass
from typing import Any, Generic, TypeVar, get_args, get_origin

import msgspec

T = TypeVar("T")

stream = AsyncIterator
"""Annotate streaming handlers with ``-> stream[T]``. Equivalent to ``AsyncIterator[T]``."""


@dataclass(slots=True)
class SsePayload(Generic[T]):
    """A streaming event with an explicit SSE ``id:`` (and optional retry hint).

    Yield ``SsePayload(value, id="evt-42")`` instead of bare ``value`` to give
    the client a resume cursor. The TS client records the most recent ``id``
    and replays it as ``Last-Event-Id`` if the connection drops.

    ``retry_ms`` translates to the SSE ``retry:`` field — the client backs off
    by at least that many milliseconds before reconnecting.
    """

    data: T
    id: str | None = None
    retry_ms: int | None = None


def is_stream_annotation(annotation: object) -> bool:
    return get_origin(annotation) in {AsyncIterator, AsyncIterable, AsyncGenerator}


def stream_event_type(annotation: object) -> Any:
    args = get_args(annotation)
    return args[0] if args else None


_encoder = msgspec.json.Encoder()


def encode_frame(value: object) -> bytes:
    """Encode an SSE frame.

    Plain values go out as ``data: <json>\\n\\n``. ``SsePayload`` instances
    additionally emit ``id:`` and ``retry:`` lines per the SSE spec.
    """
    if isinstance(value, SsePayload):
        # ``SsePayload`` is Generic[T]; widening to ``Any`` here avoids
        # pyright-strict's "Unknown type parameter" propagation downstream.
        from typing import cast as _cast

        payload = _cast("SsePayload[Any]", value)  # type: ignore[redundant-cast]
        parts: list[bytes] = []
        if payload.id is not None:
            parts.append(b"id: " + payload.id.encode("utf-8") + b"\n")
        if payload.retry_ms is not None:
            parts.append(b"retry: " + str(payload.retry_ms).encode("ascii") + b"\n")
        parts.append(b"data: " + _encoder.encode(payload.data) + b"\n\n")
        return b"".join(parts)
    return b"data: " + _encoder.encode(value) + b"\n\n"


def encode_done() -> bytes:
    return b"event: done\ndata: {}\n\n"
