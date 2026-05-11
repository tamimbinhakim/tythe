"""Request context and dependency injection."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar, overload

if TYPE_CHECKING:
    from starlette.requests import Request

T = TypeVar("T")


@dataclass(slots=True)
class Context:
    """Per-request context. Reach for ``ctx.request`` if you need the raw Starlette object."""

    request: Request
    user: Any | None = None

    @property
    def headers(self) -> dict[str, str]:
        return {k.decode().lower(): v.decode() for k, v in self.request.scope.get("headers", [])}

    @property
    def cookies(self) -> dict[str, str]:
        return dict(self.request.cookies)

    async def is_disconnected(self) -> bool:
        return await self.request.is_disconnected()


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
