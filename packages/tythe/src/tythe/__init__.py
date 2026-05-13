"""Tythe — a type-safe RPC bridge between Python and TypeScript.

The function signature is the contract. See
https://github.com/tamimbinhakim/tythe for full docs.

``tythe.tasks`` is loaded lazily via PEP 562 — it drags ``asyncio``'s
unix-event-loop internals that only matter when you actually queue a
background job. Bidi is cheap to import eagerly (only ``msgspec`` at
runtime; ``starlette.websockets`` is ``TYPE_CHECKING``-only) so it stays
on the default path.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from tythe.app import App
from tythe.bidi import BidiChannel, bidi
from tythe.context import Context, Depends, after
from tythe.errors import raises
from tythe.params import Form
from tythe.streaming import SsePayload, stream

if TYPE_CHECKING:  # pragma: no cover - re-export shape only
    from tythe.tasks import (
        InMemoryBackend,
        TaskBackend,
        TaskState,
        mount_task_routes,
    )

# Raw-body sentinel: annotate a handler param or return with ``Bytes`` to
# skip the JSON envelope entirely. Identical to the ``bytes`` builtin; the
# alias is exported for documentation and explicit-intent reasons.
Bytes = bytes

_LAZY_TASKS = {"InMemoryBackend", "TaskBackend", "TaskState", "mount_task_routes"}


def __getattr__(name: str) -> Any:
    # ``importlib.import_module`` (not ``from tythe import ...``) so we don't
    # recurse into this very ``__getattr__`` looking up the submodule.
    if name in _LAZY_TASKS:
        import importlib

        return getattr(importlib.import_module("tythe.tasks"), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "App",
    "BidiChannel",
    "Bytes",
    "Context",
    "Depends",
    "Form",
    "InMemoryBackend",
    "SsePayload",
    "TaskBackend",
    "TaskState",
    "after",
    "bidi",
    "mount_task_routes",
    "raises",
    "stream",
]

__version__ = "0.1.1"
