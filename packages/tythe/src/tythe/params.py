"""Parameter location markers.

Use these inside ``Annotated[T, ...]`` to tell Tythe where a handler's
parameter lives on the wire:

    @app.post("/login")
    async def login(
        email: Annotated[str, Body()],
        password: Annotated[str, Body()],
        ua: Annotated[str, Header("user-agent")] = "",
    ) -> Session: ...

If no marker is given, Tythe infers: path-template names → ``Path``, structural
types (Struct/dataclass/TypedDict) → ``Body``, everything else → ``Query``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from starlette.datastructures import UploadFile

ParamLocation = Literal["path", "query", "body", "header", "cookie", "file"]

__all__ = [
    "Body",
    "Cookie",
    "File",
    "Header",
    "Marker",
    "ParamLocation",
    "Path",
    "Query",
    "UploadFile",
    "location_of",
]


@dataclass(slots=True, frozen=True)
class Marker:
    alias: str | None = None


@dataclass(slots=True, frozen=True)
class Body(Marker):
    embed: bool = False


@dataclass(slots=True, frozen=True)
class Query(Marker):
    pass


@dataclass(slots=True, frozen=True)
class Path(Marker):
    pass


@dataclass(slots=True, frozen=True)
class Header(Marker):
    pass


@dataclass(slots=True, frozen=True)
class Cookie(Marker):
    pass


@dataclass(slots=True, frozen=True)
class File(Marker):
    pass


_LOCATIONS: dict[type[Marker], ParamLocation] = {
    Body: "body",
    Query: "query",
    Path: "path",
    Header: "header",
    Cookie: "cookie",
    File: "file",
}


def location_of(marker: object) -> ParamLocation | None:
    return _LOCATIONS.get(type(marker)) if isinstance(marker, Marker) else None
