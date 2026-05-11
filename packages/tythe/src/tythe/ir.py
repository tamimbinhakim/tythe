"""IR builder.

Every registered handler reduces to a JSON-Schema-2020-12 IR that the
codegen walks to emit TypeScript. The two-step (IR → renderer) split is
what lets polyglot clients (Swift, Kotlin) follow later without rewriting
type extraction.

Two passes:

1. Per-route: reuse the runtime's ``build_plan`` so the IR sees the same
   parameter resolution the request path does — no drift between what
   the wire accepts and what the client generates for.
2. Global schema bake: collect every type and call
   ``msgspec.json.schema_components`` once. Shared types get one ``$defs``
   entry, not one per route.
"""

from __future__ import annotations

import inspect
import typing
from dataclasses import dataclass, fields
from typing import Any

import msgspec

from tythe.app import App, Route
from tythe.params import ParamLocation
from tythe.runtime import HandlerPlan, build_plan

_REF_TEMPLATE = "#/$defs/{name}"


@dataclass(slots=True)
class ParamIR:
    name: str
    alias: str
    schema: dict[str, Any]
    location: ParamLocation
    required: bool
    embed: bool = False


@dataclass(slots=True)
class ErrorIR:
    name: str
    schema: dict[str, Any]


@dataclass(slots=True)
class RouteIR:
    method: str
    path: str
    name: str
    params: list[ParamIR]
    response: dict[str, Any] | None
    streams: bool
    event_schema: dict[str, Any] | None
    raises: list[ErrorIR]


@dataclass(slots=True)
class AppIR:
    routes: list[RouteIR]
    components: dict[str, dict[str, Any]]


# Sentinel for "this slot doesn't need a schema" (File params, None returns).
# Keeps the type-list positions stable so we can stitch results back by index.
class _Skip:
    pass


def build_ir(app: App) -> AppIR:
    plans: list[tuple[Route, HandlerPlan]] = []
    for route in app.routes:
        plan = route.plan or build_plan(route.handler, route.path)
        route.plan = plan
        plans.append((route, plan))

    types_for_extraction: list[Any] = []
    slots: list[tuple[str, int, Any]] = []  # (kind, route_idx, payload)

    for r_idx, (_route, plan) in enumerate(plans):
        for p in plan.params:
            if p.location is None:  # Context / Depends — not on the wire
                continue
            slots.append(("param", r_idx, p))
            if p.location == "file":
                types_for_extraction.append(_Skip)
            else:
                types_for_extraction.append(
                    p.py_type if p.py_type is not inspect.Signature.empty else Any,
                )

        ret = plan.return_annotation
        slots.append(("response", r_idx, None))
        if plan.streams and plan.event_type is not None:
            types_for_extraction.append(plan.event_type)
        elif ret is None or ret is type(None) or ret is inspect.Signature.empty:
            types_for_extraction.append(_Skip)
        else:
            types_for_extraction.append(ret)

        for exc in plan.raises:
            slots.append(("raises", r_idx, exc))
            types_for_extraction.append(_synth_exc_type(exc))

    # msgspec.json.schema_components chokes on _Skip / non-schema-able types;
    # feed it a filtered list and stitch results back by position.
    real_indices: list[int] = []
    real_types: list[Any] = []
    for i, t in enumerate(types_for_extraction):
        if t is _Skip:
            continue
        real_indices.append(i)
        real_types.append(t)

    schemas: list[dict[str, Any]] = []
    components: dict[str, dict[str, Any]] = {}
    if real_types:
        real_schemas, real_components = msgspec.json.schema_components(
            real_types,
            ref_template=_REF_TEMPLATE,
        )
        schemas = list(real_schemas)
        components = dict(real_components)

    schemas_by_index: dict[int, dict[str, Any]] = {}
    for i, s in zip(real_indices, schemas, strict=True):
        schemas_by_index[i] = s

    routes_ir: list[RouteIR] = []
    for r_idx, (route, plan) in enumerate(plans):
        params_ir: list[ParamIR] = []
        response_schema: dict[str, Any] | None = None
        event_schema: dict[str, Any] | None = None
        raises_ir: list[ErrorIR] = []

        for slot_idx, (kind, slot_r_idx, payload) in enumerate(slots):
            if slot_r_idx != r_idx:
                continue
            schema: dict[str, Any] | None = schemas_by_index.get(slot_idx)
            if kind == "param":
                p = payload
                assert p.location is not None
                params_ir.append(
                    ParamIR(
                        name=p.name,
                        alias=p.alias,
                        schema=schema if schema is not None else _file_schema(),
                        location=p.location,
                        required=p.required,
                        embed=p.embed,
                    ),
                )
            elif kind == "response":
                if plan.streams:
                    event_schema = schema
                else:
                    response_schema = schema
            elif kind == "raises":
                raises_ir.append(
                    ErrorIR(name=payload.__name__, schema=schema or _exc_schema(payload)),
                )

        routes_ir.append(
            RouteIR(
                method=route.method,
                path=route.path,
                name=route.name or route.handler.__name__,
                params=params_ir,
                response=response_schema,
                streams=plan.streams,
                event_schema=event_schema,
                raises=raises_ir,
            ),
        )

    return AppIR(routes=routes_ir, components=components)


def _file_schema() -> dict[str, Any]:
    return {"type": "string", "format": "binary"}


def _synth_exc_type(exc: type[Exception]) -> Any:
    """Coerce an exception class into a tagged msgspec Struct.

    Even for dataclass-style exceptions, we build a tagged Struct rather than
    passing the dataclass through directly — the ``kind`` discriminator is what
    lets the TS side narrow ``result.error.kind === "PostNotFound"``, and the
    raw dataclass schema doesn't carry it.
    """
    return _build_exc_struct(exc)


_EXC_STRUCT_CACHE: dict[type[Exception], type[msgspec.Struct]] = {}


def _build_exc_struct(exc: type[Exception]) -> type[msgspec.Struct]:
    cached = _EXC_STRUCT_CACHE.get(exc)
    if cached is not None:
        return cached

    try:
        hints = typing.get_type_hints(exc, include_extras=False)
    except Exception:
        hints = {}
    hints.pop("return", None)

    field_defs: list[tuple[str, Any]] = list(hints.items())
    struct_type: type[msgspec.Struct] = msgspec.defstruct(
        exc.__name__,
        field_defs,
        tag=exc.__name__,
        tag_field="kind",
    )
    _EXC_STRUCT_CACHE[exc] = struct_type
    return struct_type


def _exc_schema(exc: type[Exception]) -> dict[str, Any]:
    """Last-resort schema for an exception that msgspec wouldn't accept."""
    props: dict[str, dict[str, Any]] = {"kind": {"const": exc.__name__, "type": "string"}}
    if hasattr(exc, "__dataclass_fields__"):
        for f in fields(exc):  # type: ignore[arg-type]
            props[f.name] = {"type": "string"}
    return {"type": "object", "title": exc.__name__, "properties": props, "required": ["kind"]}
