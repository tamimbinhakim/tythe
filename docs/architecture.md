# Architecture

This is what's actually happening when you type `tythe dev`. It's not magic,
and the parts are small enough that you can read the whole thing in a
weekend.

## The 30-second mental model

```
your Python handlers
        │
        ▼
   IR Builder           (inspect + typing.get_type_hints + msgspec schema)
        │
        ▼
    AppIR  ──►  ASGI runtime  ──►  HTTP / SSE
        │
        ▼
    Codegen        (IR → single client.ts)
        │
        ▼
your frontend's src/lib/tythe/client.ts
        │
        ▼
    @tythe/ts    (~3 KB runtime, Proxy dispatch + SSE)
```

Two flows: **server start** rebuilds the IR and writes `client.ts`; **at
request time** the ASGI runtime decodes via msgspec, calls your handler,
encodes the response.

## Layer by layer

### 1. `App` and route registration (`tythe/app.py`)

The `App` is a plain dataclass with a list of `Route` records. Decorators
(`@app.get`, `@app.post`, …) just append to the list. There are no globals,
no metaclasses, no import-time side effects.

```python
app = App()

@app.get("/users/{user_id}")
async def get_user(user_id: int) -> User: ...
```

Why this matters: tests can build an `App`, populate it, introspect it, and
throw it away — all without booting a server.

### 2. IR extraction (`tythe/ir.py`)

At server start (and on every reload) the IR builder walks each `Route`:

1. `inspect.signature(handler)` → parameter names, defaults, kinds.
2. `typing.get_type_hints(handler, include_extras=True)` → resolved
   annotations, including `Annotated[T, Body()|Query()|Path()|Header()]`.
3. `msgspec.json.schema_components([...])` → JSON Schema 2020-12 fragments
   that share `$ref`-style components for repeated types.
4. Return-type analysis: `AsyncIterator[T]` (or the friendlier
   `stream[T]`) → a streaming endpoint; `Task[T]` → long-running.
5. `tythe.errors.get_declared_raises(handler)` → the typed-error union.

The output is a plain dataclass tree (`AppIR`) — serializable to JSON,
inspectable in the REPL, easy to snapshot in tests.

### 3. ASGI transport (`tythe/app.py` + Starlette under the hood)

The runtime is Starlette underneath. We don't reinvent routing, ASGI
lifespan, or middleware — that ecosystem is solid.

For each request:

1. Match path → `Route` → `RouteIR`.
2. Decode body with `msgspec.json.decode` against the route's input schema.
   No allocator-heavy model wrapping — msgspec gives us a `Struct` directly.
3. Resolve `Depends(...)` if present.
4. Call the handler.
5. Encode the return value with `msgspec.json.encode`. For streaming
   handlers, wrap in `EventSourceResponse` and yield tagged frames.

For typed errors: if the handler raises one of the exceptions declared in
`@raises(...)`, the runtime wraps it in the `Result` envelope. Anything else
becomes a 500 and is logged.

### 4. Codegen (`tythe/codegen.py`)

Codegen reads an `AppIR` and emits one TypeScript file. The strategy:

- **Types**: every msgspec `Struct` / `TypedDict` / `dataclass` becomes a
  `type` declaration; shared types are deduped via the components map.
- **Discriminated unions**: msgspec `tag=` becomes a TS `kind: "..."` field
  so narrowing works the way TS expects.
- **Streaming**: an endpoint with `stream[T]` becomes a method returning
  `AsyncIterable<T>` (or, for tagged unions, the narrowed shape).
- **Errors**: `@raises(A, B)` becomes `Result<T, A | B>`. The client is
  forced to handle the typed cases.
- **The client object**: a `createClient({ routes: [...] })` call followed
  by a thin `Proxy` so calls like `api.users.get` are synthesized at runtime
  from the route table — but the _types_ are static.

The output is **one** file. Not a `client/` directory. Not 12 `*.types.ts`
files. One file you import.

### 5. The dev loop (`tythe/cli.py` + `watchfiles`)

`tythe dev` does three things in one process:

1. Spawn uvicorn with reload enabled (so handler edits hot-reload).
2. Watch `*.py` with `watchfiles` and rerun IR extraction on change.
3. Write the codegen output to the configured path atomically (write tmp →
   `rename`) so your TS toolchain never reads a half-written file.

Everything is logged with `rich` so the terminal stays readable.

### 6. The TS runtime (`@tythe/ts`)

The runtime is ~3 KB min+gz. It exports:

- `createClient(config)` → a `Proxy` that dispatches `api.<name>(...)` to
  the matching route in the config.
- `parseSSE(stream)` → a minimal SSE parser. Used by the generated client
  to turn `fetch().body` into a typed `AsyncIterable<TEvent>`.
- `Result<T, E>` / `Ok<R>` / `Err<R>` → the envelope type and the helpers
  for unwrapping a route's success and error type from its return.

Zero dependencies. ESM-first. Side-effect-free. Tree-shakable.

## Why this shape

A few decisions I want to call out explicitly.

**Why an IR at all, instead of inspect → string?**
Because polyglot. The IR is JSON Schema 2020-12 with a thin Tythe layer for
streams/errors/tasks. The day someone wants a Swift or Kotlin client, we
walk the same IR with a different renderer.

**Why msgspec over Pydantic by default?**
Speed and tightness of the JSON Schema output. msgspec is 2–30× faster than
Pydantic v2 on the codecs that matter for high-throughput endpoints, and its
schema export is conservative and predictable. Pydantic ships as a
first-class plugin (`tythe[pydantic]`) for users who want it.

**Why SSE for streaming, not WebSockets?**
Browser support is built in (`EventSource`), it passes proxies cleanly, and
most server-push protocols have standardized on it. WS opens you up to
bidirectional state-management complexity that most apps don't need. WS is
on the roadmap (`bidi[Send, Recv]`) for the cases that actually want it.

**Why a Proxy client instead of generated functions?**
Same reason tRPC does it: the dot path is the only API surface to learn,
and the types come from the generated `.d.ts` for free. We avoid
hand-writing (or generating) one function per endpoint.

## Where to read the code

- [`packages/tythe/src/tythe/app.py`](../packages/tythe/src/tythe/app.py)
- [`packages/tythe/src/tythe/ir.py`](../packages/tythe/src/tythe/ir.py)
- [`packages/tythe/src/tythe/codegen.py`](../packages/tythe/src/tythe/codegen.py)
- [`packages/tythe/src/tythe/streaming.py`](../packages/tythe/src/tythe/streaming.py)
- [`packages/tythe/src/tythe/cli.py`](../packages/tythe/src/tythe/cli.py)
- [`packages/tythe-ts/src/`](../packages/tythe-ts/src)

If you read all of those and still have a "wait, how does X work?" question,
that's a docs bug. Please file it.
