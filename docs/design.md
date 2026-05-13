# Design

The choices Tythe makes, what they buy you, and what they cost.

## The contract: your function signature

```python
@app.post("/posts")
async def create_post(data: CreatePost) -> Post: ...
```

That's the entire API contract. Inputs are parameter type hints. Output is the return annotation.

What this gets you:

- One source of truth. No `class CreatePostRequest(BaseModel)` floating in `schemas/`.
- The type-checker is the linter. Adding a field on the Python side fails the TS build until the client uses it.
- No tools to learn beyond `tythe dev`. Editors do the rest.

What it costs you:

- You can't share one model across multiple routes by importing it under a different name. Define the type once, reference it from every handler that uses it.

## Codegen exists, but you never see it

One command — `tythe dev` — runs your ASGI app, watches files, and writes one `client.ts` into your frontend. No `package.json` script. No pre-commit hook. No "did CI run codegen?". The watcher owns it.

The generated file is one file, not a `client/` directory with twelve `*.types.ts`. You can grep it, diff it, snapshot it, commit it (or `.gitignore` it — your call).

## One transport, two shapes

- **Unary**: HTTP POST/GET + JSON. Boring, cacheable, works through every proxy.
- **Streaming**: SSE with a typed discriminated-union event envelope.
- **Bidirectional**: opt-in via `bidi[Send, Recv]`. Off by default.

Why SSE over WebSockets for streaming: native browser support (`EventSource`), passes corporate proxies cleanly, the wire is just `text/event-stream` you can `curl`. WebSockets are a different mental model (connection state, framing, ping/pong) most apps don't need. The `bidi[...]` primitive exists for the cases that genuinely do.

## msgspec by default, Pydantic on opt-in

msgspec is **2–30× faster than Pydantic v2** for decode/encode on the codecs that matter for high-throughput endpoints. Its `Struct` is a slot-based C extension with native JSON Schema export — exactly what the codegen needs.

What this gets you:

- Server-side encode/decode that doesn't dominate p99.
- A schema export that's stable and predictable, so the generated TS doesn't change shape on a Pydantic upgrade.

What it costs you:

- msgspec is less famous than Pydantic. If your team only knows Pydantic, install `tythe[pydantic]` and use `BaseModel` everywhere — it's a first-class plugin, not a shim.

## Errors are values

`@raises(IssueNotFound, Forbidden)` on a handler becomes `Result<T, IssueNotFound | Forbidden>` on the client. The TS compiler forces the caller to branch on `result.ok` before reaching `result.data`.

What this gets you:

- No `try/catch` lottery on the client.
- No string-matching on `error.detail`.
- Exhaustiveness checks: add a new error to `@raises(...)` and every call site lights up red until you handle it.

What it costs you:

- You have to declare what a handler raises. Undeclared exceptions become 500s and don't reach the client typed.

## camelCase ↔ snake_case at the boundary

The wire is snake_case (Python). The TS surface is camelCase. The runtime translates JSON keys both directions on every request and response.

What this gets you:

- Python code stays idiomatic. `user_id`, not `userId`.
- TS code stays idiomatic. `userId`, not `user_id`.
- You never see the translation. It happens once at the wire boundary.

## Generated client output is part of the public surface

A minor version bump that changes the shape of `client.ts` in a way that breaks a working caller is a breaking change. The output rules — multi-line wrapping past N fields, JSDoc from docstrings, trailing commas — are part of the contract.

What this gets you: your client doesn't break when you `pnpm up @tythe/ts` to a new patch version.

## What's not in the box

- **No auth implementation.** `Depends(current_user)` is the integration point. Recipes for Clerk / Auth0 / NextAuth / session cookies in [`docs/auth.md`](./auth.md).
- **No rate limiting / caching headers / ETag.** Middleware territory. `ctx.set_header` covers the basics.
- **No LLM-shaped types.** LLM tokens are typed SSE events — use `stream[T]`. Bring your own OpenAI/Anthropic SDK.
- **No GraphQL.** Different mental model. Strawberry exists.
- **No bundled frontend template.** Tythe writes a file into your `src/`. Pick your own framework.
- **No managed hosting.** It's a library. Modal / Fly / Render handle hosting fine.

## How it compares

|                        | **Tythe**                               | FastAPI + openapi-typescript | tRPC          | Encore.ts          | Connect-RPC              | Reflex              |
| ---------------------- | --------------------------------------- | ---------------------------- | ------------- | ------------------ | ------------------------ | ------------------- |
| Backend lang           | **Python**                              | Python                       | TypeScript    | TS / Go            | Polyglot                 | Python              |
| Frontend lang          | **Any TS**                              | TS                           | TS only       | TS only            | Polyglot                 | None — JS hidden    |
| DTO duplication        | **None**                                | Yes                          | None          | None               | Yes (`.proto`)           | N/A                 |
| Codegen visible to dev | **`tythe dev` only**                    | Yes, explicit                | None          | Implicit (build)   | Yes, `buf gen`           | None                |
| Streaming type-safe    | **Yes (typed SSE union)**               | Painful / manual             | Subscriptions | Yes                | Yes                      | N/A                 |
| Typed errors → TS      | **Discriminated union**                 | HTTP codes                   | `TRPCError`   | Yes                | Yes (`isAPIError`)       | N/A                 |
| Validation runtime     | msgspec (Pydantic opt-in)               | Pydantic v2                  | Zod           | Rust + JSON Schema | Protovalidate            | Pydantic            |
| Best for               | **Python backend + modern TS frontend** | CRUD APIs + external clients | TS monorepo   | TS/Go monorepo     | Cross-team microservices | Internal dashboards |

## Polyglot clients

The IR is JSON Schema 2020-12 plus a thin Tythe layer for streams/errors/tasks. The TypeScript renderer is one consumer; Swift and Kotlin ship in core (`tythe swift`, `tythe kotlin`). Anything that reads JSON Schema can read Tythe's IR.

What this gets you: if you ship a mobile app later, the same Python handler also generates a Swift or Kotlin client off the same source of truth.

## Why this matters for your repo

If your stack is Python + modern TS, Tythe removes the codegen ceremony you don't want to deal with — but it doesn't replace your Python framework, your auth, your ORM, or your frontend framework. It's the wire between two halves of your app, with the types intact.

If your stack is something else, Tythe probably isn't the right tool. tRPC is great for TS monorepos. Connect-RPC is great for polyglot microservices. Reflex is great for internal dashboards. Pick the right tool for the actual constraint.

## Stability commitments

The four pillars of the v1.0 freeze are written down, not just promised:

- **Public API** — what we keep stable, what counts as a break, the deprecation cycle: [`docs/semver.md`](./semver.md).
- **Wire format / IR** — additive-only invariants on the JSON-Schema IR and the on-the-wire envelope: [`docs/ir-stability.md`](./ir-stability.md).
- **LTS** — support windows, backport policy, EOL rules: [`docs/lts.md`](./lts.md).
- **Codegen output** — the generated TypeScript client is part of the surface, not an implementation detail. A minor bump must not break a working client.

## Want to read the code?

- [`packages/tythe/src/tythe/app.py`](../packages/tythe/src/tythe/app.py)
- [`packages/tythe/src/tythe/ir.py`](../packages/tythe/src/tythe/ir.py)
- [`packages/tythe/src/tythe/codegen.py`](../packages/tythe/src/tythe/codegen.py)
- [`packages/tythe/src/tythe/streaming.py`](../packages/tythe/src/tythe/streaming.py)
- [`packages/tythe-ts/src/`](../packages/tythe-ts/src)

Full walk-through in [`docs/architecture.md`](./architecture.md).
