"""Typed errors and the ``Result`` envelope.

A handler decorated with ``@raises(E1, E2)`` returns the envelope::

    { "ok": true,  "data": ... }
    { "ok": false, "error": { "kind": "E1", ...fields } }

Handlers with no ``@raises`` return the bare value — keeps the simple case simple.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., object])

_RAISES_ATTR = "__tythe_raises__"


def raises(*exc_types: type[Exception]) -> Callable[[F], F]:
    """Declare typed exceptions a handler may raise.

    >>> from dataclasses import dataclass
    >>> @dataclass
    ... class NotEnoughCredits(Exception):
    ...     remaining: int
    ...     required: int
    >>>
    >>> @raises(NotEnoughCredits)
    ... async def boost() -> None: ...
    """

    def decorator(handler: F) -> F:
        existing: tuple[type[Exception], ...] = getattr(handler, _RAISES_ATTR, ())
        setattr(handler, _RAISES_ATTR, existing + tuple(exc_types))
        return handler

    return decorator


def get_declared_raises(handler: object) -> tuple[type[Exception], ...]:
    return getattr(handler, _RAISES_ATTR, ())


def exception_to_payload(exc: Exception) -> dict[str, Any]:
    """Serialize an exception to ``{ "kind": ClassName, ...fields }``.

    Tries, in order: ``exc.to_dict()`` → ``dataclasses.asdict`` → ``__dict__`` → ``str(exc)``.
    """
    body: dict[str, Any]
    to_dict: Any = getattr(exc, "to_dict", None)
    if callable(to_dict):
        raw: Any = to_dict()
        body = {str(k): v for k, v in dict(raw).items()}
    elif _is_dataclass_instance(exc):
        body = asdict(exc)  # type: ignore[call-overload]
    elif getattr(exc, "__dict__", None):
        body = {k: v for k, v in exc.__dict__.items() if not k.startswith("_")}
    else:
        body = {"message": str(exc)}
    return {"kind": type(exc).__name__, **body}


def _is_dataclass_instance(obj: object) -> bool:
    # ``obj: object`` keeps Pylance from carrying caller-side narrowing into the
    # ``hasattr`` argument (where it would otherwise become a union with Struct).
    return hasattr(obj, "__dataclass_fields__")
