# Example · Vite + React CRUD

A boring-on-purpose CRUD example. Show typed inputs, typed outputs, typed
errors, and the dev loop — without any AI distractions.

> **Status:** scaffold only. Coming with v0.1.

## What this will look like

### Server

```python
# server/app.py
from dataclasses import dataclass
from tythe import App, raises
import msgspec

app = App()

class Post(msgspec.Struct):
    id: int
    title: str
    body: str

class CreatePost(msgspec.Struct):
    title: str
    body: str

@dataclass
class PostNotFound(Exception):
    post_id: int

POSTS: dict[int, Post] = {}

@app.get("/posts")
async def list_posts() -> list[Post]:
    return list(POSTS.values())

@app.get("/posts/{post_id}")
@raises(PostNotFound)
async def get_post(post_id: int) -> Post:
    if post_id not in POSTS:
        raise PostNotFound(post_id=post_id)
    return POSTS[post_id]

@app.post("/posts")
async def create_post(data: CreatePost) -> Post:
    post = Post(id=len(POSTS) + 1, title=data.title, body=data.body)
    POSTS[post.id] = post
    return post
```

### Frontend

```tsx
// frontend/src/App.tsx
import { api } from "./lib/tythe/client";
import { useEffect, useState } from "react";

export default function App() {
  const [posts, setPosts] = useState<
    Awaited<ReturnType<typeof api.list_posts>>
  >([]);

  useEffect(() => {
    api.list_posts().then(setPosts);
  }, []);

  async function load(id: number) {
    const result = await api.get_post({ post_id: id });
    if (result.ok) {
      console.log(result.data.title);
    } else if (result.error.kind === "PostNotFound") {
      alert(`No post with id ${result.error.post_id}`);
    }
  }

  return <pre>{JSON.stringify(posts, null, 2)}</pre>;
}
```

## How to run (once the scaffold lands)

```bash
# Terminal 1 — server
cd examples/vite-react/server
uv sync
uv run tythe dev app:app --out ../frontend/src/lib/tythe/client.ts

# Terminal 2 — frontend
cd examples/vite-react/frontend
pnpm install
pnpm dev
```

## What this example demonstrates

- Path params (`{post_id}`) typed correctly on the TS side
- Inline `msgspec.Struct` for request/response shapes
- `@raises(PostNotFound)` → `Result<Post, PostNotFound>` on the client
- No AI, no streaming — just the boring foundation working cleanly
