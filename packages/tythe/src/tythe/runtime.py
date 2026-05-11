"""Per-route handler runners and the bits that turn ``Route``s into HTTP.

Flow per request:

1. Starlette matches the path → ``RouteRunner.handle(request)``.
2. The runner pulls each parameter from path/query/body/headers/cookies/multipart.
3. Each value is validated via ``msgspec.convert`` (or ``msgspec.json.decode`` for whole bodies).
4. ``Depends(...)`` providers are resolved (including teardown for generator providers).
5. The handler is called.
6. The return value is encoded — streaming → SSE, ``@raises`` → ``Result`` envelope,
   otherwise plain JSON.
"""

from __future__ import annotations

import contextlib
import inspect
import re
import typing
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Annotated, Any, cast, get_args, get_origin

import msgspec
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse

from tythe.context import Context, Dependency
from tythe.errors import exception_to_payload, get_declared_raises
from tythe.params import Body, Marker, ParamLocation, location_of
from tythe.streaming import encode_done, encode_frame, is_stream_annotation, stream_event_type

_MISSING: Any = object()
_PATH_PARAM_RE = re.compile(r"\{([^}:]+)(?::[^}]+)?\}")

TeardownFn = Callable[[], Awaitable[None]]


@dataclass(slots=True)
class ParamSpec:
    name: str
    alias: str
    location: ParamLocation | None  # None for Context / Depends
    py_type: Any
    required: bool
    default: Any
    embed: bool = False
    is_context: bool = False
    dependency: Dependency | None = None


@dataclass(slots=True)
class HandlerPlan:
    params: list[ParamSpec]
    return_annotation: Any
    streams: bool
    event_type: Any
    raises: tuple[type[Exception], ...]
    body_embed: bool
    file_params: list[ParamSpec]


def build_plan(handler: Callable[..., Any], path_template: str) -> HandlerPlan:
    sig = inspect.signature(handler)
    localns: dict[str, Any] | None = getattr(handler, "__tythe_localns__", None)
    hints = typing.get_type_hints(handler, localns=localns, include_extras=True)
    path_params = set(_PATH_PARAM_RE.findall(path_template))

    specs: list[ParamSpec] = []
    for param in sig.parameters.values():
        if param.name == "self":
            continue
        specs.append(_resolve_param(param, hints.get(param.name, param.annotation), path_params))

    body_specs = [s for s in specs if s.location == "body"]
    body_embed = len(body_specs) > 1 or any(s.embed for s in body_specs)
    if body_embed:
        for s in body_specs:
            s.embed = True

    return HandlerPlan(
        params=specs,
        return_annotation=hints.get("return", inspect.Signature.empty),
        streams=is_stream_annotation(hints.get("return")),
        event_type=stream_event_type(hints.get("return"))
        if is_stream_annotation(hints.get("return"))
        else None,
        raises=get_declared_raises(handler),
        body_embed=body_embed,
        file_params=[s for s in specs if s.location == "file"],
    )


def _resolve_param(param: inspect.Parameter, annotation: Any, path_params: set[str]) -> ParamSpec:
    has_default = param.default is not inspect.Parameter.empty
    default = param.default if has_default else _MISSING

    if annotation is Context:
        return ParamSpec(
            name=param.name,
            alias=param.name,
            location=None,
            py_type=Context,
            required=False,
            default=None,
            is_context=True,
        )
    if isinstance(param.default, Dependency):
        return ParamSpec(
            name=param.name,
            alias=param.name,
            location=None,
            py_type=annotation,
            required=False,
            default=None,
            dependency=param.default,
        )

    py_type = annotation
    marker: Marker | None = None
    if get_origin(annotation) is Annotated:
        args = get_args(annotation)
        py_type = args[0]
        for extra in args[1:]:
            if isinstance(extra, Marker):
                marker = extra
                break

    if marker is not None:
        location = location_of(marker)
        assert location is not None
        return ParamSpec(
            name=param.name,
            alias=marker.alias or param.name,
            location=location,
            py_type=py_type,
            required=not has_default,
            default=default,
            embed=isinstance(marker, Body) and marker.embed,
        )

    # No marker: infer from path template, then type shape, falling back to query.
    if param.name in path_params:
        location = "path"
    elif _is_structural(py_type):
        location = "body"
    else:
        location = "query"
    return ParamSpec(
        name=param.name,
        alias=param.name,
        location=location,
        py_type=py_type,
        required=not has_default,
        default=default,
    )


def _is_structural(t: Any) -> bool:
    """``True`` for Struct / dataclass / TypedDict — anything that's a whole-object shape."""
    return _is_struct_class(t) or _has_struct_attrs(t)


def _is_struct_class(t: Any) -> bool:
    try:
        return isinstance(t, type) and issubclass(t, msgspec.Struct)
    except TypeError:
        return False


def _has_struct_attrs(t: object) -> bool:
    # ``t: object`` blocks Pylance from inheriting any narrowing from the caller,
    # which otherwise turns the hasattr argument into ``type[Unknown] | type[Struct]``.
    return hasattr(t, "__dataclass_fields__") or hasattr(t, "__required_keys__")


class ValidationError(Exception):
    def __init__(self, message: str, *, location: ParamLocation | None = None) -> None:
        super().__init__(message)
        self.location = location


async def _read_value(
    spec: ParamSpec,
    request: Request,
    body_cache: dict[str, Any] | None,
    form_cache: Mapping[str, Any] | None,
) -> Any:
    if spec.is_context:
        return Context(request=request)
    if spec.location == "path":
        return _convert_primitive(request.path_params.get(spec.alias), spec)
    if spec.location == "query":
        raw = request.query_params.get(spec.alias)
        return _optional_or_convert(raw, spec)
    if spec.location == "header":
        raw = request.headers.get(spec.alias.lower())
        return _optional_or_convert(raw, spec)
    if spec.location == "cookie":
        raw = request.cookies.get(spec.alias)
        return _optional_or_convert(raw, spec)
    if spec.location == "body":
        assert body_cache is not None
        if spec.embed:
            if spec.alias not in body_cache:
                if not spec.required:
                    return spec.default
                raise _missing(spec)
            return msgspec.convert(body_cache[spec.alias], type=spec.py_type, strict=False)
        if not body_cache and not spec.required:
            return spec.default
        return msgspec.convert(body_cache, type=spec.py_type, strict=False)
    if spec.location == "file":
        assert form_cache is not None
        value = form_cache.get(spec.alias)
        if value is None:
            if not spec.required:
                return spec.default
            raise _missing(spec)
        return value
    raise AssertionError(f"unreachable location: {spec.location!r}")


def _optional_or_convert(raw: str | None, spec: ParamSpec) -> Any:
    if raw is None:
        if not spec.required:
            return spec.default
        raise _missing(spec)
    return _convert_primitive(raw, spec)


def _convert_primitive(raw: str | None, spec: ParamSpec) -> Any:
    if raw is None:
        raise _missing(spec)
    t = spec.py_type
    if t is str or t is Any or t is inspect.Signature.empty:
        return raw
    if t is bool:
        return raw.lower() in ("true", "1", "yes", "on")
    try:
        return msgspec.convert(raw, type=t, strict=False)
    except msgspec.ValidationError:
        return msgspec.json.decode(raw.encode(), type=t)


def _missing(spec: ParamSpec) -> ValidationError:
    return ValidationError(f"missing required parameter {spec.alias!r}", location=spec.location)


_json_encoder = msgspec.json.Encoder()


def _encode_json(value: Any) -> bytes:
    return _json_encoder.encode(value)


@dataclass(slots=True)
class RouteRunner:
    handler: Callable[..., Any]
    plan: HandlerPlan

    async def handle(self, request: Request) -> Response:
        teardown: list[TeardownFn] = []
        try:
            kwargs, teardown = await self._gather_kwargs(request)

            if self.plan.streams:
                return StreamingResponse(
                    self._stream(self.handler(**kwargs), teardown, request),
                    media_type="text/event-stream",
                    headers={"cache-control": "no-cache, no-transform", "x-accel-buffering": "no"},
                )

            result: Any = self.handler(**kwargs)
            if inspect.isawaitable(result):
                result = await result

            payload = (
                _encode_json({"ok": True, "data": result})
                if self.plan.raises
                else _encode_json(result)
            )
            await _run_teardown(teardown)
            return Response(content=payload, media_type="application/json")
        except ValidationError as exc:
            await _run_teardown(teardown)
            return JSONResponse({"detail": str(exc), "location": exc.location}, status_code=422)
        except Exception as exc:
            # Declared exceptions become Result envelopes whether they were
            # raised inside the handler body or inside a ``Depends(...)`` provider.
            if isinstance(exc, self.plan.raises):
                await _run_teardown(teardown)
                return Response(
                    content=_encode_json({"ok": False, "error": exception_to_payload(exc)}),
                    media_type="application/json",
                )
            await _run_teardown(teardown)
            raise

    async def _gather_kwargs(
        self,
        request: Request,
    ) -> tuple[dict[str, Any], list[TeardownFn]]:
        kwargs: dict[str, Any] = {}
        body_cache: dict[str, Any] | None = None
        form_cache: Mapping[str, Any] | None = None

        if any(p.location == "body" for p in self.plan.params):
            body_cache = await _read_json_body(request, embed=self.plan.body_embed)
        if self.plan.file_params:
            form_cache = await request.form()

        teardown: list[TeardownFn] = []
        resolver = _DepResolver(request)
        for spec in self.plan.params:
            value: Any
            if spec.dependency is not None:
                value, td = await resolver.resolve(spec.dependency)
                if td is not None:
                    teardown.append(td)
            else:
                value = await _read_value(spec, request, body_cache, form_cache)
            kwargs[spec.name] = value
        return kwargs, teardown

    async def _stream(
        self,
        iterator: Any,
        teardown: list[TeardownFn],
        request: Request,
    ) -> AsyncIterator[bytes]:
        try:
            async for item in iterator:
                if await request.is_disconnected():
                    break
                yield encode_frame(item)
            yield encode_done()
        except Exception as exc:
            if isinstance(exc, self.plan.raises):
                yield b"event: error\ndata: " + _encode_json(exception_to_payload(exc)) + b"\n\n"
            else:
                await _run_teardown(teardown)
                raise
        finally:
            await _run_teardown(teardown)


async def _read_json_body(request: Request, *, embed: bool) -> dict[str, Any]:
    raw = await request.body()
    if not raw:
        return {}
    decoded: Any = msgspec.json.decode(raw)
    if not isinstance(decoded, dict):
        if embed:
            raise ValidationError("expected JSON object when binding multiple body params")
        return {"__root__": decoded}
    out: dict[str, Any] = {}
    # cast is "redundant" for mypy but Pylance strict-mode treats the dict
    # contents as Unknown without it. Side with Pylance since that's the editor.
    for key, val in cast("dict[Any, Any]", decoded).items():  # type: ignore[redundant-cast]
        out[str(key)] = val
    return out


class _DepResolver:
    """Per-request DI resolver. Two ``Depends(same)`` params share one instance."""

    __slots__ = ("cache", "request")

    def __init__(self, request: Request) -> None:
        self.request: Request = request
        self.cache: dict[Callable[..., Any], Any] = {}

    async def resolve(self, dep: Dependency) -> tuple[Any, TeardownFn | None]:
        if dep.use_cache and dep.provider in self.cache:
            return self.cache[dep.provider], None

        sig = inspect.signature(dep.provider)
        hints = typing.get_type_hints(dep.provider, include_extras=True)
        kwargs: dict[str, Any] = {}
        teardowns: list[TeardownFn] = []
        for p in sig.parameters.values():
            ann = hints.get(p.name, p.annotation)
            if ann is Context:
                kwargs[p.name] = Context(request=self.request)
                continue
            if ann is Request:
                kwargs[p.name] = self.request
                continue
            if isinstance(p.default, Dependency):
                inner, td = await self.resolve(p.default)
                if td is not None:
                    teardowns.append(td)
                kwargs[p.name] = inner
                continue
            # Providers can pull from headers/query/cookies the same way handlers
            # do — without this, ``Annotated[str, Header()]`` on a provider would
            # silently fall back to the default value.
            spec = _resolve_param(p, ann, path_params=set())
            if spec.location in {"header", "query", "cookie"}:
                kwargs[p.name] = await _read_value(spec, self.request, None, None)

        raw: Any = dep.provider(**kwargs)
        value: Any
        if inspect.isasyncgen(raw):
            value = await raw.__anext__()
            teardowns.append(_async_gen_teardown(raw))
        elif inspect.isgenerator(raw):
            value = next(raw)
            teardowns.append(_sync_gen_teardown(raw))
        elif inspect.isawaitable(raw):
            value = await raw
        else:
            value = raw

        if dep.use_cache:
            self.cache[dep.provider] = value

        if not teardowns:
            return value, None
        return value, _combine_teardowns(teardowns)


def _async_gen_teardown(agen: AsyncIterator[Any]) -> TeardownFn:
    async def teardown() -> None:
        with contextlib.suppress(StopAsyncIteration):
            await agen.__anext__()

    return teardown


def _sync_gen_teardown(gen: Any) -> TeardownFn:
    async def teardown() -> None:
        with contextlib.suppress(StopIteration):
            next(gen)

    return teardown


def _combine_teardowns(items: list[TeardownFn]) -> TeardownFn:
    async def teardown() -> None:
        # Outermost-first reverse so nested deps tear down in stack order.
        for td in reversed(items):
            with contextlib.suppress(Exception):
                await td()

    return teardown


async def _run_teardown(teardowns: list[TeardownFn]) -> None:
    for td in reversed(teardowns):
        with contextlib.suppress(Exception):
            await td()
