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
from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse

from tythe._pydantic import is_pydantic_model, to_jsonable
from tythe._pydantic import validate as pydantic_validate
from tythe.context import Context, Dependency, current_context_var, run_after_callbacks
from tythe.errors import exception_to_payload, get_declared_raises
from tythe.params import Body, Form, Marker, ParamLocation, location_of
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
    is_form: bool = False  # body is form-encoded, py_type is the inner struct
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
    # Fast-path body decoder: set only when the route has exactly one body
    # param of a msgspec-native type (Struct / dataclass / TypedDict / scalar).
    # Lets us go raw bytes → typed value in one C call instead of bytes →
    # untyped dict → msgspec.convert.
    body_decoder: Any = None  # msgspec.json.Decoder[Any] | None
    body_spec: ParamSpec | None = None  # the single body param when body_decoder is set
    # Skip the pydantic detection branch on the response encoder when no
    # pydantic models appear in the route's type graph.
    pydantic_in_use: bool = False


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

    return_annotation = hints.get("return", inspect.Signature.empty)

    # Decide *whether* the fast-path body decoder is applicable but defer the
    # ``msgspec.json.Decoder(py_type)`` construction itself — that call does
    # meaningful upfront work (codegen), so we lazily build it on the route's
    # first hit. ``app._build()`` iterates every route, so eager construction
    # would charge cold-start for routes that may never be called.
    fast_body_spec: ParamSpec | None = None
    if (
        len(body_specs) == 1
        and not body_embed
        and body_specs[0].py_type is not bytes
        and not body_specs[0].is_form
        and not is_pydantic_model(body_specs[0].py_type)
    ):
        fast_body_spec = body_specs[0]

    pydantic_in_use = _route_uses_pydantic(specs, return_annotation)

    return HandlerPlan(
        params=specs,
        return_annotation=return_annotation,
        streams=is_stream_annotation(return_annotation),
        event_type=stream_event_type(return_annotation)
        if is_stream_annotation(return_annotation)
        else None,
        raises=get_declared_raises(handler),
        body_embed=body_embed,
        file_params=[s for s in specs if s.location == "file"],
        body_decoder=None,
        body_spec=fast_body_spec,
        pydantic_in_use=pydantic_in_use,
    )


def _route_uses_pydantic(specs: list[ParamSpec], return_annotation: Any) -> bool:
    """``True`` iff any param or the return type touches a Pydantic model.

    Used to skip the pydantic-detection branch in the response encoder hot
    path for the (overwhelmingly common) msgspec-only routes.
    """
    if is_pydantic_model(return_annotation):
        return True
    # Stream return types: peel ``stream[T]`` to inspect T.
    if is_stream_annotation(return_annotation):
        inner = stream_event_type(return_annotation)
        if is_pydantic_model(inner):
            return True
    return any(is_pydantic_model(s.py_type) for s in specs)


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
            is_form=isinstance(marker, Form),
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
    """``True`` for Struct / dataclass / TypedDict / Pydantic BaseModel / ``bytes``."""
    return t is bytes or _is_struct_class(t) or _has_struct_attrs(t) or is_pydantic_model(t)


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
    """Raised when an inbound request fails validation.

    The 422 response body shape is::

        {
          "detail": "human-readable message",
          "location": "body" | "query" | ...,
          "field": "data.items[2].name" | None,
          "value": <offending raw value, or None if missing entirely>
        }
    """

    def __init__(
        self,
        message: str,
        *,
        location: ParamLocation | None = None,
        field: str | None = None,
        value: Any = None,
    ) -> None:
        super().__init__(message)
        self.location = location
        self.field = field
        self.value = value


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
        # List-valued query params: `?tag=a&tag=b` → ["a", "b"]. Tells from
        # the annotation: ``list[T]`` (or generic-alias forms thereof).
        if _is_list_type(spec.py_type):
            raws = request.query_params.getlist(spec.alias)
            if not raws:
                if not spec.required:
                    # ``= None`` and ``= []`` both mean "empty list when absent"
                    # — the more useful default for list-typed query params.
                    if spec.default is _MISSING or spec.default is None:
                        return []
                    return spec.default
                raise _missing(spec)
            inner = _list_item_type(spec.py_type)
            return [_convert_query_value(r, inner) for r in raws]
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
            return _convert_body(body_cache[spec.alias], spec.py_type, alias=spec.alias)
        if not body_cache and not spec.required:
            return spec.default
        return _convert_body(body_cache, spec.py_type, alias=spec.alias)
    if spec.location == "file":
        assert form_cache is not None
        value = form_cache.get(spec.alias)
        if value is None:
            if not spec.required:
                return spec.default
            raise _missing(spec)
        return value
    raise AssertionError(f"unreachable location: {spec.location!r}")


def _convert_body(value: Any, py_type: Any, *, alias: str | None = None) -> Any:
    """Pydantic BaseModel → ``model_validate``; everything else → msgspec.convert.

    On failure raises ``ValidationError`` with a field path scoped under
    ``alias`` (e.g. ``data.items[2].name``) and the offending raw value.
    """
    if py_type is bytes:
        return value
    try:
        if is_pydantic_model(py_type):
            return pydantic_validate(py_type, value)
        return msgspec.convert(value, type=py_type, strict=False)
    except msgspec.ValidationError as exc:
        field, offending = _msgspec_field_and_value(value, str(exc), alias)
        raise ValidationError(str(exc), location="body", field=field, value=offending) from exc
    except Exception as exc:
        # Pydantic ValidationError lives outside our import chain; duck-type.
        first = _pydantic_first_error(exc)
        if first is not None:
            loc = cast("tuple[Any, ...]", first.get("loc", ()))
            raise ValidationError(
                str(first.get("msg", exc)),
                location="body",
                field=_join_pydantic_path(loc, alias),
                value=first.get("input"),
            ) from exc
        raise


def _pydantic_first_error(exc: Exception) -> dict[str, Any] | None:
    errs = getattr(exc, "errors", None)
    if not callable(errs):
        return None
    try:
        errors: Any = errs()
    except Exception:
        return None
    for item in errors:
        return cast("dict[str, Any]", item)
    return None


def _msgspec_field_and_value(
    payload: Any,
    msg: str,
    alias: str | None,
) -> tuple[str | None, Any]:
    """Pull the offending field path + value out of a msgspec error message.

    msgspec has two error shapes:
    - ``Expected float, got str - at `$.items[1].weight``` (type mismatch)
    - ``Object missing required field `label``` (missing top-level field)

    Best-effort parse — if we can't recover a path, fall back to the alias scope.
    """
    import re

    # Type-mismatch / nested-path shape carries `at $.foo.bar`.
    path_match = re.search(r"at `\$\.?([^`]*)`", msg)
    field_path = path_match.group(1) if path_match else ""

    # Missing-required-field shape: `Object missing required field \`X\``.
    if not field_path:
        miss = re.search(r"missing required field `([^`]+)`", msg)
        if miss:
            field_path = miss.group(1)

    field = _scope(alias, field_path) if field_path else alias
    offending = _walk_path(payload, field_path)
    return field, offending


def _walk_path(value: Any, path: str) -> Any:
    """Walk ``foo.bar[2].baz`` style paths into a nested dict/list payload."""
    if not path:
        return value
    import re

    cursor: Any = value
    for token in re.findall(r"[^.\[\]]+|\[\d+\]", path):
        if token.startswith("[") and token.endswith("]"):
            idx = int(token[1:-1])
            if isinstance(cursor, list):
                items = cast("list[Any]", cursor)  # type: ignore[redundant-cast]
                if 0 <= idx < len(items):
                    cursor = items[idx]
                    continue
            return None
        if isinstance(cursor, dict):
            cursor = cast("dict[str, Any]", cursor).get(token)
            continue
        return None
    return cursor


def _scope(alias: str | None, sub: str) -> str:
    if not alias:
        return sub
    return f"{alias}.{sub}" if sub else alias


def _join_pydantic_path(loc: tuple[Any, ...], alias: str | None) -> str:
    """Convert Pydantic's ``loc`` tuple into a dotted/bracketed field path."""
    parts: list[str] = []
    for piece in loc:
        if isinstance(piece, int):
            parts.append(f"[{piece}]")
        elif parts:
            parts.append(f".{piece}")
        else:
            parts.append(str(piece))
    inner = "".join(parts)
    return _scope(alias, inner)


def _optional_or_convert(raw: str | None, spec: ParamSpec) -> Any:
    if raw is None:
        if not spec.required:
            return spec.default
        raise _missing(spec)
    return _convert_primitive(raw, spec)


def _convert_primitive(raw: str | None, spec: ParamSpec) -> Any:
    if raw is None:
        raise _missing(spec)
    return _convert_query_value(raw, spec.py_type)


def _convert_query_value(raw: str, t: Any) -> Any:
    """Convert a single query/path/header/cookie string into ``t``."""
    if t is str or t is Any or t is inspect.Signature.empty:
        return raw
    if t is bool:
        return raw.lower() in ("true", "1", "yes", "on")
    try:
        return msgspec.convert(raw, type=t, strict=False)
    except msgspec.ValidationError:
        return msgspec.json.decode(raw.encode(), type=t)


def _is_list_type(t: Any) -> bool:
    origin = get_origin(t)
    return origin is list or t is list


def _list_item_type(t: Any) -> Any:
    args = get_args(t)
    return args[0] if args else Any


def _missing(spec: ParamSpec) -> ValidationError:
    return ValidationError(
        f"missing required parameter {spec.alias!r}",
        location=spec.location,
        field=spec.alias,
        value=None,
    )


_json_encoder = msgspec.json.Encoder()


def _encode_json(value: Any) -> bytes:
    # Pydantic BaseModel instances need ``model_dump`` before msgspec sees them;
    # everything else (Struct, dataclass, scalar, dict, list) passes straight through.
    return _json_encoder.encode(to_jsonable(value))


def _encode_json_fast(value: Any) -> bytes:
    """Encoder hot-path for routes whose type graph touches no Pydantic models.

    Skips the per-call ``to_jsonable`` dispatch — pure msgspec encode.
    """
    return _json_encoder.encode(value)


def _ctx_background(ctx: Context | None) -> BackgroundTask | None:
    """Bundle a Context's after-callbacks into a Starlette BackgroundTask."""
    if ctx is None or not ctx.after_callbacks:
        return None
    callbacks = list(ctx.after_callbacks)
    return BackgroundTask(run_after_callbacks, callbacks)


def _apply_ctx_headers(ctx: Context | None, headers: dict[str, str]) -> dict[str, str]:
    if ctx is None:
        return headers
    merged: dict[str, str] = {**headers, **ctx.response_headers}
    return merged


def _ctx_status(ctx: Context | None, default: int) -> int:
    return default if ctx is None or ctx.response_status is None else ctx.response_status


def _apply_ctx_cookies(ctx: Context | None, response: Response) -> None:
    """Emit a Set-Cookie header per queued cookie. Starlette's ``set_cookie``
    handles the format (Max-Age/Expires/SameSite/Secure/HttpOnly)."""
    if ctx is None:
        return
    for c in ctx.response_cookies:
        response.set_cookie(
            key=c.name,
            value=c.value,
            max_age=c.max_age,
            expires=c.expires,
            path=c.path,
            domain=c.domain,
            secure=c.secure,
            httponly=c.http_only,
            samesite=c.same_site,
        )


def _build_response(result: Any, plan: HandlerPlan, ctx: Context | None) -> Response:
    headers = _apply_ctx_headers(ctx, {})
    background = _ctx_background(ctx)
    status = _ctx_status(ctx, 200)

    # Raw bytes response — skip the JSON envelope, send octet-stream by default.
    if plan.return_annotation is bytes and isinstance(result, (bytes, bytearray)):
        media = headers.pop("content-type", None) or "application/octet-stream"
        resp = Response(
            content=bytes(result),
            media_type=media,
            headers=headers,
            background=background,
            status_code=status,
        )
        _apply_ctx_cookies(ctx, resp)
        return resp

    encode = _encode_json if plan.pydantic_in_use else _encode_json_fast
    payload = encode({"ok": True, "data": result}) if plan.raises else encode(result)
    resp = Response(
        content=payload,
        media_type="application/json",
        headers=headers,
        background=background,
        status_code=status,
    )
    _apply_ctx_cookies(ctx, resp)
    return resp


def _build_error_response(exc: Exception, ctx: Context | None) -> Response:
    headers = _apply_ctx_headers(ctx, {})
    background = _ctx_background(ctx)
    resp = Response(
        content=_encode_json({"ok": False, "error": exception_to_payload(exc)}),
        media_type="application/json",
        headers=headers,
        background=background,
        status_code=_ctx_status(ctx, 200),
    )
    _apply_ctx_cookies(ctx, resp)
    return resp


@dataclass(slots=True)
class RouteRunner:
    handler: Callable[..., Any]
    plan: HandlerPlan

    async def handle(self, request: Request) -> Response:
        teardown: list[TeardownFn] = []
        ctx_token = None
        ctx_for_response: Context | None = None
        try:
            kwargs, teardown, ctx_for_response = await self._gather_kwargs(request)
            # Free-function ``after()`` calls look up the current Context via
            # this contextvar. If the handler didn't request a Context param,
            # we synthesize one so ``after()`` still works.
            if ctx_for_response is None:
                ctx_for_response = Context(request=request)
            ctx_token = current_context_var.set(ctx_for_response)

            if self.plan.streams:
                return StreamingResponse(
                    self._stream(self.handler(**kwargs), teardown, request),
                    media_type="text/event-stream",
                    headers={"cache-control": "no-cache, no-transform", "x-accel-buffering": "no"},
                )

            result: Any = self.handler(**kwargs)
            if inspect.isawaitable(result):
                result = await result

            await _run_teardown(teardown)
            return _build_response(result, self.plan, ctx_for_response)
        except ValidationError as exc:
            await _run_teardown(teardown)
            body: dict[str, Any] = {
                "detail": str(exc),
                "location": exc.location,
            }
            if exc.field is not None:
                body["field"] = exc.field
            if exc.value is not None or "value" in exc.__dict__:
                body["value"] = exc.value
            return JSONResponse(body, status_code=422)
        except Exception as exc:
            # Declared exceptions become Result envelopes whether they were
            # raised inside the handler body or inside a ``Depends(...)`` provider.
            if isinstance(exc, self.plan.raises):
                await _run_teardown(teardown)
                return _build_error_response(exc, ctx_for_response)
            await _run_teardown(teardown)
            raise
        finally:
            if ctx_token is not None:
                current_context_var.reset(ctx_token)

    async def _gather_kwargs(
        self,
        request: Request,
    ) -> tuple[dict[str, Any], list[TeardownFn], Context | None]:
        kwargs: dict[str, Any] = {}
        body_cache: dict[str, Any] | bytes | None = None
        form_cache: Mapping[str, Any] | None = None
        ctx_value: Context | None = None

        body_specs = [p for p in self.plan.params if p.location == "body"]
        raw_body_spec = next((s for s in body_specs if s.py_type is bytes), None)
        form_body_spec = next((s for s in body_specs if s.is_form), None)
        # Fast path: single msgspec-friendly body param → decode bytes directly
        # into the typed value via a cached ``msgspec.json.Decoder`` and bind to
        # the handler param without going through an intermediate dict. The
        # decoder is built on first hit (not in ``build_plan``) so cold-start
        # only pays for routes the user actually exercises.
        fast_body_value: Any = _MISSING
        body_spec = self.plan.body_spec
        if body_spec is not None and raw_body_spec is None and form_body_spec is None:
            decoder = self.plan.body_decoder
            if decoder is None:
                try:
                    decoder = msgspec.json.Decoder(body_spec.py_type)
                    self.plan.body_decoder = decoder
                except (TypeError, msgspec.ValidationError):
                    # Annotation msgspec can't compile a typed decoder for —
                    # disable the fast path for this route permanently and
                    # drop through to the generic JSON-dict decode.
                    self.plan.body_spec = None
                    body_spec = None
            if body_spec is not None and decoder is not None:
                raw = await request.body()
                if raw:
                    try:
                        fast_body_value = decoder.decode(raw)
                    except msgspec.ValidationError as exc:
                        field, offending = _msgspec_field_and_value(None, str(exc), body_spec.alias)
                        raise ValidationError(
                            str(exc),
                            location="body",
                            field=field,
                            value=offending,
                        ) from exc
                elif not body_spec.required:
                    fast_body_value = body_spec.default
                else:
                    raise _missing(body_spec)
        if fast_body_value is _MISSING and body_cache is None:
            if raw_body_spec is not None:
                body_cache = await request.body()
            elif form_body_spec is not None:
                # urlencoded + multipart both come through request.form().
                form_cache = await request.form()
                body_cache = {k: form_cache[k] for k in form_cache}
            elif body_specs:
                body_cache = await _read_json_body(request, embed=self.plan.body_embed)
        if self.plan.file_params and form_cache is None:
            form_cache = await request.form()

        teardown: list[TeardownFn] = []
        resolver = _DepResolver(request)
        fast_spec_name = self.plan.body_spec.name if self.plan.body_spec is not None else None
        for spec in self.plan.params:
            value: Any
            if (
                fast_spec_name is not None
                and spec.name == fast_spec_name
                and fast_body_value is not _MISSING
            ):
                value = fast_body_value
            elif spec.dependency is not None:
                value, td = await resolver.resolve(spec.dependency)
                if td is not None:
                    teardown.append(td)
            elif spec.is_context:
                ctx_value = Context(request=request)
                value = ctx_value
            elif spec.location == "body" and spec.py_type is bytes:
                value = body_cache  # raw bytes
            else:
                value = await _read_value(
                    spec,
                    request,
                    body_cache if isinstance(body_cache, dict) else None,
                    form_cache,
                )
            kwargs[spec.name] = value
        return kwargs, teardown, ctx_value

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
