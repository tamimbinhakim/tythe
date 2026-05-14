# @dyadpy/svelte

Svelte 5 store bindings for [Dyadpy](https://github.com/tamimbinhakim/dyadpy)-generated
clients. Three factory functions on top of the typed `api`:

| Store          | What it does                                                               |
| -------------- | -------------------------------------------------------------------------- |
| `query`        | Fires a unary call when subscribed; tracks `status`/`data`/`error`.        |
| `mutation`     | Returns a `mutate(args)` you call imperatively.                            |
| `subscription` | Subscribes to a `stream[T]` endpoint; events forwarded to an `onEvent` cb. |

## Install

```bash
pnpm add @dyadpy/svelte@alpha @dyadpy/ts@alpha svelte
# alpha channel — drop `@alpha` once v0.1.0 ships
```

## Use

```svelte
<script lang="ts">
  import { createDyadpyStores } from "@dyadpy/svelte";
  import { api } from "$lib/dyadpy/client";

  const stores = createDyadpyStores(api);
  const issue = stores.query("getIssue", { issueId: 1 });
</script>

{#if $issue.status === "loading"}
  Loading…
{:else if $issue.status === "success"}
  {$issue.data.title}
{:else if $issue.status === "error"}
  Failed: {$issue.error.kind}
{/if}
```

For a `@raises(...)` route the `error` slot is the typed discriminated union
from Python; for a route without `@raises`, it's a thrown `Error`.

## License

MIT
