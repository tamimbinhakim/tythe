# Reference

Every primitive Dyadpy exports, what it does, and the smallest example. If a
feature isn't here, it isn't in `dyadpy`.

Dyadpy ships at the wire level: HTTP routes, body / param markers, typed
streaming, typed errors, post-response hooks. Nothing higher-level (no
auth, no rate-limiting, no LLM types).

- [App + decorators](#app--decorators)
- [Parameter markers (`Annotated[T, ...]`)](#parameter-markers)
- [Request body shapes (JSON, `Bytes`, `Form`, file)](#request-body-shapes)
- [Response control (`Context.set_status` / `set_header` / `set_cookie`)](#response-control)
- [Typed errors (`@raises`)](#typed-errors)
- [Streaming (`stream[T]`)](#streaming)
- [Dependency injection (`Depends`)](#dependency-injection)
- [Post-response hooks (`after()`)](#post-response-hooks)
- [Background jobs (`TaskBackend`)](#background-jobs)
- [Observability (`dyadpy.otel`)](#observability)
- [OpenAPI + polyglot codegen (CLI)](#openapi--polyglot-codegen)

---

## App + decorators

```python
from dyadpy import App

app = App()

@app.get("/users/{user_id}")
@app.post("/posts")
@app.put("/users/{user_id}")
@app.patch("/users/{user_id}")
@app.delete("/users/{user_id}")
async def handler(...): ...
```

Each decorator registers a route and infers parameter locations from
annotations + the path template.

## Parameter markers

Inside `Annotated[T, ...]`. Tell Dyadpy where a value lives on the wire.

```python
from typing import Annotated
from dyadpy.params import Body, Cookie, File, Form, Header, Path, Query, UploadFile

@app.post("/posts/{post_id}/comments")
async def add_comment(
    post_id: int,                                       # path (inferred from template)
    body: Annotated[str, Body()],                       # JSON body field
    cursor: Annotated[str | None, Query()] = None,      # ?cursor=...
    if_match: Annotated[str, Header("If-Match")] = "",  # request header
    session: Annotated[str, Cookie()] = "",             # request cookie
    avatar: Annotated[UploadFile, File()] = None,       # multipart upload
): ...
```

Without an explicit marker:

- path-template names (`{post_id}`) → `Path`
- structural types (msgspec.Struct / dataclass / TypedDict / Pydantic) → `Body`
- everything else → `Query`

### List-valued query params

```python
@app.get("/issues")
async def list_issues(
    tag: Annotated[list[str], Query()] = None,  # ?tag=bug&tag=ui  →  ["bug", "ui"]
    status: Annotated[list[Status], Query()] = None,
) -> Page: ...
```

Missing or `None` default → empty list. TS client expands array args back into
repeated `?tag=a&tag=b` keys.

## Request body shapes

### JSON (default)

```python
class CreatePost(msgspec.Struct):
    title: str
    body: str

@app.post("/posts")
async def create_post(data: CreatePost) -> Post: ...
```

Multi-field embedded:

```python
@app.post("/login")
async def login(
    email: Annotated[str, Body()],
    password: Annotated[str, Body()],
) -> Session: ...
```

### Raw bytes — `Bytes`

```python
from dyadpy import Bytes

@app.post("/webhooks/stripe")
async def stripe_webhook(
    body: Bytes,
    signature: Annotated[str, Header("stripe-signature")],
) -> None: ...

@app.get("/exports/{id}.csv")
async def export(id: str) -> Bytes:
    return render_csv(id)
```

Skips the JSON envelope on both sides. TS client passes
`Blob | Uint8Array | ArrayBuffer` through, decodes responses with `res.blob()`.
Content-Type defaults to `application/octet-stream` (override via `set_header`).

### Form — `Annotated[T, Form()]`

```python
import msgspec
from dyadpy import Form

class LoginForm(msgspec.Struct):
    email: str
    password: str
    remember_me: bool = False

@app.post("/login")
async def login(form: Annotated[LoginForm, Form()]) -> Session: ...
```

Reads `application/x-www-form-urlencoded` (or `multipart/form-data` when files
are present). The handler receives a `LoginForm` instance — pyright sees the
inner type directly. TS client sends `URLSearchParams`.

### Multipart files — `UploadFile` + `File()`

```python
from dyadpy.params import File, UploadFile

@app.post("/avatar")
async def upload(file: Annotated[UploadFile, File()]) -> dict[str, int]: ...
```

## Response control

`Context` is a per-request handle the runtime injects when you annotate a
parameter `ctx: Context`. Mutating these from inside the handler shapes the
final response.

```python
from dyadpy import Context

@app.post("/issues")
async def create_issue(data: CreateIssue, ctx: Context) -> Issue:
    issue = save(data)
    ctx.set_status(201)
    ctx.set_header("location", f"/issues/{issue.id}")
    ctx.set_cookie(
        "session", sign(user.id),
        max_age=86400, http_only=True, secure=True, same_site="strict",
    )
    return issue
```

| Method                                                                                       | What it does                                                                          |
| -------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| `ctx.set_status(code)`                                                                       | Override the default 200 (e.g. 201 Created, 202 Accepted).                            |
| `ctx.set_header(name, val)`                                                                  | Add or replace a response header (`Location`, `X-Request-Id`, …).                     |
| `ctx.set_cookie(name, val, *, max_age, expires, path, domain, secure, http_only, same_site)` | Queue a `Set-Cookie` header. Multiple calls = multiple cookies.                       |
| `ctx.after(fn, *a, **kw)`                                                                    | Run `fn` after the response is sent. See [Post-response hooks](#post-response-hooks). |
| `ctx.request`                                                                                | The raw Starlette `Request` if you need an escape hatch.                              |
| `ctx.headers`                                                                                | Read-only dict of request headers.                                                    |
| `ctx.cookies`                                                                                | Read-only dict of request cookies.                                                    |
| `await ctx.is_disconnected()`                                                                | Client-gone check (use it inside long-running streams).                               |

## Validation errors

When an inbound request fails parameter validation, Dyadpy returns **HTTP 422**
with a structured body:

```json
{
  "detail": "Expected `float`, got `str`",
  "location": "body",
  "field": "data.items[2].weight",
  "value": "not-a-number"
}
```

| Field      | Meaning                                                                              |
| ---------- | ------------------------------------------------------------------------------------ |
| `detail`   | Human-readable message from msgspec or Pydantic.                                     |
| `location` | Which input slot failed — `body` / `query` / `header` / `cookie` / `path` / `file`.  |
| `field`    | Dotted/bracketed path to the offending field (`alias.foo[2].bar`), or `null` if N/A. |
| `value`    | The offending raw value as received, or `null` if the field was missing entirely.    |

The TS client throws on 422 — wrap calls in `try/catch` and inspect the body if you
need to surface field-level errors in a form.

## Typed errors

Declare which exceptions a handler can raise. They become a discriminated union
on the TS side, with `result.ok` narrowing.

```python
from dataclasses import dataclass
from dyadpy import raises

@dataclass
class IssueNotFound(Exception):
    issue_id: int

@dataclass
class Forbidden(Exception):
    reason: str

@app.get("/issues/{issue_id}")
@raises(IssueNotFound, Forbidden)
async def get_issue(issue_id: int) -> Issue:
    issue = store.get(issue_id)
    if issue is None:
        raise IssueNotFound(issue_id=issue_id)
    return issue
```

TS side:

```ts
const r = await api.getIssue({ issueId: 1 });
if (r.ok) return r.data; // r.data: Issue
switch (
  r.error.kind // exhaustive
) {
  case "IssueNotFound":
    return `× ${r.error.issueId}`;
  case "Forbidden":
    return `× ${r.error.reason}`;
}
```

### Exceptions inside generic types

An Exception subclass nested inside a user-defined generic Struct (e.g. a
`BatchResult[T, E]` where `E` is a typed error) resolves to the same
tagged-Struct schema as a top-level `@raises(E)` would. The TS client can
still narrow on `error.kind`, just one level deeper:

```python
class BatchFailure(msgspec.Struct, Generic[T, E]):
    input: T
    error: E

class BatchResult(msgspec.Struct, Generic[T, E]):
    ok: list[T]
    failed: list[BatchFailure[T, E]]

@app.post("/users:bulk")
async def create_many(items: list[NewUser]) -> BatchResult[User, BadRequest]:
    ...
```

`BadRequest` shows up inline in the schema with a `kind: "BadRequest"`
discriminator — no separate `@raises` declaration needed for the
generic-parameter case.

## Streaming

```python
import asyncio
from dyadpy import stream

class Tick(msgspec.Struct, tag_field="kind", tag="tick"):
    seq: int

class Done(msgspec.Struct, tag_field="kind", tag="done"):
    total: int

@app.get("/ticks")
async def ticks(count: int) -> stream[Tick | Done]:
    for i in range(count):
        await asyncio.sleep(0.5)
        yield Tick(seq=i)
    yield Done(total=count)
```

Wire is SSE (`text/event-stream`). TS client returns an `AsyncIterable`:

```ts
for await (const ev of api.ticks({ count: 10 }, { signal: ac.signal })) {
  if (ev.kind === "tick") console.log(ev.seq);
}
```

Streams + `@raises(...)`: declared errors surface as SSE `event: error`
frames that throw on the client side.

### Resumption with `SsePayload` / `Last-Event-Id`

Wrap events in `SsePayload(data, id=..., retry_ms=...)` to attach an
SSE `id:` and an optional `retry:` hint. The TS client tracks the last
seen id and reconnects with `Last-Event-Id` if the connection drops:

```python
from dyadpy import SsePayload, Context, stream
from dyadpy.params import Header
from typing import Annotated

@app.get("/events")
async def events(
    last_event_id: Annotated[str | None, Header("Last-Event-Id")] = None,
) -> stream[Event]:
    cursor = parse_cursor(last_event_id) if last_event_id else 0
    async for ev in store.since(cursor):
        yield SsePayload(data=ev, id=str(ev.seq), retry_ms=3000)
```

The client side is fully automatic — `for await (const ev of api.events())`
reconnects with the right header on any transport error, capped at 5
minutes of cumulative retry. Typed `@raises` errors and explicit user
cancellation (`AbortSignal`) still propagate immediately.

## Dependency injection

```python
from dyadpy import Depends

def current_user(authorization: Annotated[str, Header()] = "") -> User:
    if not authorization.startswith("Bearer "):
        raise Forbidden(reason="missing token")
    return decode(authorization[7:])

@app.get("/me")
async def me(me: User = Depends(current_user)) -> User:
    return me
```

Providers can be plain functions, async functions, sync generators yielding
once, or async generators yielding once. The post-`yield` body runs as
teardown after the response is finalized. Same shape as FastAPI.

## Post-response hooks

```python
from dyadpy import after

@app.post("/posts")
async def create_post(data: CreatePost) -> Post:
    post = save(data)
    after(notify_webhook, post.id)
    after(log_audit, "post.created", user_id=post.author_id)
    return post
```

Runs sync and async callables after the response is sent. Errors are
swallowed (response is already gone). Looked up via a contextvar — works
without threading `ctx` through. Outside a handler it raises.

Also available as `ctx.after(fn, …)` if you have `Context` in scope.

## Background jobs

In-memory queue ships in core. Redis / SQS adapters live in their own
packages.

```python
from dyadpy import InMemoryBackend, TaskBackend, TaskState

backend: TaskBackend = InMemoryBackend()

async def heavy_work(arg: int) -> str:
    await asyncio.sleep(10)
    return f"done({arg})"

@app.post("/work")
async def submit() -> dict[str, str]:
    task_id = await backend.enqueue(heavy_work, 42)
    return {"task_id": task_id}

@app.get("/work/{task_id}")
async def status(task_id: str) -> TaskState[str]:
    return await backend.status(task_id)
```

`InMemoryBackend.stream(task_id)` yields `TaskState` snapshots through the
queued → running → succeeded/failed/cancelled lifecycle.

### One-call submit + status + stream

`mount_task_routes` registers the submit / status / stream triple from a
single handler, so you don't hand-write the three routes:

```python
from dyadpy import App, InMemoryBackend, mount_task_routes

app = App()
backend = InMemoryBackend()

async def transcribe(payload: TranscribeInput) -> Transcript:
    return await run_model(payload.audio_url)

mount_task_routes(app, "/transcribe", transcribe, backend=backend)
```

This wires:

- `POST /transcribe` — body matches `transcribe`'s own param shape;
  returns `{"task_id": "..."}`.
- `GET /transcribe/{task_id}` — returns `TaskState[Transcript]`.
- `GET /transcribe/{task_id}/events` — SSE stream of `TaskState[Transcript]`
  until the task reaches a terminal status (`succeeded` / `failed` /
  `cancelled`).

The handler's return type flows into `TaskState[T]` automatically. Unknown
task ids surface as a structured 422 on either polling route — the same
shape produced by request validation errors.

## Observability

```python
from dyadpy import App
from dyadpy.otel import instrument

app = instrument(App())
```

Adds one OpenTelemetry span per request with method, path, and status code.
No-op if `opentelemetry-api` isn't installed (it's an optional extra:
`dyadpy[otel]`).

## OpenAPI + polyglot codegen

CLI commands that read the same IR the TS codegen uses:

```bash
dyadpy openapi server.app:app --out openapi.json
dyadpy swift server.app:app --out Dyadpy.swift
dyadpy kotlin server.app:app --out Dyadpy.kt --package com.example.api
```

- **`dyadpy openapi`** — OpenAPI 3.1 doc for external clients (consumers
  who can't use Dyadpy's TS client).
- **`dyadpy swift`** — typed Swift client using URLSession + JSONEncoder
  with `convertToSnakeCase`.
- **`dyadpy kotlin`** — typed Kotlin client using HttpURLConnection +
  `kotlinx.serialization` (no ktor/OkHttp dep).

Streaming endpoints surface as `URLRequest` (Swift) / raw `String` (Kotlin) —
caller wires SSE through their platform's preferred parser.

## What's NOT here

By design. See [`docs/design.md`](./design.md) for the reasoning.

- No `dyadpy.ai` / LLM-shaped types — LLM tokens are just typed events on
  an SSE stream; use the existing `stream[T]` primitive.
- No auth implementation — wire `Depends(current_user)` to your provider
  (Clerk / Auth0 / custom JWT). See [`docs/auth.md`](./auth.md).
- No rate limiting, caching headers, ETag — single-header concerns that
  middleware or `set_header` cover.
- No WebSocket bidi (yet) — SSE is the default, opt-in only.
- No GraphQL.
