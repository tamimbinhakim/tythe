# tythe (Python)

> A type-safe RPC bridge between Python and TypeScript.

```bash
uv add tythe
```

This is the Python half of [Tythe](https://github.com/tamimbinhakim/tythe). It
ships:

- A thin ASGI framework (`tythe.App`) that uses your function signatures
  as the contract — no separate Pydantic models declared above the
  handler.
- A type extractor that walks `inspect.signature` +
  `typing.get_type_hints`, normalizes through `msgspec`'s native JSON
  Schema export, and produces a canonical IR.
- A codegen that turns the IR into a single `client.ts` for your
  frontend.
- A CLI (`tythe dev`, `tythe build`, `tythe codegen`, `tythe init`) that
  runs the whole loop in one process.

For the full story, the design rationale, and a side-by-side comparison
vs. FastAPI + openapi-typescript / tRPC / Encore.ts / Connect-RPC, see
the [repo README](https://github.com/tamimbinhakim/tythe).

## 30-second example

```python
from tythe import App, stream, raises
from dataclasses import dataclass
import msgspec

app = App()

class CreatePost(msgspec.Struct):
    title: str
    body: str

class Post(msgspec.Struct):
    id: int
    title: str
    body: str

@dataclass
class PostNotFound(Exception):
    post_id: int

@app.post("/posts")
async def create_post(data: CreatePost) -> Post: ...

@app.get("/posts/{post_id}")
@raises(PostNotFound)
async def get_post(post_id: int) -> Post: ...

class Tick(msgspec.Struct, tag="tick"):
    seq: int

@app.get("/ticks")
async def ticks(count: int) -> stream[Tick]:
    for i in range(count):
        yield Tick(seq=i)
```

Run it:

```bash
tythe dev server.app:app
```

The watcher writes `frontend/src/lib/tythe/client.ts` automatically. Then
in your frontend:

```ts
import { api } from "@/lib/tythe/client";

const post = await api.create_post({ title: "hi", body: "world" });

for await (const ev of api.ticks({ count: 10 })) {
  /* typed */
}
```

## Scope

Tythe ships at the fundamental level: RPC, typed streaming, typed
errors, cancellation, file uploads, dependency injection. It does
**not** ship vertical integrations — no LLM types, no React hooks in
core, no chat-bot primitives. Those layers compose on top of the
fundamentals and live in their own packages.

## License

MIT
