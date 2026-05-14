<div align="center">

# Dyadpy

**Write a Python handler. Call it from TypeScript with full types. No DTOs, no OpenAPI codegen, no broken types after a refactor.**

[![CI](https://github.com/tamimbinhakim/dyadpy/actions/workflows/ci.yml/badge.svg)](https://github.com/tamimbinhakim/dyadpy/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/dyadpy.svg)](https://pypi.org/project/dyadpy/)
[![npm](https://img.shields.io/npm/v/@dyadpy/ts.svg)](https://www.npmjs.com/package/@dyadpy/ts)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

[**Quickstart**](./docs/getting-started.md) · [**Docs**](./docs) · [**Examples**](./examples)

</div>

## What you get

```python
# server/app.py
from dyadpy import App
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
import { api } from "@/lib/dyadpy/client";

const user = await api.getUser({ userId: 1 });
//    ^? User — full type, autocomplete, refactor-safe
```

That's the whole loop. `dyadpy dev` rewrites `client.ts` every time you save Python, so the TS side is always in sync.

## Why you'd use it

- **Zero DTO duplication.** Your Python function signature _is_ the API contract. No `class CreatePostRequest(BaseModel)` mirrored in three files.
- **Method names that don't make you cry.** `api.getUser(...)` — not `createPostPostsPost`.
- **Typed streaming out of the box.** `stream[T]` becomes `AsyncIterable<T>` on the client, with auto-reconnect on drop.
- **Typed errors as discriminated unions.** `@raises(NotFound, Forbidden)` → `Result<T, NotFound | Forbidden>`. The compiler forces you to handle each case.
- **One file, not twelve.** The generated client is a single `client.ts` you can read, diff, and grep.
- **Framework-agnostic on both ends.** Python web framework: dyadpy (Starlette under the hood). Frontend: anything that runs TS — Next.js, Vite, SvelteKit, Astro, Solid Start.
- **First-class hooks for the big three.** `@dyadpy/react` (TanStack Query), `@dyadpy/svelte` (stores), `@dyadpy/solid` (resources). Server-side prefetch helpers ship with each.
- **Fast.** msgspec on the hot path — 2–30× faster than Pydantic v2 on decode/encode. Pydantic still ships as a first-class plugin (`dyadpy[pydantic]`).

## Day-to-day

**Rename a Python field — TS lights up in red.**

```diff
 class User(msgspec.Struct):
     id: int
-    email: str
+    contact_email: str
```

```ts
user.email;
//   ~~~~~ Property 'email' does not exist on type 'User'.
//         Did you mean 'contactEmail'?
```

Save Python. Your editor tells you exactly which call sites to fix. No grep, no broken prod.

**Add an endpoint — autocomplete picks it up instantly.**

```python
@app.post("/orders")
async def create_order(order: NewOrder) -> Order: ...
```

```ts
api.cr|
//   ^ createOrder  ← appears the moment you save Python
```

**Errors as discriminated unions — forget a case, get a compile error.**

```python
@raises(NotFound, Forbidden)
async def get_user(user_id: int) -> User: ...
```

```ts
const result = await api.getUser({ userId: 1 });
if (!result.ok) {
  switch (result.error.kind) {
    case "NotFound":
      /* ... */ break;
    case "Forbidden":
      /* ... */ break;
    // add a third @raises later? the compiler flags this switch as non-exhaustive.
  }
}
```

**Typed streaming with no extra plumbing.**

```python
@app.get("/build/{id}/events")
async def watch_build(id: int) -> stream[BuildLog]: ...
```

```ts
for await (const log of api.watchBuild({ id: 42 })) {
  log.level; // "info" | "warn" | "error" — autocomplete works
}
```

**One file you can read.** The generated client is a single `client.ts` — diff it in PRs, grep it for routes, paste it into a gist. Not a black-box artifact buried in `node_modules`.

**No codegen step in your head.** No `pnpm gen`, no `buf gen`, no `npm run codegen` to remember. `dyadpy dev` watches Python and writes the client atomically. If it's in your editor, it's in the client.

Full primitives in [`docs/reference.md`](./docs/reference.md).

## Install

> Dyadpy is in **alpha** (`0.1.0a0` / `0.1.0-alpha.0`). The version pin
> and `@alpha` tag below opt you into the prerelease channel. Once
> v0.1.0 ships, drop both.

```bash
# Server
uv add 'dyadpy==0.1.0a0'

# Client runtime (any frontend)
pnpm add @dyadpy/ts@alpha

# Framework hooks (optional)
pnpm add @dyadpy/react@alpha   # or @dyadpy/svelte@alpha / @dyadpy/solid@alpha
```

## Run

```bash
dyadpy dev server.app:app --out ../frontend/src/lib/dyadpy/client.ts
```

What that does:

1. Starts your ASGI app on `http://127.0.0.1:8000`.
2. Watches `*.py`. On save, regenerates `client.ts` atomically into your frontend.
3. Your TS toolchain hot-reloads on the new file.

That's it. Walkthrough in [docs/getting-started.md](./docs/getting-started.md).

## How it compares

|                     | **Dyadpy**                              | FastAPI + openapi-typescript | tRPC          | Connect-RPC              |
| ------------------- | --------------------------------------- | ---------------------------- | ------------- | ------------------------ |
| Backend lang        | **Python**                              | Python                       | TypeScript    | Polyglot                 |
| DTO duplication     | **None**                                | Yes                          | None          | Yes (`.proto`)           |
| Codegen step        | **Invisible (`dyadpy dev`)**            | Manual rerun                 | None          | `buf gen`                |
| Streaming type-safe | **Yes (typed SSE)**                     | Manual                       | Subscriptions | Yes                      |
| Typed errors → TS   | **Discriminated union**                 | HTTP codes                   | `TRPCError`   | Yes                      |
| Best for            | **Python backend + modern TS frontend** | External clients             | TS monorepo   | Cross-team microservices |

## SSR

Server-rendered first paint with no waterfall. Each framework has a prefetch helper in its `/server` subpath:

```tsx
// Next.js App Router
import { prefetchQuery } from "@dyadpy/react/server";
await prefetchQuery(queryClient, api, "getUser", { userId: 1 });
```

```ts
// SvelteKit
import { loadQuery } from "@dyadpy/svelte/server";
export const load = (event) => ({
  me: await loadQuery(api, "me", undefined, event),
});
```

```tsx
// Solid Start
import { serverQuery } from "@dyadpy/solid/server";
return serverQuery(api, "me", undefined, event.request);
```

Auth/cookies/tracing headers forward automatically via [`forwardHeaders`](./docs/ssr.md). Full guide in [`docs/ssr.md`](./docs/ssr.md).

## Packages

| Package                                            | What it is                                                                                  | Status |
| -------------------------------------------------- | ------------------------------------------------------------------------------------------- | ------ |
| [`dyadpy`](./packages/dyadpy) (PyPI)               | Python framework, CLI, codegen.                                                             | v0.1   |
| [`@dyadpy/ts`](./packages/dyadpy-ts) (npm)         | ~3 KB framework-agnostic TS runtime. Works with any frontend.                               | v0.1   |
| [`@dyadpy/react`](./packages/dyadpy-react) (npm)   | React hooks (`useQuery`, `useMutation`, `useSubscription`) on TanStack Query + SSR helpers. | v0.1   |
| [`@dyadpy/svelte`](./packages/dyadpy-svelte) (npm) | Svelte 5 store bindings + SSR helpers.                                                      | v0.1   |
| [`@dyadpy/solid`](./packages/dyadpy-solid) (npm)   | SolidJS resource bindings + SSR helpers.                                                    | v0.1   |

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
