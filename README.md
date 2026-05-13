<div align="center">

# Tythe

_pronounced **"tythe"** — rhymes with "scythe" (`/taɪð/`)_

**Write a Python handler. Call it from TypeScript with full types. No DTOs, no OpenAPI codegen, no broken types after a refactor.**

[![CI](https://github.com/tamimbinhakim/tythe/actions/workflows/ci.yml/badge.svg)](https://github.com/tamimbinhakim/tythe/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/tythe.svg)](https://pypi.org/project/tythe/)
[![npm](https://img.shields.io/npm/v/@tythe/ts.svg)](https://www.npmjs.com/package/@tythe/ts)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

[**Quickstart**](./docs/getting-started.md) · [**Docs**](./docs) · [**Examples**](./examples)

</div>

## What you get

```python
# server/app.py
from tythe import App
import msgspec

app = App()

class User(msgspec.Struct):
    id: int
    email: str
    name: str

@app.get("/users/{user_id}")
async def get_user(user_id: int) -> User:
    return await db.get_user(user_id)
```

```ts
// frontend/anywhere.tsx
import { api } from "@/lib/tythe/client";

const user = await api.getUser({ userId: 1 });
//    ^? User — full type, autocomplete, refactor-safe
```

That's the whole loop. `tythe dev` rewrites `client.ts` every time you save Python, so the TS side is always in sync.

## Why you'd use it

- **Zero DTO duplication.** Your Python function signature _is_ the API contract. No `class CreatePostRequest(BaseModel)` mirrored in three files.
- **Method names that don't make you cry.** `api.getUser(...)` — not `createPostPostsPost`.
- **Typed streaming out of the box.** `stream[T]` becomes `AsyncIterable<T>` on the client, with auto-reconnect on drop.
- **Typed errors as discriminated unions.** `@raises(NotFound, Forbidden)` → `Result<T, NotFound | Forbidden>`. The compiler forces you to handle each case.
- **One file, not twelve.** The generated client is a single `client.ts` you can read, diff, and grep.
- **Framework-agnostic on both ends.** Python web framework: tythe (Starlette under the hood). Frontend: anything that runs TS — Next.js, Vite, SvelteKit, Astro, Solid Start.
- **First-class hooks for the big three.** `@tythe/react` (TanStack Query), `@tythe/svelte` (stores), `@tythe/solid` (resources). Server-side prefetch helpers ship with each.
- **Fast.** msgspec on the hot path — 2–30× faster than Pydantic v2 on decode/encode. Pydantic still ships as a first-class plugin (`tythe[pydantic]`).

## What it ships

| Primitive                                     | What it does                                                                |
| --------------------------------------------- | --------------------------------------------------------------------------- |
| `@app.{get,post,put,patch,delete}`            | Route decorators. Param locations inferred from path + type shape.          |
| `Annotated[T, Query/Header/Cookie/Path/Body]` | Explicit param-location markers when inference isn't enough.                |
| `Annotated[list[T], Query()]`                 | List-valued query params (`?tag=a&tag=b`).                                  |
| `Annotated[T, Form()]`                        | `application/x-www-form-urlencoded` or multipart form bodies.               |
| `Annotated[UploadFile, File()]`               | Multipart file uploads.                                                     |
| `Bytes`                                       | Raw request / response bodies (webhooks, downloads). No JSON envelope.      |
| `stream[T]`                                   | Typed Server-Sent Events. `AsyncIterable<T>` on the client.                 |
| `@raises(Err1, Err2, ...)`                    | Typed errors → `Result<T, Err1 \| Err2>` on the client, narrowable by kind. |
| `Context`                                     | Shape the response: status, headers, cookies, after-hooks.                  |
| `Depends(provider)`                           | FastAPI-shape dependency injection. Plain / async / generator providers.    |
| `after(fn, *args, **kw)`                      | Run a callback after the response is sent.                                  |
| `mount_task_routes(...)`                      | Long-running jobs: submit + status + stream from one handler.               |
| `tythe.otel.instrument(app)`                  | One OpenTelemetry span per request (optional extra: `tythe[otel]`).         |
| `tythe openapi / swift / kotlin` (CLI)        | Emit OpenAPI 3.1, Swift, or Kotlin clients off the same IR.                 |

Full surface in [`docs/reference.md`](./docs/reference.md).

## Install

```bash
# Server
uv add tythe

# Client runtime (any frontend)
pnpm add @tythe/ts

# Framework hooks (optional)
pnpm add @tythe/react   # or @tythe/svelte / @tythe/solid
```

## Run

```bash
tythe dev server.app:app --out ../frontend/src/lib/tythe/client.ts
```

What that does:

1. Starts your ASGI app on `http://127.0.0.1:8000`.
2. Watches `*.py`. On save, regenerates `client.ts` atomically into your frontend.
3. Your TS toolchain hot-reloads on the new file.

That's it. Walkthrough in [docs/getting-started.md](./docs/getting-started.md).

## How it compares

|                     | **Tythe**                               | FastAPI + openapi-typescript | tRPC          | Connect-RPC              |
| ------------------- | --------------------------------------- | ---------------------------- | ------------- | ------------------------ |
| Backend lang        | **Python**                              | Python                       | TypeScript    | Polyglot                 |
| DTO duplication     | **None**                                | Yes                          | None          | Yes (`.proto`)           |
| Codegen step        | **Invisible (`tythe dev`)**             | Manual rerun                 | None          | `buf gen`                |
| Streaming type-safe | **Yes (typed SSE)**                     | Manual                       | Subscriptions | Yes                      |
| Typed errors → TS   | **Discriminated union**                 | HTTP codes                   | `TRPCError`   | Yes                      |
| Best for            | **Python backend + modern TS frontend** | External clients             | TS monorepo   | Cross-team microservices |

## SSR

Server-rendered first paint with no waterfall. Each framework has a prefetch helper in its `/server` subpath:

```tsx
// Next.js App Router
import { prefetchQuery } from "@tythe/react/server";
await prefetchQuery(queryClient, api, "getUser", { userId: 1 });
```

```ts
// SvelteKit
import { loadQuery } from "@tythe/svelte/server";
export const load = (event) => ({
  me: await loadQuery(api, "me", undefined, event),
});
```

```tsx
// Solid Start
import { serverQuery } from "@tythe/solid/server";
return serverQuery(api, "me", undefined, event.request);
```

Auth/cookies/tracing headers forward automatically via [`forwardHeaders`](./docs/ssr.md). Full guide in [`docs/ssr.md`](./docs/ssr.md).

## Packages

| Package                                          | What it is                                                                                  | Status |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------- | ------ |
| [`tythe`](./packages/tythe) (PyPI)               | Python framework, CLI, codegen.                                                             | v0.1   |
| [`@tythe/ts`](./packages/tythe-ts) (npm)         | ~3 KB framework-agnostic TS runtime. Works with any frontend.                               | v0.1   |
| [`@tythe/react`](./packages/tythe-react) (npm)   | React hooks (`useQuery`, `useMutation`, `useSubscription`) on TanStack Query + SSR helpers. | v0.1   |
| [`@tythe/svelte`](./packages/tythe-svelte) (npm) | Svelte 5 store bindings + SSR helpers.                                                      | v0.1   |
| [`@tythe/solid`](./packages/tythe-solid) (npm)   | SolidJS resource bindings + SSR helpers.                                                    | v0.1   |

## Stability

Pre-1.0. Pin exact versions. After 1.0:

- **Patch + minor never break.** Wire format / IR is additive-only.
- **Major bumps follow a deprecation cycle** — one full minor of warnings before removal.
- **Generated client output is part of the surface.** A minor bump won't break a working client.

Details: [`docs/semver.md`](./docs/semver.md), [`docs/ir-stability.md`](./docs/ir-stability.md), [`docs/lts.md`](./docs/lts.md).

## What it doesn't do

- **No auth implementation.** Wire `Depends(current_user)` to your provider. Recipes in [`docs/auth.md`](./docs/auth.md).
- **No LLM-shaped types in core.** LLM tokens are typed SSE events — use `stream[T]`. Bring your own OpenAI/Anthropic/LangChain code.
- **No GraphQL.** Different mental model. Strawberry exists.
- **No WebSockets by default.** SSE covers most server-push cases. WS is opt-in via `bidi[Send, Recv]` (roadmap).

## Contributing

Issues that start with "I tried to do X and got confused" are the best kind. Read [CONTRIBUTING.md](./CONTRIBUTING.md), be kind ([Code of Conduct](./CODE_OF_CONDUCT.md)).

## License

[MIT](./LICENSE).
