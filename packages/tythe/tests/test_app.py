"""Smoke tests for the public ``App`` surface."""

# pyright: basic

from __future__ import annotations

import pytest

from tythe import App, raises


@pytest.fixture
def app() -> App:
    return App()


def test_register_get(app: App) -> None:
    @app.get("/users/{user_id}")
    async def get_user(user_id: int) -> dict[str, int]:
        return {"id": user_id}

    assert len(app.routes) == 1
    route = app.routes[0]
    assert route.method == "GET"
    assert route.path == "/users/{user_id}"
    assert route.handler is get_user


def test_register_post(app: App) -> None:
    @app.post("/items")
    async def create() -> None:
        return None

    assert app.routes[0].method == "POST"
    assert app.routes[0].path == "/items"


def test_multiple_routes_preserve_order(app: App) -> None:
    @app.get("/a")
    async def a() -> None: ...

    @app.post("/b")
    async def b() -> None: ...

    @app.delete("/c")
    async def c() -> None: ...

    assert [r.path for r in app.routes] == ["/a", "/b", "/c"]
    assert [r.method for r in app.routes] == ["GET", "POST", "DELETE"]


def test_raises_decorator_stacks(app: App) -> None:
    class ErrA(Exception): ...

    class ErrB(Exception): ...

    @app.post("/boost")
    @raises(ErrA, ErrB)
    async def boost() -> None: ...

    from tythe.errors import get_declared_raises

    assert get_declared_raises(boost) == (ErrA, ErrB)
