"""Tythe — a type-safe RPC bridge between Python and TypeScript.

The function signature is the contract. See
https://github.com/tamimbinhakim/tythe for full docs.
"""

from __future__ import annotations

from tythe.app import App
from tythe.context import Context, Depends, after
from tythe.errors import raises
from tythe.streaming import stream
from tythe.tasks import InMemoryBackend, TaskBackend, TaskState

# Raw-body sentinel: annotate a handler param or return with ``Bytes`` to
# skip the JSON envelope entirely. Identical to the ``bytes`` builtin; the
# alias is exported for documentation and explicit-intent reasons.
Bytes = bytes

__all__ = [
    "App",
    "Bytes",
    "Context",
    "Depends",
    "InMemoryBackend",
    "TaskBackend",
    "TaskState",
    "after",
    "raises",
    "stream",
]

__version__ = "0.1.0"
