"""IR + codegen tests."""

# pyright: basic
# Tests don't need strict typing; handlers are also consumed via decorator side effects.

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

import msgspec

from tythe import App, raises, stream
from tythe.codegen import render, write
from tythe.ir import build_ir
from tythe.params import Body, Header


def test_build_ir_captures_routes() -> None:
    app = App()

    @app.get("/ping")
    async def ping() -> str:
        return "pong"

    ir = build_ir(app)
    assert len(ir.routes) == 1
    assert ir.routes[0].path == "/ping"
    assert ir.routes[0].method == "GET"


def test_render_emits_header_and_routes() -> None:
    app = App()

    @app.get("/users/{user_id}")
    async def get_user(user_id: int) -> dict[str, int]:
        return {"id": user_id}

    out = render(build_ir(app))
    assert "AUTO-GENERATED" in out
    assert "/users/{user_id}" in out
    assert '"GET"' in out


def test_write_creates_parent_dirs(tmp_path: Path) -> None:
    app = App()

    @app.get("/x")
    async def x() -> int:
        return 1

    target = tmp_path / "nested" / "deep" / "client.ts"
    write(build_ir(app), target)
    assert target.exists()
    assert "AUTO-GENERATED" in target.read_text()


def test_struct_becomes_ts_type_declaration() -> None:
    class CreatePost(msgspec.Struct):
        title: str
        body: str
        tags: list[str] = []

    app = App()

    @app.post("/posts")
    async def create(data: CreatePost) -> CreatePost:
        return data

    out = render(build_ir(app))
    assert "export type CreatePost" in out
    assert "title: string" in out
    assert "tags?: Array<string>" in out


def test_streaming_endpoint_emits_asynciterable() -> None:
    class Token(msgspec.Struct, tag_field="kind", tag="token"):
        text: str

    app = App()

    @app.get("/chat")
    async def chat() -> stream[Token]:
        yield Token(text="hi")

    out = render(build_ir(app))
    assert "AsyncIterable<Token>" in out
    assert "streams: true" in out


def test_raises_emits_result_envelope() -> None:
    @dataclass
    class PostNotFound(Exception):
        post_id: int

    app = App()

    @app.get("/posts/{post_id}")
    @raises(PostNotFound)
    async def get_post(post_id: int) -> dict[str, int]:
        return {"id": post_id}

    out = render(build_ir(app))
    assert "Promise<Result<" in out
    assert "PostNotFound" in out
    assert "result: true" in out


def test_result_import_omitted_when_no_route_raises() -> None:
    """No `@raises(...)` anywhere → no `Result` in the type import, no unused import."""
    app = App()

    @app.get("/ping")
    async def ping() -> str:
        return "pong"

    out = render(build_ir(app))
    assert 'import type { CallOptions, RouteDescriptor } from "@tythe/ts";' in out
    assert "Result" not in out


def test_result_import_omitted_for_streaming_only_raises() -> None:
    """`@raises` on a streaming route surfaces as SSE error frames, not `Result`."""

    @dataclass
    class JobMissing(Exception):
        job_id: str

    class Tick(msgspec.Struct, tag_field="kind", tag="tick"):
        n: int

    app = App()

    @app.get("/jobs/{job_id}/events")
    @raises(JobMissing)
    async def watch(job_id: str) -> stream[Tick]:
        yield Tick(n=1)

    out = render(build_ir(app))
    assert 'import type { CallOptions, RouteDescriptor } from "@tythe/ts";' in out
    assert "Result<" not in out


def test_result_import_present_when_any_route_raises() -> None:
    @dataclass
    class NotFound(Exception):
        thing_id: int

    app = App()

    @app.get("/ping")
    async def ping() -> str:
        return "pong"

    @app.get("/thing/{thing_id}")
    @raises(NotFound)
    async def get_thing(thing_id: int) -> dict[str, int]:
        return {"id": thing_id}

    out = render(build_ir(app))
    assert 'import type { CallOptions, Result, RouteDescriptor } from "@tythe/ts";' in out


def test_descriptor_includes_param_locations() -> None:
    app = App()

    @app.get("/u/{user_id}")
    async def lookup(
        user_id: int,
        q: str,
        x_trace: Annotated[str, Header(alias="x-trace-id")] = "",
    ) -> dict[str, str]:
        return {"user_id": str(user_id), "q": q, "trace": x_trace}

    out = render(build_ir(app))
    assert 'in: "path"' in out
    assert 'in: "query"' in out
    assert 'in: "header"' in out
    assert '"x-trace-id"' in out


def test_embedded_body_params_marked_embed() -> None:
    app = App()

    @app.post("/login")
    async def login(
        email: Annotated[str, Body()],
        password: Annotated[str, Body()],
    ) -> dict[str, str]:
        return {"email": email, "pw_len": str(len(password))}

    out = render(build_ir(app))
    assert out.count("embed: true") == 2


def test_route_namespace_emitted_for_unary_with_raises() -> None:
    @dataclass
    class NotFound(Exception):
        post_id: int

    app = App()

    @app.get("/posts/{post_id}")
    @raises(NotFound)
    async def get_post(post_id: int) -> dict[str, int]:
        return {"id": post_id}

    out = render(build_ir(app))
    assert "export namespace Routes" in out
    assert "export namespace getPost" in out
    assert "export type Args = { postId: number }" in out
    assert "export type Data = " in out
    assert "export type Error = NotFound" in out
    assert "export type Return = Promise<Result<Data, Error>>" in out


def test_route_namespace_for_streaming_endpoint() -> None:
    class Token(msgspec.Struct, tag_field="kind", tag="token"):
        text: str

    app = App()

    @app.get("/chat")
    async def chat() -> stream[Token]:
        yield Token(text="hi")

    out = render(build_ir(app))
    assert "export namespace chat" in out
    assert "export type Event = Token" in out
    assert "export type Return = AsyncIterable<Event>" in out


def test_enum_field_emits_const_value_object() -> None:
    class Issue(msgspec.Struct):
        id: int
        status: Literal["open", "in_progress", "blocked", "closed"]

    app = App()

    @app.get("/issues/{issue_id}")
    async def get_issue(issue_id: int) -> Issue:
        return Issue(id=issue_id, status="open")

    out = render(build_ir(app))
    # The value-object exists at top-level…
    assert "export const IssueStatus = " in out
    # …with keys derived from the literal values, PascalCased.
    assert "Open: " in out
    assert "InProgress: " in out
    assert "Blocked: " in out
    assert "Closed: " in out


def test_kind_discriminator_skipped_for_enum_const() -> None:
    """Tag values (kind) are msgspec internals — no `EvenKind` const."""

    class Foo(msgspec.Struct, tag_field="kind", tag="foo"):
        x: int

    class Bar(msgspec.Struct, tag_field="kind", tag="bar"):
        y: int

    app = App()

    @app.get("/event")
    async def evt() -> Foo | Bar:
        return Foo(x=1)

    out = render(build_ir(app))
    # No `FooKind` / `BarKind` const should appear.
    assert "FooKind" not in out
    assert "BarKind" not in out


def test_exact_optional_vs_nullable() -> None:
    """T: msgspec's required + anyOf-with-null translate to TS correctly."""

    class Mixed(msgspec.Struct, kw_only=True):
        a: int  # required, non-null    → a: number
        b: int = 5  # default, non-null → b?: number
        c: int | None  # required, null → c: number | null
        d: int | None = None  # default, null → d?: number | null

    app = App()

    @app.post("/mixed")
    async def mixed(data: Mixed) -> Mixed:
        return data

    out = render(build_ir(app))
    # Order in msgspec output may vary; check each shape appears.
    assert "a: number" in out
    assert "a?: number" not in out
    assert "b?: number" in out
    assert "c: number | null" in out
    assert "d?: number | null" in out
