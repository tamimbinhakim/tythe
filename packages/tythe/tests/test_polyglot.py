"""Polyglot codegen tests — Swift + Kotlin renderers emit working clients."""

# pyright: basic

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

import msgspec

from tythe import App, raises, stream
from tythe.ir import build_ir
from tythe.params import Header, Query
from tythe.polyglot import render_kotlin, render_swift


def _build_full_ir():
    """A small app exercising path, query, header, body, raises, stream."""

    class Post(msgspec.Struct):
        id: int
        title: str
        author_name: str  # snake_case → camelCase mapping

    class CreatePost(msgspec.Struct):
        title: str
        body: str

    @dataclass
    class PostNotFound(Exception):
        post_id: int

    @dataclass
    class Forbidden(Exception):
        reason: str

    class Tick(msgspec.Struct, tag_field="kind", tag="tick"):
        n: int

    app = App()

    @app.get("/posts/{post_id}")
    @raises(PostNotFound, Forbidden)
    async def get_post(
        post_id: int,
        authorization: Annotated[str, Header()] = "",
    ) -> Post:
        del authorization
        return Post(id=post_id, title="x", author_name="ada")

    @app.post("/posts")
    async def create_post(data: CreatePost) -> Post:
        return Post(id=1, title=data.title, author_name="ada")

    @app.get("/search")
    async def search(q: Annotated[str, Query()]) -> list[Post]:
        return [Post(id=1, title=q, author_name="ada")]

    @app.get("/feed")
    async def feed() -> stream[Tick]:
        yield Tick(n=1)

    return build_ir(app)


# ----------------------- Swift ----------------------- #


def test_swift_emits_preamble_and_client() -> None:
    out = render_swift(_build_full_ir())
    assert "import Foundation" in out
    assert "public struct TytheClient" in out
    assert "convertToSnakeCase" in out  # encoder snake_case mapping
    assert "convertFromSnakeCase" in out  # decoder snake_case mapping
    assert "public enum TytheRPCError" in out


def test_swift_struct_with_camel_fields() -> None:
    out = render_swift(_build_full_ir())
    assert "public struct Post: Codable" in out
    assert "public let id: Int" in out
    assert "public let title: String" in out
    # author_name → authorName via JSONEncoder/Decoder strategies
    assert "public let authorName: String" in out


def test_swift_method_with_path_query_header() -> None:
    out = render_swift(_build_full_ir())
    assert "func getPost(postId: Int, authorization: String)" in out
    assert 'path = path.replacingOccurrences(of: "{post_id}"' in out
    # query method
    assert "func search(q: String)" in out
    assert 'URLQueryItem(name: "q"' in out
    # header
    assert 'forHTTPHeaderField: "authorization"' in out


def test_swift_method_with_body_param() -> None:
    out = render_swift(_build_full_ir())
    assert "func createPost(data: CreatePost)" in out
    assert "TytheClient.encoder.encode(data)" in out


def test_swift_emits_error_enum_for_raises() -> None:
    out = render_swift(_build_full_ir())
    assert "public enum GetPostError: Error {" in out
    assert "case postNotFound(PostNotFound)" in out
    assert "case forbidden(Forbidden)" in out


def test_swift_streaming_method_returns_async_throwing_stream() -> None:
    out = render_swift(_build_full_ir())
    # Stream endpoint surfaces an AsyncThrowingStream of the event type.
    assert "func feed() async throws -> AsyncThrowingStream<Tick, Error>" in out
    assert "session.bytes(for: req)" in out
    assert 'eventName == "done"' in out
    assert 'eventName == "error"' in out
    assert "TytheClient.decoder.decode(Tick.self" in out


# ----------------------- Kotlin ----------------------- #


def test_kotlin_emits_preamble_and_client() -> None:
    out = render_kotlin(_build_full_ir(), package="demo.api")
    assert "package demo.api" in out
    assert "class TytheClient(" in out
    assert "class TytheRPCError" in out
    assert "kotlinx.serialization.Serializable" in out


def test_kotlin_data_class_with_serialname() -> None:
    out = render_kotlin(_build_full_ir())
    assert "data class Post(" in out
    # snake_case → camelCase via @SerialName
    assert '@SerialName("author_name") val authorName: String' in out


def test_kotlin_method_with_path_query_header() -> None:
    out = render_kotlin(_build_full_ir())
    assert "suspend fun getPost(postId: Long, authorization: String):" in out
    assert 'path.replace("{post_id}"' in out
    assert 'put("authorization"' in out
    # query
    assert "suspend fun search(q: String):" in out
    assert '"q" to q.toString()' in out


def test_kotlin_method_with_body_encodes_struct() -> None:
    out = render_kotlin(_build_full_ir())
    assert "suspend fun createPost(data: CreatePost):" in out
    assert "tytheJson.encodeToString(data)" in out


def test_kotlin_emits_sealed_class_for_raises() -> None:
    out = render_kotlin(_build_full_ir())
    assert "sealed class GetPostError" in out
    assert "Is PostNotFound".replace(" ", "") in out  # IsPostNotFound
    assert "IsForbidden" in out


def test_kotlin_streaming_returns_flow() -> None:
    out = render_kotlin(_build_full_ir())
    # Stream endpoint returns a Flow<EventT> backed by an SSE parser.
    assert "fun feed(): kotlinx.coroutines.flow.Flow<Tick>" in out
    assert "flow {" in out
    assert "tytheJson.decodeFromString<Tick>" in out
    assert "event: text/event-stream" in out or 'Accept", "text/event-stream' in out
    assert "Dispatchers.IO" in out
