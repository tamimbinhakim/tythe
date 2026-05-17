"""IR + codegen tests."""

# pyright: basic
# Tests don't need strict typing; handlers are also consumed via decorator side effects.

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

import msgspec
import pytest

from dyadpy import App, raises, stream
from dyadpy.codegen import render, write
from dyadpy.ir import build_ir
from dyadpy.params import Body, Header


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
    assert 'import type { CallOptions, RouteDescriptor } from "@dyadpy/ts";' in out
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
    assert 'import type { CallOptions, RouteDescriptor } from "@dyadpy/ts";' in out
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
    assert 'import type { CallOptions, Result, RouteDescriptor } from "@dyadpy/ts";' in out


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


def test_large_struct_wraps_to_multi_line() -> None:
    """Structs past the inline-field threshold render one field per line."""

    class BigStruct(msgspec.Struct):
        a: int
        b: int
        c: int
        d: int
        e: int

    app = App()

    @app.post("/big")
    async def big(data: BigStruct) -> BigStruct:
        return data

    out = render(build_ir(app))
    assert "export type BigStruct = {\n  a: number;\n" in out
    # Trailing comma on the close brace's preceding line is preserved.
    assert "  e: number;\n};" in out


def test_small_struct_stays_inline() -> None:
    """≤ 3-field structs without nested objects stay on one line."""

    class Tiny(msgspec.Struct):
        a: int
        b: str

    app = App()

    @app.post("/tiny")
    async def tiny(data: Tiny) -> Tiny:
        return data

    out = render(build_ir(app))
    assert "export type Tiny = { a: number; b: string };" in out


def test_handler_docstring_emitted_as_jsdoc() -> None:
    """Handler ``__doc__`` surfaces as JSDoc above the route method signature."""
    app = App()

    @app.get("/ping")
    async def ping() -> str:
        """Health probe — returns the literal string ``pong``."""
        return "pong"

    out = render(build_ir(app))
    assert "/** Health probe — returns the literal string ``pong``. */" in out


def test_multi_line_docstring_becomes_block_jsdoc() -> None:
    """Docstrings with multiple lines render as ``/**\\n * ... \\n */`` blocks."""
    app = App()

    @app.get("/x")
    async def x() -> int:
        """First line.

        Second paragraph with extra detail.
        """
        return 1

    out = render(build_ir(app))
    assert "/**\n   * First line." in out
    assert "* Second paragraph with extra detail." in out


def test_msgspec_auto_title_not_emitted_as_jsdoc() -> None:
    """msgspec emits ``title=<ClassName>`` on every Struct; that's noise, not docs."""

    class Plain(msgspec.Struct):
        x: int

    app = App()

    @app.post("/plain")
    async def plain(data: Plain) -> Plain:
        return data

    out = render(build_ir(app))
    # The redundant `/** Plain */` JSDoc above `export type Plain` must NOT appear.
    assert "/** Plain */\nexport type Plain" not in out


def test_struct_docstring_emitted_as_jsdoc() -> None:
    """A Struct docstring surfaces as JSDoc above its TS type declaration."""

    class Thing(msgspec.Struct):
        """A thing that lives in the system."""

        id: int

    app = App()

    @app.post("/things")
    async def create(data: Thing) -> Thing:
        return data

    out = render(build_ir(app))
    assert "/** A thing that lives in the system. */\nexport type Thing" in out


def test_route_descriptor_wraps_when_long() -> None:
    """Long route descriptors break onto multiple lines with trailing commas."""
    app = App()

    @app.get("/posts")
    async def list_posts(
        tag: Annotated[list[str] | None, Header()] = None,
        cursor: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, int]]:
        return []

    out = render(build_ir(app))
    # The multi-param list should wrap with item-per-line and trailing commas.
    assert 'params: [\n      { name: "tag",' in out
    assert "    ],\n  }," in out


def test_long_method_signature_wraps_args() -> None:
    """When the inline method signature exceeds the line budget, args break out."""
    app = App()

    @app.get("/search")
    async def search_with_many_filters(
        query: str,
        category: str,
        tag: str,
        author: str,
        sort: str,
        cursor: str | None = None,
    ) -> list[dict[str, str]]:
        return []

    out = render(build_ir(app))
    # Args + opts wrap to their own lines once the inline form exceeds 100 cols.
    assert "searchWithManyFilters(\n    args:" in out
    assert "opts?: CallOptions,\n  )" in out


def test_struct_named_array_gets_renamed_to_avoid_shadowing_builtin() -> None:
    """A user struct called ``Array`` must not be emitted as ``export type Array``."""

    class Array(msgspec.Struct):
        items: list[int]

    app = App()

    @app.post("/arr")
    async def arr(data: Array) -> Array:
        return data

    out = render(build_ir(app))
    assert "export type Array =" not in out
    # The render path always uses the disambiguated name, both for the type
    # declaration and at every reference site — so no orphaned `Array` refs.
    assert "export type Array " not in out


def test_struct_named_delete_gets_renamed() -> None:
    """JS reserved words like ``delete`` are not valid top-level type names."""

    class delete(msgspec.Struct):
        x: int

    app = App()

    @app.post("/d")
    async def d(data: delete) -> delete:
        return data

    out = render(build_ir(app))
    assert "export type delete " not in out


def test_route_name_collision_raises() -> None:
    """Two routes that camelCase to the same TS name fail loudly at render."""
    app = App()

    @app.get("/a")
    async def get_user() -> int:
        return 1

    @app.get("/b")
    async def getUser() -> int:  # collision with `get_user` is the point of the test
        return 2

    ir = build_ir(app)
    with pytest.raises(ValueError, match="getUser"):
        render(ir)


def test_enum_const_collision_with_type_name_gets_enum_suffix() -> None:
    """If ``UserRole`` is already a user-defined type, the enum const becomes ``UserRoleEnum``."""

    class UserRole(msgspec.Struct):
        slug: str

    class User(msgspec.Struct):
        id: int
        role: Literal["admin", "member"]

    app = App()

    @app.get("/users/{user_id}")
    async def get_user(user_id: int) -> User:
        return User(id=user_id, role="admin")

    @app.get("/roles")
    async def list_roles() -> list[UserRole]:
        return []

    out = render(build_ir(app))
    assert "export type UserRole =" in out  # User struct keeps its name.
    # Enum const renamed to avoid clobbering the type.
    assert "export const UserRoleEnum = " in out
    assert "export const UserRole = " not in out


def test_duplicate_enum_const_names_get_numeric_suffix() -> None:
    """Two structs that both produce a ``StatusValue`` const each get unique names."""

    class A(msgspec.Struct):
        status: Literal["a", "b"]

    class B(msgspec.Struct):
        status: Literal["c", "d"]

    app = App()

    @app.get("/a")
    async def aa() -> A:
        return A(status="a")

    @app.get("/b")
    async def bb() -> B:
        return B(status="c")

    out = render(build_ir(app))
    # Both structs get their own status const, distinct names.
    assert "export const AStatus = " in out
    assert "export const BStatus = " in out


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


# Module-scope types for the generics test. msgspec resolves forward refs in
# the class's own globals, so these can't live inside the test function when
# ``from __future__ import annotations`` is active.
from typing import Generic, TypeVar  # noqa: E402

_GenT = TypeVar("_GenT")
_GenE = TypeVar("_GenE")


class _GenBadRequest(Exception):
    """Stand-in for a typed HTTP error inside a generic type parameter."""


class _GenFailure(msgspec.Struct, Generic[_GenT, _GenE]):
    input: _GenT
    error: _GenE


class _GenBatchOut(msgspec.Struct, Generic[_GenT, _GenE]):
    ok: list[_GenT]
    failed: list[_GenFailure[_GenT, _GenE]]


class _GenItem(msgspec.Struct):
    name: str


def test_generic_struct_with_exception_in_type_args() -> None:
    """User-defined generics with an Exception class inside (e.g. ``BatchResult[T, E]``)
    must flow through the IR — msgspec needs the schema_hook the IR installs.
    """
    app = App()

    @app.post("/bulk")
    async def bulk(items: list[_GenItem]) -> _GenBatchOut[_GenItem, _GenBadRequest]:
        return _GenBatchOut(ok=[], failed=[])

    out = render(build_ir(app))
    # The generic parameterization reaches the components map; the error's
    # synthesized tagged Struct surfaces inline so the TS client can narrow
    # on ``error.kind``.
    assert "GenBatchOut" in out
    assert "kind" in out
