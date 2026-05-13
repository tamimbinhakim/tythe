# Server-side rendering

Tythe's runtime (`@tythe/ts`) and every framework adapter
(`@tythe/react`, `@tythe/svelte`, `@tythe/solid`) is SSR-safe by
construction — the generated `client.ts` uses `globalThis.fetch`, never
touches `window`/`document`/`localStorage`, and accepts a custom
`fetch` / `headers` / `baseUrl` for environments that need it.

What you usually want on top of that "doesn't crash under SSR" baseline
is a way to **prefetch on the server, hydrate on the client** — so the
first paint isn't a spinner. Tythe ships three small helpers for that,
one per framework, all sharing the same shape.

## The shape

- **`forwardHeaders(req)`** (from `@tythe/ts`) — pulls cookies, auth,
  CSRF, and tracing headers off the incoming request so your SSR call
  reaches the Python handler authenticated as the user.
- **Framework helper** — bridges the generic Tythe call into the
  framework's prefetch / load primitive (React Query's `prefetchQuery`,
  SvelteKit's `+page.server.ts` load, SolidStart's request event).

## Next.js App Router

```tsx
// app/users/[id]/page.tsx — server component
import {
  dehydrate,
  HydrationBoundary,
  QueryClient,
} from "@tanstack/react-query";
import { prefetchQuery } from "@tythe/react/server";
import { forwardHeaders } from "@tythe/ts";
import { headers } from "next/headers";

import { api } from "@/lib/tythe/client";
import { UserCard } from "./UserCard"; // client component using `useTythe.useQuery`

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const qc = new QueryClient();

  // Forward cookies / auth so the SSR call is authenticated as the user.
  const incoming = new Request("https://x/", { headers: await headers() });
  api.headers = forwardHeaders(incoming); // or pass per-call via `opts.headers`

  await prefetchQuery(qc, api, "getUser", { userId: Number(id) });

  return (
    <HydrationBoundary state={dehydrate(qc)}>
      <UserCard userId={Number(id)} />
    </HydrationBoundary>
  );
}
```

The client component uses `useTythe.useQuery("getUser", { userId: 1 })`
with the same query key — React Query finds the dehydrated entry and
renders instantly without a refetch.

Multiple calls in parallel:

```ts
await prefetchQueries(qc, api, [
  ["getUser", { userId: 1 }],
  ["listPosts", { authorId: 1, limit: 20 }],
  ["getInbox", undefined],
]);
```

## SvelteKit

```ts
// src/routes/me/+page.server.ts
import { loadQuery } from "@tythe/svelte/server";
import { api } from "$lib/tythe/client";

export const load = async (event) => ({
  me: await loadQuery(api, "me", undefined, event),
});
```

```svelte
<!-- src/routes/me/+page.svelte -->
<script lang="ts">
  let { data } = $props();
</script>

<h1>Hello, {data.me.name}</h1>
```

The load function runs on the server, forwards cookies/auth from the
SvelteKit `event.request` to the Python handler, and SvelteKit serializes
the result into the rendered HTML — no client refetch.

## Solid Start

```tsx
// src/routes/me.tsx
import { createAsync } from "@solidjs/router";
import { getRequestEvent } from "solid-js/web";
import { serverQuery } from "@tythe/solid/server";

import { api } from "~/lib/tythe/client";

const fetchMe = async () => {
  "use server";
  const event = getRequestEvent();
  if (!event) throw new Error("server-only");
  return serverQuery(api, "me", undefined, event.request);
};

export default function Me() {
  const me = createAsync(() => fetchMe());
  return <h1>Hello, {me()?.name}</h1>;
}
```

## What "SSR-safe" actually means here

These claims are pinned by tests (`tests/csr-safety.test.ts` in each
framework package):

- Importing any `@tythe/*` module under a Node environment with no
  `window` / `document` / `localStorage` does not throw.
- The server entry points (`@tythe/react/server`, `@tythe/svelte/server`,
  `@tythe/solid/server`) do not transitively reach for DOM globals at
  import or at call time.
- `forwardHeaders` accepts both a bare `Headers` and any
  `{ headers: Headers }` shape, so it composes with Next.js
  `headers()`, SvelteKit `event.request`, SolidStart `event.request`,
  and any plain `Request`.

## What we don't do

- **No magic `useTythe.useSuspenseQuery`.** If you want suspense, use
  `useQuery({ suspense: true })` (TanStack) or `createAsync` (Solid)
  on top of the existing hook — the SSR prefetch already populates the
  cache so suspense resolves synchronously.
- **No server-action wrappers.** A Next.js server action or a SvelteKit
  form action is just a function — call `api.foo({ ... })` directly. The
  generated client works the same way on the server as on the browser.
- **No custom transport for streaming SSR.** Streaming endpoints
  (`stream[T]`) are inherently client-side over SSE. If your initial
  render needs the first frame of a stream, fetch it as a unary call
  first; otherwise leave streaming to the client.
