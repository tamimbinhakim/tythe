# Example · Next.js typed streaming

A streaming demo built on Tythe's fundamentals: typed events over SSE,
discriminated-union narrowing on the client, cancellation via
`AbortSignal`. No third-party services, no API keys, runs on a single
machine.

The scenario is a "long-running job" that emits progress updates and
then a final result — the same wire shape that fits a build-progress UI,
a deploy log tailer, a notifications feed, or any other "server pushes
typed events to client" use case.

> **Status:** scaffold only. The actual `server/` and `frontend/` apps
> are coming with the v0.1 release.

## What this will look like

### Server (~25 lines)

```python
# server/app.py
import asyncio
import msgspec
from tythe import App, stream

app = App()

class Progress(msgspec.Struct, tag="progress"):
    step: int
    total: int
    label: str

class Log(msgspec.Struct, tag="log"):
    line: str

class Done(msgspec.Struct, tag="done"):
    summary: str

@app.get("/jobs/{job_id}/events")
async def watch_job(job_id: str) -> stream[Progress | Log | Done]:
    total = 5
    for i in range(total):
        yield Progress(step=i + 1, total=total, label=f"phase {i}")
        await asyncio.sleep(0.4)
        yield Log(line=f"[{job_id}] processed batch {i}")
    yield Done(summary=f"job {job_id} finished")
```

### Frontend (~25 lines)

```tsx
// frontend/app/jobs/[id]/page.tsx
"use client";
import { api } from "@/lib/tythe/client";
import { useEffect, useState } from "react";

export default function JobPage({ params }: { params: { id: string } }) {
  const [pct, setPct] = useState(0);
  const [lines, setLines] = useState<string[]>([]);
  const [done, setDone] = useState<string | null>(null);

  useEffect(() => {
    const ac = new AbortController();
    (async () => {
      for await (const ev of api.watch_job(
        { job_id: params.id },
        { signal: ac.signal },
      )) {
        if (ev.kind === "progress") setPct((ev.step / ev.total) * 100);
        else if (ev.kind === "log") setLines((l) => [...l, ev.line]);
        else if (ev.kind === "done") setDone(ev.summary);
      }
    })();
    return () => ac.abort();
  }, [params.id]);

  return (
    <main>
      <progress value={pct} max={100} />
      <pre>{lines.join("\n")}</pre>
      {done && <p>{done}</p>}
    </main>
  );
}
```

## How to run (once the scaffold lands)

```bash
# Terminal 1 — server
cd examples/nextjs-streaming/server
uv sync
uv run tythe dev app:app --out ../frontend/src/lib/tythe/client.ts

# Terminal 2 — frontend
cd examples/nextjs-streaming/frontend
pnpm install
pnpm dev
```

Open <http://localhost:3000/jobs/demo>. Watch the progress bar fill,
the log lines append, and the summary appear when the job finishes.

## What this example demonstrates

- `stream[Progress | Log | Done]` — tagged-union streaming responses
- Auto-narrowing on the TS side via the `kind` discriminant
- AbortSignal-based cancellation on unmount (try navigating away
  mid-stream)
- The watcher loop: edit `app.py`, see `client.ts` update on save
- No external services required to understand the wire protocol

> The same wire shape carries LLM token streams, pubsub feeds, log
> tails, partial responses — anything where the server pushes typed
> events to the client. Tythe doesn't care what's inside the events.
