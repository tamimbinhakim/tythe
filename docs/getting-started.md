# Getting started

This is the 5-minute version. Real depth lives in
[architecture](./architecture.md) and [design](./design.md). For now:
install, write a handler, watch a typed TS client appear, call it from
your frontend, ship something.

## What you need

| Tool   | Version | Why                                          |
| ------ | ------- | -------------------------------------------- |
| Python | ≥ 3.11  | Tythe uses modern type-hint syntax.          |
| Node   | ≥ 20    | For your frontend toolchain.                 |
| `uv`   | latest  | Python package manager. `brew install uv`.   |
| `pnpm` | ≥ 9     | Or `npm` / `yarn`, but pnpm is what I'd use. |

## 1. Install

In your Python project:

```bash
uv add tythe
```

In your frontend project (Next.js, Vite, SvelteKit, whatever):

```bash
pnpm add @tythe/ts
```

> The two halves talk through a generated `client.ts` file — neither
> one needs to know where the other lives until you tell the CLI.

## 2. Write your first handler

Create `server/app.py`:

```python
from tythe import App
import msgspec

app = App()

class CreatePost(msgspec.Struct):
    title: str
    body: str

class Post(msgspec.Struct):
    id: int
    title: str
    body: str

POSTS: dict[int, Post] = {}

@app.get("/posts/{post_id}")
async def get_post(post_id: int) -> Post:
    return POSTS[post_id]

@app.post("/posts")
async def create_post(data: CreatePost) -> Post:
    post = Post(id=len(POSTS) + 1, title=data.title, body=data.body)
    POSTS[post.id] = post
    return post
```

That's the whole API contract. No `class PostRequest(BaseModel)`
declared in another file. The handler parameters are the request
shape; the return annotation is the response shape.

## 3. Run the dev loop

```bash
tythe dev server.app:app --out ../frontend/src/lib/tythe/client.ts
```

What just happened:

1. Uvicorn started on `http://127.0.0.1:8000`.
2. The watcher scanned `server/app.py`, found your `App`, and wrote a
   typed `client.ts` to the path you passed.
3. Any time you save a `.py` file, the watcher reruns extraction and
   rewrites `client.ts` atomically.

You can also do a one-shot:

```bash
tythe codegen server.app:app --out ../frontend/src/lib/tythe/client.ts
```

## 4. Call it from your frontend

```ts
// frontend/src/app/page.tsx
import { api } from "@/lib/tythe/client";

const post = await api.createPost({ data: { title: "first", body: "hello" } });
//    ^? Post

const got = await api.getPost({ postId: post.id });
console.log(got.title);
```

Open your editor. Hover over `api.createPost`. The return type is
`Post`. The parameter type is `CreatePost`. If you pass
`{ title: 123 }`, TypeScript yells at you before you save.

That's the whole loop.

## 5. Stream typed events

Any handler whose return annotation is `stream[T]` becomes a
server-sent-events endpoint. You yield instances of `T` (or a
discriminated union of `T`s); the generated client gives you a typed
`AsyncIterable` back.

```python
from tythe import stream
import msgspec, asyncio

class Tick(msgspec.Struct, tag="tick"):
    seq: int
    ts: float

class Done(msgspec.Struct, tag="done"):
    total: int

@app.get("/ticks")
async def ticks(count: int) -> stream[Tick | Done]:
    for i in range(count):
        await asyncio.sleep(0.5)
        yield Tick(seq=i, ts=asyncio.get_event_loop().time())
    yield Done(total=count)
```

On the frontend:

```ts
const ac = new AbortController();
for await (const ev of api.ticks({ count: 10 }, { signal: ac.signal })) {
  if (ev.kind === "tick") console.log("tick", ev.seq);
  else if (ev.kind === "done") console.log("finished", ev.total);
}
```

Cancellation? Pass the `AbortSignal`. The server sees the disconnect
via `request.is_disconnected()` and stops the work.

> The same primitive works for anything that pushes typed events:
> progress streams, log tailing, pubsub, partial responses, LLM token
> streams. Tythe doesn't care what's inside the events — it just
> carries them with the types intact.

## 6. Typed errors

Declare which errors a handler can raise:

```python
from dataclasses import dataclass
from tythe import raises

@dataclass
class PostNotFound(Exception):
    post_id: int

@app.get("/posts/{post_id}")
@raises(PostNotFound)
async def get_post(post_id: int) -> Post:
    if post_id not in POSTS:
        raise PostNotFound(post_id=post_id)
    return POSTS[post_id]
```

On the TS side you get a `Result<Post, PostNotFound>` shape —
TypeScript forces you to handle the typed error in a way it can check:

```ts
const result = await api.getPost({ postId: 42 });
if (result.ok) {
  console.log(result.data.title);
} else if (result.error.kind === "PostNotFound") {
  toast(`No post with id ${result.error.postId}`);
}
```

## Where to go next

- [Architecture](./architecture.md) — what's actually happening under
  the hood.
- [Design](./design.md) — why msgspec, why SSE, why no OpenAPI by
  default, why no vertical integrations in core.
- [`examples/`](../examples) — runnable starter projects.

## Troubleshooting

**The watcher says "no `App` found".**
The argument to `tythe dev` is `module:attr`, not a path. Make sure
`server/app.py` defines `app = App()` and that the working directory
is the Python project root (so `server.app` is importable).

**My TS types are `any`.**
Either you're missing `@tythe/ts`, or your editor hasn't picked up
the generated `client.ts`. Restart the TypeScript server in your
editor.

**Streaming doesn't cancel server-side.**
Make sure your handler periodically checks
`request.is_disconnected()` (or yields control via `await`). A tight
CPU loop will keep running until the next await point.
