# Getting started

Five minutes from clone to a typed Python ↔ TypeScript call.

## Requirements

| Tool   | Version | Why                                          |
| ------ | ------- | -------------------------------------------- |
| Python | ≥ 3.11  | Tythe uses modern type-hint syntax.          |
| Node   | ≥ 20    | For your frontend toolchain.                 |
| `uv`   | latest  | Python package manager. `brew install uv`.   |
| `pnpm` | ≥ 9     | Or `npm` / `yarn`, but pnpm is what I'd use. |

## 1. Install

```bash
# In your Python project
uv add tythe

# In your frontend project
pnpm add @tythe/ts
```

## 2. Write a handler

```python
# server/app.py
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

The handler signature is the API contract. No `class PostRequest(BaseModel)` in another file.

## 3. Run dev

```bash
tythe dev server.app:app --out ../frontend/src/lib/tythe/client.ts
```

- Uvicorn starts on `http://127.0.0.1:8000`.
- Tythe watches `*.py` and rewrites the generated `client.ts` atomically on save.

For a one-shot codegen (no server, no watcher):

```bash
tythe codegen server.app:app --out ../frontend/src/lib/tythe/client.ts
```

## 4. Call it

```ts
// frontend/src/app/page.tsx
import { api } from "@/lib/tythe/client";

const post = await api.createPost({ data: { title: "first", body: "hello" } });
//    ^? Post

const got = await api.getPost({ postId: post.id });
console.log(got.title);
```

Hover `api.createPost` in your editor. Return type: `Post`. Param type: `CreatePost`. Pass `{ title: 123 }` and TypeScript yells at you before you hit save.

## 5. Streaming

`stream[T]` return → SSE on the wire → `AsyncIterable<T>` on the client.

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

```ts
const ac = new AbortController();
for await (const ev of api.ticks({ count: 10 }, { signal: ac.signal })) {
  if (ev.kind === "tick") console.log("tick", ev.seq);
  else if (ev.kind === "done") console.log("finished", ev.total);
}
```

Cancellation: pass an `AbortSignal`. The server sees the disconnect via `request.is_disconnected()`. Drops are auto-reconnected on the client with `Last-Event-Id`.

## 6. Typed errors

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

```ts
const result = await api.getPost({ postId: 42 });
if (result.ok) {
  console.log(result.data.title);
} else if (result.error.kind === "PostNotFound") {
  toast(`No post with id ${result.error.postId}`);
}
```

TypeScript forces you to handle each declared error case before reaching `result.data`.

## 7. Other primitives you'll reach for

Each has a one-liner here and a full example in [reference](./reference.md).

### Raw bodies — `Bytes`

```python
from tythe import Bytes

@app.post("/webhooks/stripe")
async def stripe(body: Bytes, sig: Annotated[str, Header("stripe-signature")]) -> None:
    verify(body, sig)

@app.get("/exports/{id}.csv")
async def csv(id: str) -> Bytes:
    return render_csv(id)
```

TS: `Blob | Uint8Array | ArrayBuffer` in, `Blob` out.

### Form bodies

```python
from tythe import Form

class LoginForm(msgspec.Struct):
    email: str
    password: str

@app.post("/login")
async def login(form: Annotated[LoginForm, Form()]) -> Session: ...
```

Wire: `application/x-www-form-urlencoded` (or multipart with files).

### Response control — `Context`

```python
from tythe import Context

@app.post("/issues")
async def create(data: CreateIssue, ctx: Context) -> Issue:
    issue = save(data)
    ctx.set_status(201)
    ctx.set_header("location", f"/issues/{issue.id}")
    ctx.set_cookie("session", token, max_age=86400, http_only=True, secure=True)
    return issue
```

### Post-response hooks — `after()`

```python
from tythe import after

@app.post("/posts")
async def create_post(data: CreatePost) -> Post:
    post = save(data)
    after(notify_webhook, post.id)
    return post
```

Runs after the response is sent. Errors swallowed (response is gone). Sync + async both supported.

### List query params

```python
@app.get("/issues")
async def list_issues(
    tag: Annotated[list[str], Query()] = None,
) -> Page: ...
```

`?tag=bug&tag=ui` → `["bug", "ui"]`. The TS client expands array args back into repeated keys.

## 8. SSR (Next.js / SvelteKit / Solid Start)

Prefetch on the server, hydrate on the client — first paint with no waterfall.

```tsx
// Next.js App Router server component
import { prefetchQuery } from "@tythe/react/server";

const qc = new QueryClient();
await prefetchQuery(qc, api, "getUser", { userId: 1 });
return <HydrationBoundary state={dehydrate(qc)}>{...}</HydrationBoundary>;
```

Full SSR guide: [`docs/ssr.md`](./ssr.md).

## Where to go next

- [Reference](./reference.md) — every primitive in one page.
- [SSR](./ssr.md) — Next.js / SvelteKit / Solid Start prefetch helpers.
- [Auth recipes](./auth.md) — JWT, sessions, NextAuth.
- [Architecture](./architecture.md) — what's happening under the hood (for contributors).
- [`examples/`](../examples) — runnable starter projects.

## Troubleshooting

**The watcher says "no `App` found".**
`tythe dev` takes `module:attr`, not a path. Make sure `server/app.py` defines `app = App()` and the working directory is the Python project root.

**My TS types are `any`.**
You're missing `@tythe/ts`, or your editor hasn't picked up the generated `client.ts`. Restart the TypeScript server.

**Streaming doesn't cancel server-side.**
Your handler needs to periodically `await` (or check `request.is_disconnected()`). A tight CPU loop will keep running until the next await.
