# Examples

Runnable starter projects. Each one is self-contained — `cd` in, install,
run, poke around.

| Example                                  | Stack                                  | What it shows                                                                                                                  |
| ---------------------------------------- | -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| [`nextjs-streaming`](./nextjs-streaming) | Next.js 15 (App Router) + Python `App` | Typed SSE streaming — progress, logs, and a final result — with discriminated-union narrowing and cancellation. The hero demo. |
| [`vite-react`](./vite-react)             | Vite + React + Python `App`            | CRUD on Posts. Typed errors. No framework magic.                                                                               |

> These examples are **not** published to npm or PyPI. They exist to demo
> features and catch regressions in real-world setups. Copy/paste from them
> freely.

## How they're wired

Each example has two halves:

```
examples/<name>/
├── server/                  # Python — runs uvicorn via `tythe dev`
│   ├── app.py
│   └── pyproject.toml
└── frontend/                # Whatever JS framework — runs its own dev server
    ├── src/
    │   └── lib/tythe/
    │       └── client.ts    # Generated. Don't edit.
    ├── package.json
    └── ...
```

Run the server with the watcher, run the frontend separately, profit.

## What's intentionally missing

- **Auth.** Recipes for NextAuth / Clerk / custom JWT are on the v0.3
  roadmap. For now, examples assume single-user.
- **Persistence.** In-memory `dict[int, Post]` is enough to show the wire
  protocol. Bring your own DB.
- **Deployment configs.** No Dockerfiles, no `vercel.json`. Examples are
  local-dev only; deployment is intentionally out of scope.
