"""Cover the less-trodden branches in tythe.errors."""

# pyright: basic

from __future__ import annotations

from dataclasses import dataclass

from tythe.errors import exception_to_payload, get_declared_raises, raises


def test_exception_with_to_dict_method() -> None:
    class CustomError(Exception):
        def to_dict(self) -> dict[str, int]:
            return {"code": 42, "retry_after": 5}

    payload = exception_to_payload(CustomError())
    assert payload["kind"] == "CustomError"
    assert payload["code"] == 42
    assert payload["retry_after"] == 5


def test_exception_dataclass_path() -> None:
    @dataclass
    class NotFound(Exception):
        resource_id: int

    payload = exception_to_payload(NotFound(resource_id=99))
    assert payload == {"kind": "NotFound", "resource_id": 99}


def test_exception_dict_attrs_path() -> None:
    class Boom(Exception):
        def __init__(self) -> None:
            super().__init__()
            self.context = "boom"
            self.code = 7

    payload = exception_to_payload(Boom())
    assert payload["kind"] == "Boom"
    assert payload["context"] == "boom"
    assert payload["code"] == 7


def test_exception_bare_falls_back_to_message() -> None:
    payload = exception_to_payload(RuntimeError("nope"))
    assert payload["kind"] == "RuntimeError"
    assert payload["message"] == "nope"


def test_raises_decorator_aggregates() -> None:
    class A(Exception): ...

    class B(Exception): ...

    @raises(A)
    @raises(B)
    def fn() -> None: ...

    assert set(get_declared_raises(fn)) == {A, B}


def test_get_declared_raises_default_empty() -> None:
    def fn() -> None: ...

    assert get_declared_raises(fn) == ()
