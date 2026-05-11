"""Streaming primitives.

``stream[T]`` is the marker the codegen looks for on a handler's return
annotation; the runtime encodes yielded values as tagged-JSON SSE frames.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterable, AsyncIterator
from typing import Any, TypeVar, get_args, get_origin

import msgspec

T = TypeVar("T")

stream = AsyncIterator
"""Annotate streaming handlers with ``-> stream[T]``. Equivalent to ``AsyncIterator[T]``."""


def is_stream_annotation(annotation: object) -> bool:
    return get_origin(annotation) in {AsyncIterator, AsyncIterable, AsyncGenerator}


def stream_event_type(annotation: object) -> Any:
    args = get_args(annotation)
    return args[0] if args else None


_encoder = msgspec.json.Encoder()


def encode_frame(value: object) -> bytes:
    return b"data: " + _encoder.encode(value) + b"\n\n"


def encode_done() -> bytes:
    return b"event: done\ndata: {}\n\n"
