<div align="center">

# Tythe

**A type-safe RPC bridge between Python and TypeScript.**

The function signature is the contract. No DTOs. No OpenAPI codegen
ceremony. No "wait, did I run the codegen?"

[![CI](https://github.com/tamimbinhakim/tythe/actions/workflows/ci.yml/badge.svg)](https://github.com/tamimbinhakim/tythe/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/tythe.svg)](https://pypi.org/project/tythe/)
[![npm](https://img.shields.io/npm/v/@tythe/ts.svg)](https://www.npmjs.com/package/@tythe/ts)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-yellow.svg)](https://conventionalcommits.org)

[**Quickstart**](./docs/getting-started.md) · [**Docs**](./docs) · [**Design**](./docs/design.md) · [**Examples**](./examples)

</div>

## The problem (or: why I built this)

I've been constantly facing this issue. You probably have too.

You're building a product. The backend is in Python — because that's where
your data, your auth, your queues, your background jobs, your team, and
most of the actually interesting code already are. But your users live in
a browser, and your users expect a real frontend — Next.js, Vite,
SvelteKit, whatever — written by people who don't want to touch a Jinja
template ever again.

So you do the dance:

1. Define a Pydantic model `class CreatePostRequest(BaseModel): ...`
2. Reference it from a FastAPI handler
3. Mount `/openapi.json`
4. Run `openapi-typescript` or `@hey-api/openapi-ts` or Orval or Kubb
5. Get back a generated client where your endpoint is now called
   `createPostPostsPost` and your body type is `Body_create_post_posts_post`
6. Wrap it in a hand-written hook because nobody wants
   `createPostPostsPost` in their JSX
7. Forget to re-run the codegen
8. Ship a bug

That's the boring case. Then you need to **stream** something — server
push, progress events, partial updates, log lines — and OpenAPI doesn't
really have an answer. You're hand-parsing `data:` lines in a `fetch` body
reader and casting `any`.

I kept hitting this. Every project. Every team I talked to was hitting it.
None of the existing options — not tRPC (TypeScript-only), not Connect-RPC
(`.proto` files as source of truth), not Reflex (hides JS) — actually
solved the underlying problem at the right level of abstraction.

So: **Tythe**.

## What Tythe is

A thin, opinionated ASGI framework plus a tiny watcher. Your Python
function signature is the contract. At server start, Tythe reads your
types with `inspect` + `typing.get_type_hints`, normalizes them through
`msgspec`'s native JSON Schema export, and writes a single `client.ts`
straight into your frontend.

Then you do this on the TS side:

```ts
import { api } from "@/lib/tythe/client";

const user = await api.getUser({ userId: 1 });

for await (const ev of api.subscribeEvents({ topic: "orders" })) {
  console.log(ev.kind, ev.payload);
}
```

…and that's the whole API surface you have to learn. `api.getUser` is
a Proxy, the types come straight from the generated `.d.ts`, and the
editor gives you autocomplete + inline errors the same way tRPC does —
except your backend is Python.

## Show me the Python side

```python
# server/app.py
from tythe import App, stream, raises
from dataclasses import dataclass
import msgspec

app = App()

# Inputs are just parameters. Outputs are just return types.
@app.get("/users/{user_id}")
async def get_user(user_id: int) -> User:
    return await db.get_user(user_id)

# Multi-field input? Drop a Struct next to the handler. No separate DTO file.
class CreatePost(msgspec.Struct):
    title: str
    body: str
    tags: list[str] = []

@app.post("/posts")
async def create_post(data: CreatePost, ctx: Context) -> Post:
    return await db.create_post(author_id=ctx.user.id, **msgspec.structs.asdict(data))

# Streaming. Just yield typed events. The return annotation tells the
# codegen everything it needs to know.
class Event(msgspec.Struct, tag_field="kind"): ...
class OrderPlaced(Event, tag="order_placed"): order_id: int
class OrderShipped(Event, tag="order_shipped"): order_id: int; carrier: str

@app.get("/events")
async def events(topic: str) -> stream[OrderPlaced | OrderShipped]:
    async for ev in bus.subscribe(topic):
        yield ev

# Typed errors flow to the client as a discriminated union.
@dataclass
class PostNotFound(Exception):
    post_id: int

@app.get("/posts/{post_id}")
@raises(PostNotFound)
async def get_post(post_id: int) -> Post: ...
```

That's it. No `class XRequest(BaseModel)` declared in another file. No
second trip through OpenAPI. No build step you have to remember.

## What you actually get

A small toolbox of bottom-level primitives. Each is type-level — the codegen
sees it and the TS side reflects it. Full surface in
[`docs/reference.md`](./docs/reference.md).

| Primitive                                                      | What it does                                                                                 |
| -------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| `@app.{get,post,put,patch,delete}`                             | Route decorators. Param locations inferred from the path template and type shape.            |
| `Annotated[T, Query/Header/Cookie/Path]`                       | Explicit parameter location markers when inference isn't enough.                             |
| `Annotated[list[T], Query()]`                                  | List-valued query params (`?tag=a&tag=b`).                                                   |
| `Annotated[T, Body()]`                                         | JSON body (single or embedded multi-field).                                                  |
| `Annotated[T, Form()]`                                         | Form bodies — `application/x-www-form-urlencoded` or multipart.                              |
| `Annotated[UploadFile, File()]`                                | Multipart file uploads.                                                                      |
| `Bytes`                                                        | Raw request / response bodies (webhooks, downloads). Skips the JSON envelope.                |
| `stream[T]`                                                    | Typed Server-Sent Events. `T` is usually a tagged union; the client gets `AsyncIterable<T>`. |
| `@raises(E1, E2, …)`                                           | Declared typed errors → `Result<T, E1 \| E2>` on the TS side. Discriminated on `kind`.       |
| `Context` (`ctx.set_status / set_header / set_cookie / after`) | Shape the response without dropping to Starlette.                                            |
| `Depends(provider)`                                            | FastAPI-shape dependency injection. Plain / async / generator providers.                     |
| `after(fn, *args, **kw)`                                       | Run a callback after the response is sent. Free function or `ctx.after(...)`.                |
| `tythe.otel.instrument(app)`                                   | One OpenTelemetry span per request. Optional extra: `tythe[otel]`.                           |
| `tythe.tasks.InMemoryBackend`                                  | Pluggable background-job queue. Redis / SQS adapters as separate packages.                   |
| `tythe openapi / swift / kotlin` (CLI)                         | Emit OpenAPI 3.1, Swift, or Kotlin clients off the same IR.                                  |

## How does it compare?

|                        | **Tythe**                               | FastAPI + openapi-typescript | tRPC          | Encore.ts          | Connect-RPC              |
| ---------------------- | --------------------------------------- | ---------------------------- | ------------- | ------------------ | ------------------------ |
| Backend lang           | **Python**                              | Python                       | TypeScript    | TS / Go            | Polyglot                 |
| Frontend lang          | **Any TS**                              | TS                           | TS only       | TS only            | Polyglot                 |
| DTO duplication        | **None**                                | Yes                          | None          | None               | Yes (`.proto`)           |
| Codegen visible to dev | **`tythe dev` only**                    | Yes, explicit                | None          | Implicit           | Yes, `buf gen`           |
| Streaming type-safe    | **Yes (typed SSE union)**               | Painful / manual             | Subscriptions | Yes                | Yes                      |
| Typed errors → TS      | **Discriminated union**                 | HTTP codes                   | `TRPCError`   | Yes                | Yes                      |
| Validation runtime     | msgspec (Pydantic opt-in)               | Pydantic v2                  | Zod           | Rust + JSON Schema | Protovalidate            |
| Best for               | **Python backend + modern TS frontend** | CRUD + external clients      | TS monorepo   | TS/Go monorepo     | Cross-team microservices |

[Read the full design doc →](./docs/design.md)

## Quickstart (60 seconds)

```bash
# 1. Install the server
uv add tythe

# 2. Install the client runtime in your frontend
pnpm add @tythe/ts

# 3. Run it
tythe dev
```

Tythe writes `frontend/src/lib/tythe/client.ts` on every change. Import
it like any other file. That's the whole loop.

Full walkthrough in [docs/getting-started.md](./docs/getting-started.md).

## Packages

| Package                                          | What it is                                                                                                                                                | Status |
| ------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| [`tythe`](./packages/tythe) (PyPI)               | The Python framework, the CLI, the codegen.                                                                                                               | v0.1   |
| [`@tythe/ts`](./packages/tythe-ts) (npm)         | The tiny (~3 KB) framework-agnostic TS runtime your generated `client.ts` imports. Works with any frontend — Next.js, Vite, SvelteKit, Astro, plain HTML. | v0.1   |
| [`@tythe/react`](./packages/tythe-react) (npm)   | React-specific hooks (`useQuery`, `useSubscription`, `useMutation`) on top of TanStack Query.                                                             | v0.1   |
| [`@tythe/svelte`](./packages/tythe-svelte) (npm) | Svelte 5 store bindings (`query`, `mutation`, `subscription`).                                                                                            | v0.1   |
| [`@tythe/solid`](./packages/tythe-solid) (npm)   | SolidJS resource bindings (`query`, `mutation`, `subscription`).                                                                                          | v0.1   |

## What about AI / LLMs?

Tythe ships at the fundamental level: RPC, typed streaming, typed errors,
cancellation. AI apps benefit from those primitives the same way any other
streaming workload does (LLM tokens are just typed events on an SSE stream),
but Tythe **does not ship LLM-specific types or adapters**. Bring your own
OpenAI / Anthropic / Pydantic AI / LangChain code; Tythe carries the wire.

## Philosophy

Tythe is intentionally a **low-level library**. Every primitive it ships
maps onto an HTTP, SSE, or JSON-Schema concept — nothing higher. There
is no `Cached[T]`, no `RateLimited[T]`, no `Auth[T]`, no page-based
routing, no ORM glue, no LLM types in core, no matter how often any of
those gets asked for. Those are **opinions**, and opinions belong on
top, not inside.

The contract we keep:

- **The function signature is the contract.** No DTO files. No OpenAPI
  round-trip. No `class XRequest(BaseModel)` floating in a `schemas/`
  folder.
- **Codegen is visible exactly once per save.** `tythe dev` rewrites
  `client.ts` atomically. You never run a separate `generate` step.
- **The wire stays HTTP.** JSON + SSE + multipart. No custom protocol.
  Nothing a curl debugger can't read.

## What to expect next

- **Maintenance.** Bug fixes, dependency updates, security patches,
  and integrity of the IR / wire format are the steady commitment.
  This is the part that matters: you should be able to pin a version
  and have it keep working.
- **New primitives, when they earn it.** When a single bottom-level
  piece keeps showing up across real apps — like `Bytes`, `after(...)`,
  `set_cookie`, list query params — it lands in core. Anything that
  carries opinion stays out.
- **Meta-frameworks on top.** File-based routing, monorepo scaffolds,
  multi-tenant conventions, AI-app templates, and similar opinion
  layers are exactly what a **meta-framework** should provide.
  Tythe itself stays unopinionated; someone — possibly us, in a
  separate package (`tythe-kit` or whatever shape it takes) — can
  build a Next.js-flavoured experience on top. The IR is deliberately
  designed to make that possible: read it, scan the file tree, emit
  routes. Everything Tythe knows about your handlers is available to
  consumers of the IR.

If you'd like to build a meta-framework on top, the IR module
(`tythe.ir`) and the CLI surface (`tythe codegen`, `tythe openapi`,
`tythe swift`, `tythe kotlin`) are stable entry points. The OpenAPI
exporter is itself an example of consuming the IR to produce a
secondary artifact.

## Status

Tythe is pre-1.0. The surface area documented in
[`docs/reference.md`](./docs/reference.md) is what we commit to keeping
stable in shape; the internals may move. Pin exact versions until 1.0.

I'm dogfooding this on real projects and shipping changes weekly. If you
want to follow along, watch the repo and read [ROADMAP.md](./ROADMAP.md).

## Contributing

I love PRs. I love issues that start with "I tried to do X and got
confused" even more. Read [CONTRIBUTING.md](./CONTRIBUTING.md), be kind
([Code of Conduct](./CODE_OF_CONDUCT.md)), and let's go.

## License

[MIT](./LICENSE). Use it. Fork it. Build a company on it. Just don't sue me.
