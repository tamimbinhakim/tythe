# Roadmap

This is what's shipping when. Priorities shift, the world is
unpredictable. But it's the most honest plan I have.

If you want to influence it, the highest-leverage move is to open an
issue saying "I tried to use Tythe for X and it didn't work because Y."
That's worth more than ten feature requests.

## v0.1 — MVP

The bet: get the core loop right. Everything else is post-MVP.

- [x] App / router / handler registration
- [x] Unary HTTP+JSON with msgspec validation
- [x] Type extraction → JSON Schema IR
- [x] TS codegen: single file, Proxy-based client, types, fetch wrapper,
      AbortSignal
- [x] `tythe dev`, `tythe build`, `tythe codegen` CLI
- [x] SSE streaming with `stream[T]` and tagged-union events
- [x] `@raises(...)` typed errors → `Result<T, E>` on client
- [x] Multipart file uploads via a generic `File` parameter marker
- [x] Cookie / header / query / body via `Annotated`
- [x] DI container compatible with FastAPI's `Depends()`
- [x] `Bytes` for raw request/response bodies (webhooks, downloads)
- [x] `after(fn, …)` post-response hook + `ctx.set_status` / `ctx.set_header`
- [x] Examples for Next.js, Vite/React, and SvelteKit
- [x] One short hero demo: typed streaming end-to-end in **<50 lines**

## v0.2 — Framework bindings + Pydantic

Once the core is solid, meet the JS ecosystem where it lives.

- [x] Pydantic plugin (`tythe[pydantic]`) — first-class peer to msgspec
- Framework-specific binding packages (separate from `@tythe/ts`,
  which stays framework-agnostic):
  - [x] `@tythe/react` — `useQuery`, `useMutation`, `useSubscription`
        on top of TanStack Query
  - [x] `@tythe/svelte` — store-based bindings
  - [x] `@tythe/solid` — `createResource`-style bindings
- [~] `Task[T]` long-running job queue — `TaskBackend` Protocol and
  `InMemoryBackend` ship; runtime/codegen don't yet recognize a
  `Task[T]` return annotation, and Redis / SQS adapters are
  separate packages.

## v0.3+ — Polyglot, auth, observability

- [ ] WebSocket bidirectional (`bidi[Send, Recv]`) — not started.
- [x] Auth recipes (NextAuth, Clerk, custom JWT) — see [`docs/auth.md`](./docs/auth.md)
- [x] Optional OpenAPI 3.1 export via `tythe openapi` for users who also
      need to serve external clients
- [x] Polyglot clients (Swift, Kotlin) via the same IR — `tythe swift`
      and `tythe kotlin` emit working HTTP clients (typed args, typed
      responses, typed `@raises` error unions, snake_case mapping,
      URLSession / HttpURLConnection transport). Full per-language SSE
      parsers for streaming endpoints remain a follow-up.
- [x] Tracing/observability — OpenTelemetry ASGI middleware via
      `tythe.otel.instrument(app)`
- [x] `tythe deploy` thin wrapper for Fly / Render / Modal

## Won't do (probably)

Some lines I'm holding for now. If enough people push back I'll
reconsider — but the default is no.

- **A `tythe.ai` module / LLM-specific types.** Tythe ships at the
  fundamental level: RPC, streaming, errors, cancellation. LLM tokens,
  tool calls, agent state, structured outputs — those are user code or
  a separate plugin (`tythe-llm`, community-maintained). The core stays
  application-agnostic.
- **WebSockets as the default streaming transport.** SSE is enough,
  simpler, and matches what every major server-push protocol
  standardized on. WS is opt-in.
- **A monorepo template that bundles Next.js.** Bring your own
  frontend. Tythe writes a file into your `src/`. That's it.
- **GraphQL support.** Different mental model. Scope balloon. Not doing
  it.
- **A managed hosted service.** Tythe is a library. Modal / Fly /
  Render handle hosting just fine.

## Influences

In rough order of "how much I stole from each":

- **tRPC** — for the Proxy client UX and the "the type _is_ the
  contract" idea.
- **Encore.ts** — for the proof that parse-types-and-codegen works.
- **FastAPI** — for the `Depends()` DI pattern and the dev-loop
  ergonomics.
- **Litestar** — for showing that msgspec-first ASGI is viable.
- **TanStack Query** — for the bar on what good client-side data
  ergonomics looks like.

If you've worked on one of these and have opinions about what we
should steal next, please open an issue.
