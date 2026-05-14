# dyadpy (Python)

> A type-safe RPC bridge between Python and TypeScript.

```bash
uv add 'dyadpy==0.1.0a0'   # alpha — drop the pin once v0.1.0 ships
```

This is the Python half of [Dyadpy](https://github.com/tamimbinhakim/dyadpy). It
ships:

- A thin ASGI framework (`dyadpy.App`) that uses your function signatures
  as the contract — no separate Pydantic models declared above the
  handler.
- A type extractor that walks `inspect.signature` +
  `typing.get_type_hints`, normalizes through `msgspec`'s native JSON
  Schema export, and produces a canonical IR.
- A codegen that turns the IR into a single `client.ts` for your
  frontend.
- A CLI (`dyadpy dev`, `dyadpy build`, `dyadpy codegen`, `dyadpy init`) that
  runs the whole loop in one process.

For the full story, the design rationale, and a side-by-side comparison
vs. FastAPI + openapi-typescript / tRPC / Encore.ts / Connect-RPC, see
the [repo README](https://github.com/tamimbinhakim/dyadpy).

## 30-second example

```python
from dyadpy import App, stream, raises
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
dyadpy dev server.app:app
```

The watcher writes `frontend/src/lib/dyadpy/client.ts` automatically. Then
in your frontend:

```ts
import { api } from "@/lib/dyadpy/client";

const post = await api.createPost({ data: { title: "hi", body: "world" } });

for await (const ev of api.ticks({ count: 10 })) {
  /* typed */
}
```

## Primitives in this package

| Primitive                                                           | Purpose                                                     |
| ------------------------------------------------------------------- | ----------------------------------------------------------- |
| `App` + `@app.{get,post,put,patch,delete}`                          | Route decorators.                                           |
| `Annotated[T, Body / Query / Path / Header / Cookie / File / Form]` | Parameter location markers.                                 |
| `Annotated[list[T], Query()]`                                       | Repeated query params (`?tag=a&tag=b`).                     |
| `Bytes`                                                             | Raw request / response bodies. Skips the JSON envelope.     |
| `stream[T]`                                                         | Typed SSE — client gets `AsyncIterable<T>`.                 |
| `@raises(E1, E2, …)`                                                | Typed error union → `Result<T, E1 \| E2>` on the TS side.   |
| `Context.set_status / set_header / set_cookie / after`              | Shape the response without dropping to Starlette.           |
| `Depends(provider)`                                                 | DI in the FastAPI shape.                                    |
| `after(fn, …)`                                                      | Run a callback after the response is sent.                  |
| `InMemoryBackend` + `TaskBackend` Protocol                          | Background jobs.                                            |
| `dyadpy.otel.instrument(app)`                                       | One OpenTelemetry span per request (`dyadpy[otel]`).        |
| `dyadpy openapi / swift / kotlin` (CLI)                             | Emit OpenAPI 3.1, Swift, or Kotlin clients off the same IR. |

Full reference: <https://github.com/tamimbinhakim/dyadpy/blob/main/docs/reference.md>

## Optional extras

```bash
uv add 'dyadpy[pydantic]'  # Pydantic plugin (model_validate + model_json_schema)
uv add 'dyadpy[otel]'      # OpenTelemetry middleware
uv add 'dyadpy[all]'       # everything
```

## Scope

Dyadpy ships at the wire level: RPC, typed streaming, typed errors,
cancellation, file uploads, dependency injection. It does **not** ship
vertical integrations — no LLM types, no React hooks in core, no
chat-bot primitives. Those layers compose on top of the fundamentals
and live in their own packages.

## License

MIT
