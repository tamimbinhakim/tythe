"""End-to-end ASGI tests using httpx's in-process transport.

These exercise the actual request path: parameter resolution, msgspec
decoding, response encoding, typed errors, streaming, and DI.
"""

# pyright: basic
# Tests don't need strict typing; handlers are also consumed via decorator side effects.

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated

import httpx
import msgspec
import pytest

from tythe import App, Context, Depends, raises, stream
from tythe.params import Body, Header


@pytest.fixture
def client_factory():
    def _make(app: App) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")

    return _make


async def test_unary_get_with_path_param(client_factory):
    app = App()

    @app.get("/users/{user_id}")
    async def get_user(user_id: int) -> dict[str, int]:
        return {"id": user_id}

    async with client_factory(app) as client:
        r = await client.get("/users/42")
    assert r.status_code == 200
    assert r.json() == {"id": 42}


async def test_post_struct_body(client_factory):
    class CreatePost(msgspec.Struct):
        title: str
        body: str
        tags: list[str] = []

    app = App()

    @app.post("/posts")
    async def create(data: CreatePost) -> dict[str, str]:
        return {"title": data.title, "body": data.body}

    async with client_factory(app) as client:
        r = await client.post("/posts", json={"title": "hi", "body": "world"})
    assert r.status_code == 200
    assert r.json() == {"title": "hi", "body": "world"}


async def test_embedded_body_params(client_factory):
    app = App()

    @app.post("/login")
    async def login(
        email: Annotated[str, Body()],
        password: Annotated[str, Body()],
    ) -> dict[str, str]:
        return {"email": email, "pw_len": str(len(password))}

    async with client_factory(app) as client:
        r = await client.post("/login", json={"email": "a@b.com", "password": "secret"})
    assert r.json() == {"email": "a@b.com", "pw_len": "6"}


async def test_query_param_coercion(client_factory):
    app = App()

    @app.get("/search")
    async def search(q: str, limit: int = 10) -> dict[str, int | str]:
        return {"q": q, "limit": limit}

    async with client_factory(app) as client:
        r = await client.get("/search?q=hi&limit=5")
    assert r.json() == {"q": "hi", "limit": 5}


async def test_header_param(client_factory):
    app = App()

    @app.get("/whoami")
    async def whoami(ua: Annotated[str, Header(alias="user-agent")] = "") -> dict[str, str]:
        return {"ua": ua}

    async with client_factory(app) as client:
        r = await client.get("/whoami", headers={"user-agent": "tythe-test"})
    assert r.json() == {"ua": "tythe-test"}


async def test_context_injected(client_factory):
    app = App()

    @app.get("/ctx")
    async def ctx(ctx: Context) -> dict[str, str]:
        return {"path": str(ctx.request.url.path)}

    async with client_factory(app) as client:
        r = await client.get("/ctx")
    assert r.json() == {"path": "/ctx"}


async def test_typed_error_wraps_in_result(client_factory):
    @dataclass
    class PostNotFound(Exception):
        post_id: int

    app = App()

    @app.get("/posts/{post_id}")
    @raises(PostNotFound)
    async def get_post(post_id: int) -> dict[str, int]:
        raise PostNotFound(post_id=post_id)

    async with client_factory(app) as client:
        r = await client.get("/posts/7")
    assert r.status_code == 200
    body = r.json()
    assert body == {"ok": False, "error": {"kind": "PostNotFound", "post_id": 7}}


async def test_typed_success_wraps_in_result(client_factory):
    class Err(Exception):
        pass

    app = App()

    @app.get("/ok")
    @raises(Err)
    async def ok_handler() -> int:
        return 99

    async with client_factory(app) as client:
        r = await client.get("/ok")
    assert r.json() == {"ok": True, "data": 99}


async def test_streaming_endpoint_emits_sse(client_factory):
    class Token(msgspec.Struct, tag_field="kind", tag="token"):
        text: str

    class Done(msgspec.Struct, tag_field="kind", tag="done"):
        count: int

    app = App()

    @app.get("/chat")
    async def chat() -> stream[Token | Done]:
        yield Token(text="hello")
        yield Token(text="world")
        yield Done(count=2)

    async with client_factory(app) as client:
        r = await client.get("/chat")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")

    frames: list[dict] = []
    for chunk in r.text.split("\n\n"):
        chunk = chunk.strip()
        if not chunk or chunk.startswith("event: done"):
            continue
        for line in chunk.splitlines():
            if line.startswith("data: "):
                frames.append(json.loads(line[6:]))
    assert frames == [
        {"kind": "token", "text": "hello"},
        {"kind": "token", "text": "world"},
        {"kind": "done", "count": 2},
    ]


async def test_depends_resolution(client_factory):
    def db() -> dict[str, str]:
        return {"name": "memdb"}

    app = App()

    @app.get("/db")
    async def get_db(d: dict[str, str] = Depends(db)) -> dict[str, str]:
        return d

    async with client_factory(app) as client:
        r = await client.get("/db")
    assert r.json() == {"name": "memdb"}


async def test_depends_with_generator_teardown(client_factory):
    teardown_log: list[str] = []

    def session() -> Iterator[str]:
        teardown_log.append("open")
        yield "session-1"
        teardown_log.append("close")

    app = App()

    @app.get("/s")
    async def use_session(s: str = Depends(session)) -> dict[str, str]:
        return {"s": s}

    async with client_factory(app) as client:
        r = await client.get("/s")
    assert r.json() == {"s": "session-1"}
    assert teardown_log == ["open", "close"]


async def test_query_param_default_when_missing(client_factory):
    app = App()

    @app.get("/items")
    async def list_items(limit: int = 25) -> dict[str, int]:
        return {"limit": limit}

    async with client_factory(app) as client:
        r = await client.get("/items")
    assert r.json() == {"limit": 25}


async def test_missing_required_query_param_422(client_factory):
    app = App()

    @app.get("/needs")
    async def needs(name: str) -> dict[str, str]:
        return {"name": name}

    async with client_factory(app) as client:
        r = await client.get("/needs")
    assert r.status_code == 422


async def test_unhandled_exception_500(client_factory):
    app = App()

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("not declared")

    async with client_factory(app) as client:
        with pytest.raises(Exception):
            await client.get("/boom")
