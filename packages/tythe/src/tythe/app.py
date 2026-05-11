"""``App`` is both:

- A route registry that decorators append to (no metaclasses, no import-time magic).
- A callable ASGI application that delegates to Starlette.

Routes are declared eagerly, but reflection is lazy — the per-handler ``HandlerPlan``
is built on the first ASGI call. That keeps test ergonomics nice: you can build
an ``App``, inspect its routes, and never boot a server.
"""

from __future__ import annotations

import contextlib
import sys
from collections.abc import Awaitable, Callable, MutableMapping
from dataclasses import dataclass, field
from typing import Any, Literal

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route as StarletteRoute

from tythe.runtime import HandlerPlan, RouteRunner, build_plan

HttpMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE"]

# Handlers are either ``async def`` (Awaitable[T]) or async generators
# (AsyncIterator[T]) for streams. We accept anything callable; the runtime
# inspects the return annotation to decide.
Handler = Callable[..., Any]

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]


@dataclass(slots=True)
class Route:
    method: HttpMethod
    path: str
    handler: Handler
    name: str | None = None
    plan: HandlerPlan | None = None


def _new_routes() -> list[Route]:
    return []


@dataclass(slots=True)
class App:
    routes: list[Route] = field(default_factory=_new_routes)
    _starlette: Starlette | None = None

    def _register(self, method: HttpMethod, path: str) -> Callable[[Handler], Handler]:
        def decorator(handler: Handler) -> Handler:
            # Snapshot the caller's locals so ``typing.get_type_hints`` can resolve
            # types declared next to the handler. Without this, ``from __future__
            # import annotations`` leaves annotations as strings that
            # ``get_type_hints`` can't evaluate.
            with contextlib.suppress(AttributeError, ValueError):
                handler.__tythe_localns__ = dict(sys._getframe(1).f_locals)  # type: ignore[attr-defined]
            self.routes.append(Route(method=method, path=path, handler=handler))
            self.invalidate()
            return handler

        return decorator

    def get(self, path: str) -> Callable[[Handler], Handler]:
        return self._register("GET", path)

    def post(self, path: str) -> Callable[[Handler], Handler]:
        return self._register("POST", path)

    def put(self, path: str) -> Callable[[Handler], Handler]:
        return self._register("PUT", path)

    def patch(self, path: str) -> Callable[[Handler], Handler]:
        return self._register("PATCH", path)

    def delete(self, path: str) -> Callable[[Handler], Handler]:
        return self._register("DELETE", path)

    def invalidate(self) -> None:
        """Drop the cached Starlette app so it's rebuilt on the next request."""
        self._starlette = None

    def _build(self) -> Starlette:
        starlette_routes: list[StarletteRoute] = []
        for r in self.routes:
            if r.plan is None:
                r.plan = build_plan(r.handler, r.path)
            runner = RouteRunner(handler=r.handler, plan=r.plan)
            starlette_routes.append(
                StarletteRoute(
                    path=r.path,
                    endpoint=_endpoint_for(runner),
                    methods=[r.method],
                    name=r.name or r.handler.__name__,
                ),
            )
        return Starlette(routes=starlette_routes)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        app = self._starlette
        if app is None:
            app = self._build()
            self._starlette = app
        await app(scope, receive, send)


def _endpoint_for(runner: RouteRunner) -> Callable[[Request], Awaitable[Response]]:
    async def endpoint(request: Request) -> Response:
        return await runner.handle(request)

    return endpoint
