"""WebSocket bidi[S, R] — handler-side end-to-end."""

# pyright: basic

from __future__ import annotations

import msgspec
import pytest
from starlette.testclient import TestClient

from tythe import App, BidiChannel, bidi
from tythe.bidi import bidi_types, is_bidi_annotation


class Inbound(msgspec.Struct, tag_field="kind", tag="echo"):
    text: str


class Outbound(msgspec.Struct, tag_field="kind", tag="echoed"):
    text: str


def test_bidi_alias_recognized() -> None:
    annot = bidi[Outbound, Inbound]
    assert is_bidi_annotation(annot)
    assert bidi_types(annot) == (Outbound, Inbound)


def test_websocket_route_registered() -> None:
    app = App()

    @app.websocket("/ws")
    async def chat(channel: BidiChannel[Outbound, Inbound]) -> None:
        await channel.accept()

    assert len(app.websocket_routes) == 1
    assert app.websocket_routes[0].path == "/ws"
    assert app.websocket_routes[0].send_type is Outbound
    assert app.websocket_routes[0].recv_type is Inbound


def test_websocket_handler_must_take_bidi() -> None:
    app = App()

    with pytest.raises(TypeError, match="BidiChannel"):

        @app.websocket("/ws")
        async def bad(thing: int) -> None:  # missing BidiChannel param
            del thing


def test_echo_roundtrip() -> None:
    app = App()

    @app.websocket("/echo")
    async def echo(channel: BidiChannel[Outbound, Inbound]) -> None:
        await channel.accept()
        async for msg in channel:
            await channel.send(Outbound(text=msg.text))

    with TestClient(app).websocket_connect("/echo") as ws:
        ws.send_text('{"kind":"echo","text":"hi"}')
        raw = ws.receive_bytes()
        assert b'"kind":"echoed"' in raw
        assert b'"text":"hi"' in raw


def test_close_is_clean() -> None:
    app = App()

    @app.websocket("/once")
    async def once(channel: BidiChannel[Outbound, Inbound]) -> None:
        await channel.accept()
        await channel.send(Outbound(text="hello"))
        await channel.close()

    with TestClient(app).websocket_connect("/once") as ws:
        assert b"hello" in ws.receive_bytes()
        # Server closed; iteration ends on the client too.
