# Design

This is the long version. The "why" behind every "what." If you're trying
to evaluate Tythe against the alternatives, or you're considering
contributing and want to know which way the wind blows, this is the doc
to read.

## The problem (or: why I built this)

I've been constantly facing this issue. You probably have too.

You're building a product. The backend is in Python — because that's
where your data, your auth, your queues, your background jobs, your team
already are. But your users live in a browser. They expect a real
frontend — Next.js, Vite, SvelteKit — written by people who do not want
to touch a Jinja template.

So you do the dance:

1. Define a Pydantic model: `class CreatePostRequest(BaseModel): ...`
2. Reference it from a FastAPI handler
3. Mount `/openapi.json`
4. Run `openapi-typescript` or `@hey-api/openapi-ts` or Orval or Kubb or
   `openapi-generator`
5. Get back a generated client where your endpoint is now called
   `createPostPostsPost` and your body type is
   `Body_create_post_posts_post`
6. Wrap it in a hand-written hook because nobody wants
   `createPostPostsPost` in their JSX
7. Forget to re-run the codegen
8. Ship a bug

That's the boring case. Then you try to **stream** anything from the
server — server-sent events, progress updates, partial responses, log
lines — and the whole thing falls apart. OpenAPI's story for SSE is
"good luck." Your generated client doesn't have one. So you hand-parse
`data:` lines in a `fetch` body reader and cast everything to `any`.

I kept hitting this. Every project. Every team I talked to was hitting
it. The existing tools — tRPC, Connect-RPC, Reflex — each get part of
it right and miss the rest:

|             | What it gets right                                                  | What it misses                                           |
| ----------- | ------------------------------------------------------------------- | -------------------------------------------------------- |
| tRPC        | The Proxy client UX, the "type _is_ the contract" feel              | TypeScript-only. Can't reach Python types.               |
| Connect-RPC | Real cross-language type safety, streaming                          | `.proto` files as source of truth. Alien data model.     |
| Reflex      | "Just write Python"                                                 | Hides JS entirely. Wrong abstraction for real frontends. |
| Encore.ts   | The pattern proof (parse types → derive schema → emit typed client) | TypeScript / Go only.                                    |

So I wrote Tythe. The gap is real, it's structural, and nothing in the
landscape was going to close it without active work.

## The core insight

tRPC works because TypeScript's compiler can `import type` a router
definition from the server and _structurally infer_ every input and
output at the client's compile time. The two halves are the same
language.

Python's type hints are runtime annotations (PEP 484/526), erased at
execution, living in a completely different language runtime than the
TS client. There is no path to tRPC-style inference that crosses the
Python/TS boundary. _Some_ schema-extraction step is required.

So the question isn't "can we avoid codegen?" It's: **can we make
codegen invisible?**

That's the whole bet. One `tythe dev` command. One file written into
your frontend. No "wait, did I run the codegen?" No
`Body_create_post_posts_post`. The function signature is the contract.
Everything else is plumbing.

## Design principles

In rough order of importance:

### 1. The Python function signature is the contract.

No separate Pydantic model declared above the handler that the handler
then references. Inputs are parameter type hints; output is the return
annotation. The handler _is_ the schema.

Three idiomatic styles, all of which collapse to one declaration:

```python
# A. Inline Struct — purpose-built inputs
class CreatePost(msgspec.Struct):
    title: str; body: str
@app.post("/posts")
async def create(data: CreatePost) -> Post: ...

# B. Annotated params — small handlers
@app.post("/login")
async def login(
    email: Annotated[str, Body()],
    password: Annotated[str, Body()],
    remember: Annotated[bool, Query()] = False,
) -> Session: ...

# C. TypedDict — reuse a shape
class Pagination(TypedDict):
    cursor: str | None
    limit: int
@app.get("/feed")
async def feed(page: Annotated[Pagination, Query()]) -> Page[Post]: ...
```

In every case, the parameter annotation _is_ the validator. No
`class Foo(BaseModel)` declared in another file that the handler then
re-mentions.

### 2. Codegen exists, but is invisible.

One command (`tythe dev`) runs the server, watches files, and writes
one `client.ts` into the frontend. Developers never think about it
after `tythe init`. No build step in `package.json`. No pre-commit
hook. No "oh, the CI runs codegen too." The watcher owns it.

### 3. One transport, two shapes.

- **Unary**: HTTP POST + JSON. Boring. Works everywhere. Cacheable.
- **Streaming**: SSE with a typed discriminated-union event envelope.
- **Bidirectional**: opt-in via `bidi[Send, Recv]`. Not the default.

WebSockets are powerful, and they're a different mental model. Most
apps don't need them. SSE has first-class browser support, passes
proxies, and is what most server-push protocols have standardized on.
Defaulting to SSE keeps the common case simple.

### 4. msgspec by default, Pydantic on opt-in.

Public benchmarks consistently show msgspec is **2–30× faster** than
Pydantic v2 for decode/encode and **~100×** faster than v1. msgspec's
`Struct` is a slot-based C extension with native JSON Schema export,
no allocator-heavy model wrapping, and explicit support for
`TypedDict`, dataclasses, and unions.

For a framework whose serialization sits on the hot path of every
request (and especially on streaming endpoints), defaulting to msgspec
is the right call.

Pydantic is a **first-class plugin** (`tythe[pydantic]`), not a
second-class one. A large slice of the Python ecosystem lives in
Pydantic-land, and refusing to support it would be malpractice.

### 5. Errors are values.

TypeScript doesn't have native exceptions across IO boundaries.
Discriminated unions are the right primitive. `@raises(Err1, Err2)`
on a Python handler becomes `Result<T, Err1 | Err2>` on the client —
and the type checker forces the caller to handle each typed case.

No "try/catch lottery" on the TS side. No string-matching
`error.detail`.

### 6. No magic globals.

The router is an explicit `App` object you compose. ASGI underneath.
Deploy anywhere uvicorn runs. No framework-detected module-level
auto-discovery.

### 7. Ship the fundamentals; let users build the rest.

Tythe ships at the lowest useful level of abstraction: typed RPC,
typed streaming, typed errors, cancellation, file uploads,
dependency injection. That's the framework.

We **do not** ship vertical integrations — no `tythe.ai` module, no
LLM client adapters, no React hooks in core, no chat-bot primitives,
no auth providers. Those layers compose on top of the fundamentals,
and they belong in separate packages (`@tythe/react`, `@tythe/svelte`,
community plugins, your own code). Tying them into core would couple
Tythe's release cadence to ecosystems that move on their own
schedules, and that has historically gone badly for general-purpose
frameworks.

> An LLM token stream is just a typed SSE event. A progress feed is
> just a typed SSE event. A pubsub topic is just a typed SSE event.
> Ship the fundamental; the vertical use cases come for free.

## What I'm explicitly _not_ doing

| Decision                            | Rationale                                                                                                                                                                                                                        |
| ----------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **No `tythe.ai` module.**           | LLM-shaped types (Token, Image, Audio) belong in user code or a separate plugin. The core stays application-agnostic.                                                                                                            |
| **No GraphQL.**                     | Different mental model. Scope balloons. People who want GraphQL have Strawberry.                                                                                                                                                 |
| **No managed hosted service.**      | Tythe is a library. Modal / Fly / Render handle hosting fine.                                                                                                                                                                    |
| **No bundled frontend template.**   | Bring your own frontend. Tythe writes a file into your `src/`.                                                                                                                                                                   |
| **WS as default streaming.**        | SSE is enough. Simpler. Industry-standard. WS is opt-in.                                                                                                                                                                         |
| **OpenAPI as the canonical IR.**    | OpenAPI loses fidelity on discriminated unions, generics, streaming. Tythe's IR is JSON Schema + a thin extension layer. OpenAPI export is on the v0.3 roadmap as a _secondary_ output for users who also need external clients. |
| **React hooks in the core client.** | `@tythe/ts` is framework-agnostic. React-specific bindings live in `@tythe/react`. Svelte in `@tythe/svelte`. And so on.                                                                                                         |

## Comparison to alternatives

|                        | **Tythe**                               | FastAPI + openapi-typescript | tRPC              | Encore.ts          | Connect-RPC              | Reflex              |
| ---------------------- | --------------------------------------- | ---------------------------- | ----------------- | ------------------ | ------------------------ | ------------------- |
| Backend lang           | **Python**                              | Python                       | TypeScript        | TS / Go            | Polyglot                 | Python              |
| Frontend lang          | **Any TS**                              | TS                           | TS only           | TS only            | Polyglot                 | None — JS hidden    |
| DTO duplication        | **None**                                | Yes                          | None              | None               | Yes (`.proto`)           | N/A                 |
| Codegen visible to dev | **`tythe dev` only**                    | Yes, explicit                | None              | Implicit (build)   | Yes, `buf gen`           | None                |
| Streaming type-safe    | **Yes (typed SSE union)**               | Painful / manual             | Subscriptions     | Yes                | Yes                      | N/A                 |
| Typed errors → TS      | **Discriminated union**                 | HTTP codes                   | `TRPCError`       | Yes                | Yes (`isAPIError`)       | N/A                 |
| Validation runtime     | msgspec (Pydantic opt-in)               | Pydantic v2                  | Zod               | Rust + JSON Schema | Protovalidate            | Pydantic            |
| Setup cost             | **`tythe init` + `tythe dev`**          | High                         | Low (TS monorepo) | Low                | Medium                   | Low                 |
| Best for               | **Python backend + modern TS frontend** | CRUD APIs + external clients | TS monorepo       | TS/Go monorepo     | Cross-team microservices | Internal dashboards |

## Risks I'm aware of

I'd rather call these out than pretend they don't exist.

1. **Codegen UX edge cases.** Forward references, generics over
   `TypeVar`, recursive types, and `Union` of structs with overlapping
   field sets are notoriously fiddly. We pin to msgspec's tag-union
   conventions, ban implicit untagged unions of structs, and ship a
   clear linter for ambiguous IRs. Where this fails, we fail loudly.

2. **Python ecosystem inertia.** FastAPI has enormous mindshare and
   is "good enough." Tythe must win on the codegen UX, the
   single-file generated client, and first-class typed streaming —
   not on raw feature count.

3. **Frontend framework matrix.** Next.js, Vite, SvelteKit, Astro,
   Remix, Expo all behave differently around watcher integration and
   bundling generated files. We solve Next.js and Vite first; the
   rest follow.

4. **Pydantic gravity.** Many target users live in Pydantic-land.
   Refusing to support Pydantic kills adoption. We solve this with
   the `tythe[pydantic]` peer plugin.

5. **Streaming protocols are messy.** SSE itself is stable, but the
   patterns layered on top (event envelopes, reconnection, resume
   tokens) vary. Tythe ships its own conservative wire protocol
   (tagged JSON over SSE) and offers adapters to common third-party
   protocols as _separate_ packages, so the core never has to chase
   someone else's spec.

6. **Maintenance burden of the TS client.** The runtime must stay
   tiny (~3 KB) and dependency-free; otherwise it becomes a
   liability. We mirror tRPC's discipline here.

## What "done" looks like for v1.0

- A new contributor can read [`docs/getting-started.md`](./getting-started.md),
  follow it, and have a typed end-to-end call working in under 5
  minutes from a clean machine.
- `npx create-tythe-app` produces a working Next.js + Tythe project
  that runs in 60 seconds from clone to first response.
- The generated `client.ts` for a 50-route API is under 200 KB
  ungzipped.
- A real OSS user has shipped a real product on Tythe. I want one
  testimonial before 1.0.

If you're building something that maps to this design and you hit a
wall, [open an issue](https://github.com/tamimbinhakim/tythe/issues). The
walls are how I find out what's wrong.
