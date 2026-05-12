"""WebSocket bidirectional channel — handler-side primitive.

Use ``@app.websocket(path)`` to register a route whose handler accepts a
``BidiChannel[S, R]``. The runtime dispatches the underlying Starlette
WebSocket to your handler with a typed channel:

    @app.websocket("/chat")
    async def chat(channel: BidiChannel[ServerMsg, ClientMsg]) -> None:
        await channel.accept()
        async for msg in channel:
            await channel.send(ServerMsg(kind="echo", payload=msg.payload))

Wire format: JSON text frames, msgspec-encoded. Inbound frames are
``msgspec.json.decode``-d into ``R``; outbound frames are
``msgspec.json.encode``-d from ``S``.

TS-side codegen for ``BidiChannel`` is on the v0.2.x roadmap. Today
clients hand-write the WebSocket connection until that lands.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, Generic, TypeVar, get_args, get_origin

import msgspec

if TYPE_CHECKING:
    from starlette.websockets import WebSocket

S = TypeVar("S")
R = TypeVar("R")


class BidiChannel(Generic[S, R]):
    """Server-side handle to a connected WebSocket, parameterised on send/recv types.

    Iterate with ``async for msg in channel`` to receive client messages of
    type ``R``; call ``await channel.send(value)`` to push a server message
    of type ``S``. ``accept()`` must be called before either side speaks;
    ``close()`` cleanly hangs up.
    """

    __slots__ = ("_decoder", "_encoder", "_ws", "recv_type", "send_type")

    def __init__(self, ws: WebSocket, send_type: Any, recv_type: Any) -> None:
        self._ws = ws
        self.send_type = send_type
        self.recv_type = recv_type
        self._encoder: msgspec.json.Encoder = msgspec.json.Encoder()
        # Decoder is built lazily so that None/Any recv types don't choke msgspec.
        self._decoder: msgspec.json.Decoder[Any] | None = (
            msgspec.json.Decoder(recv_type) if recv_type not in (None, Any) else None
        )

    async def accept(self) -> None:
        await self._ws.accept()

    async def send(self, value: S) -> None:
        await self._ws.send_bytes(self._encoder.encode(value))

    async def receive(self) -> R:
        text = await self._ws.receive_text()
        decoded: Any
        if self._decoder is None:
            decoded = msgspec.json.decode(text.encode("utf-8"))
        else:
            decoded = self._decoder.decode(text.encode("utf-8"))
        return decoded  # type: ignore[no-any-return]

    async def close(self, code: int = 1000) -> None:
        await self._ws.close(code=code)

    def __aiter__(self) -> AsyncIterator[R]:
        return self._iter()

    async def _iter(self) -> AsyncIterator[R]:
        try:
            while True:
                yield await self.receive()
        except Exception:
            return


# Type-level shorthand: ``bidi[S, R]`` reads better in a handler signature
# than ``BidiChannel[S, R]`` and mirrors ``stream[T]``.
bidi = BidiChannel


def is_bidi_annotation(annotation: object) -> bool:
    return get_origin(annotation) is BidiChannel or annotation is BidiChannel


def bidi_types(annotation: object) -> tuple[Any, Any] | None:
    args = get_args(annotation)
    if len(args) != 2:
        return None
    return args[0], args[1]
