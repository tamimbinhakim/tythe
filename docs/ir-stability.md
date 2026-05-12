# IR stability policy

Tythe's intermediate representation (`tythe.ir.AppIR`) is the contract
between server and client. Anything that reads the IR — the TS codegen,
the OpenAPI exporter, the polyglot Swift / Kotlin renderers, `tythe diff`,
and any third-party tool — relies on its shape.

**As of v1.0**, the IR's shape is committed. This document spells out
what that commitment means.

## What's covered

- **`AppIR`, `RouteIR`, `ParamIR`, `ErrorIR`** dataclass fields (names,
  meanings, types).
- **The JSON snapshot format** emitted by `tythe ir <module:attr>`.
- **The wire format** between Tythe servers and clients: JSON envelope,
  SSE frame shape, snake_case ↔ camelCase translation rule.

## Compatibility rules

| Change                                            | Allowed in         | Notes                                          |
| ------------------------------------------------- | ------------------ | ---------------------------------------------- |
| Add a new optional field to `RouteIR` / `ParamIR` | Any minor release  | New consumers see it, old consumers ignore it. |
| Add a new optional flag (e.g. `binary_body`)      | Any minor release  | Default must preserve previous behavior.       |
| Add a new top-level dataclass                     | Any minor release  |                                                |
| Add a new enum value to `ParamLocation` etc.      | Major release only | Existing exhaustive switches break otherwise.  |
| Rename a field                                    | Major release only | After one full minor of deprecation.           |
| Remove a field                                    | Major release only | After one full minor of deprecation.           |
| Change a field type (narrow)                      | Major release only |                                                |
| Change a field type (widen)                       | Minor release      | Must be a strict superset.                     |
| Reorder fields                                    | Free               | Field order is not part of the contract.       |

## Wire-format invariants

These are frozen:

- **JSON body keys** are snake_case on the wire. The TS client translates
  to camelCase before handing to user code; the Python server reads
  snake_case directly.
- **`Result` envelope** is `{"ok": true, "data": T}` or `{"ok": false,
"error": E}`. Routes without `@raises(...)` return `T` directly.
- **SSE frame format** matches the W3C SSE spec:
  - `data: <json>\n\n` for plain events
  - `id: <string>\n` (optional) for resume cursor
  - `retry: <ms>\n` (optional) for backoff hint
  - `event: done\ndata: {}\n\n` to terminate
  - `event: error\ndata: <error-payload>\n\n` for typed `@raises` errors
- **Multipart and form-urlencoded** bodies decode through `request.form()`
  with field names matching the wire alias.
- **Bytes** routes serialize as `application/octet-stream` by default;
  Content-Type is overridable via `ctx.set_header`.

## Deprecation cycle

When a field, primitive, or wire-format detail is going away:

1. **Announce.** Marked `deprecated` in CHANGELOG; warning emitted at
   import time or on first use.
2. **Hold for one full minor release.** During this window, both old
   and new APIs work; old emits a `DeprecationWarning`.
3. **Remove in the next major.**

Example: removing a hypothetical `RouteIR.legacy_flag` field.

- v1.5: field marked deprecated; using it emits a warning.
- v1.6: still works, still warns.
- v2.0: removed.

`tythe diff` flags additions / removals at the IR level so accidental
breakages can't slip through.

## Compatibility tests

The CI suite includes IR snapshot tests: for each minor release we
freeze a representative `tythe-ir.json` and assert future versions can
either consume it directly or produce a backward-compatible diff. The
files live in `packages/tythe/tests/golden/` (added in v0.2).
