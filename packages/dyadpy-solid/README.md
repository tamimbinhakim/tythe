# @dyadpy/solid

SolidJS resource bindings for [Dyadpy](https://github.com/tamimbinhakim/dyadpy)-generated
clients. Three factory functions on top of the typed `api`:

| Resource       | What it does                                                               |
| -------------- | -------------------------------------------------------------------------- |
| `query`        | `createResource`-backed unary call; reactive on the args accessor.         |
| `mutation`     | Imperative `mutate(args)` with `data`/`error`/`loading` signals.           |
| `subscription` | Subscribes to a `stream[T]` endpoint; events forwarded to an `onEvent` cb. |

## Install

```bash
pnpm add @dyadpy/solid@alpha @dyadpy/ts@alpha solid-js
# alpha channel — drop `@alpha` once v0.1.0 ships
```

## Use

```tsx
import { createDyadpyResources } from "@dyadpy/solid";
import { api } from "./lib/dyadpy/client";

const resources = createDyadpyResources(api);
const [issue] = resources.query("getIssue", () => ({ issueId: 1 }));

export default function Issue() {
  return (
    <Show when={issue()} fallback={<p>Loading…</p>}>
      <h1>{issue()!.title}</h1>
    </Show>
  );
}
```

For a `@raises(...)` route the `error` accessor on the query carries the
typed discriminated union.

## License

MIT
