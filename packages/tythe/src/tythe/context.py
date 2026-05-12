"""Request context and dependency injection."""

from __future__ import annotations

import contextvars
import inspect
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, TypeVar, overload

if TYPE_CHECKING:
    from starlette.requests import Request

T = TypeVar("T")

AfterCallback = tuple[Callable[..., Any], tuple[Any, ...], dict[str, Any]]


def _empty_headers() -> dict[str, str]:
    return {}


def _empty_callbacks() -> list[AfterCallback]:
    return []


@dataclass(slots=True)
class Context:
    """Per-request context. Reach for ``ctx.request`` if you need the raw Starlette object.

    Fields named ``response_*`` and ``after_callbacks`` are populated by handler
    methods (``set_status``, ``set_header``, ``after``) and consumed by the runtime
    when building the final response. Direct mutation works but the methods are
    the documented surface.
    """

    request: Request
    user: Any | None = None
    response_status: int | None = None
    response_headers: dict[str, str] = field(default_factory=_empty_headers)
    after_callbacks: list[AfterCallback] = field(default_factory=_empty_callbacks)

    @property
    def headers(self) -> dict[str, str]:
        return {k.decode().lower(): v.decode() for k, v in self.request.scope.get("headers", [])}

    @property
    def cookies(self) -> dict[str, str]:
        return dict(self.request.cookies)

    async def is_disconnected(self) -> bool:
        return await self.request.is_disconnected()

    def set_status(self, code: int) -> None:
        """Override the response status code (default is 200)."""
        self.response_status = code

    def set_header(self, name: str, value: str) -> None:
        """Add or replace a response header."""
        self.response_headers[name] = value

    def after(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        """Run ``fn`` after the response is sent. Equivalent to free ``tythe.after``."""
        self.after_callbacks.append((fn, args, kwargs))


# Contextvar so free-function ``after(...)`` can find the current Context
# without the handler having to thread one through. The runtime sets this
# around each handler invocation; outside of a handler the var is unset and
# calling ``after`` raises.
current_context_var: contextvars.ContextVar[Context] = contextvars.ContextVar(
    "_tythe_current_context",
)


def after(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
    """Register a callback to run after the response is sent.

    Errors raised inside the callback are surfaced to logs but never bubble
    to the client (the response has already been written). Use for fire-and-
    forget side effects: webhook fan-out, audit logs, cache warming.

    >>> @app.post("/posts")
    >>> async def create_post(data: CreatePost) -> Post:
    ...     post = save(data)
    ...     after(notify_webhook, post.id)
    ...     return post
    """
    try:
        ctx = current_context_var.get()
    except LookupError as exc:
        raise RuntimeError(
            "tythe.after(...) called outside a request handler",
        ) from exc
    ctx.after(fn, *args, **kwargs)


async def run_after_callbacks(callbacks: list[AfterCallback]) -> None:
    """Run every registered after-callback, swallowing exceptions per-callback."""
    for fn, args, kwargs in callbacks:
        try:
            result = fn(*args, **kwargs)
            if inspect.isawaitable(result):
                await result
        except Exception:
            pass


@dataclass(slots=True, frozen=True)
class Dependency:
    """Marker the runtime sees on a parameter default to know it's DI-resolved."""

    provider: Callable[..., Any]
    use_cache: bool = True


@overload
def Depends(provider: Callable[..., Iterator[T]], *, use_cache: bool = ...) -> T: ...
@overload
def Depends(provider: Callable[..., AsyncIterator[T]], *, use_cache: bool = ...) -> T: ...
@overload
def Depends(provider: Callable[..., Awaitable[T]], *, use_cache: bool = ...) -> T: ...
@overload
def Depends(provider: Callable[..., T], *, use_cache: bool = ...) -> T: ...
def Depends(provider: Callable[..., Any], *, use_cache: bool = True) -> Any:
    """Mark a parameter as DI-provided.

    The handler sees the yielded/returned value of ``provider``. The runtime
    intercepts ``Depends(...)`` before the handler is ever called, so the
    "default value" is never actually evaluated as the marker.

    Providers can be plain functions, async functions, sync generators yielding
    once, or async generators yielding once. The post-``yield`` body runs as
    teardown after the response is finalized.
    """
    return Dependency(provider=provider, use_cache=use_cache)
