# Contributing to Tythe

First: thank you. Genuinely. Open source moves at the speed of the people who
show up, and you showing up means a lot.

This guide will get you from "I cloned the repo" to "my PR is merged" with as
little friction as possible. If something here is wrong, unclear, or just
annoying, open a PR fixing it — meta-contributions count.

## TL;DR

```bash
git clone https://github.com/tamimbinhakim/tythe.git
cd tythe
pnpm install               # installs Node deps + sets up husky hooks
uv sync                    # installs Python deps into .venv
pnpm test                  # run everything
```

You're set up. Make a branch, make a change, write a Conventional Commit, push.

## What this repo is

A pnpm monorepo with two real packages and a pile of supporting docs/examples:

```
tythe/
├── packages/
│   ├── tythe/          # Python framework (PyPI: tythe)
│   └── tythe-ts/   # TS runtime (npm: @tythe/ts)
├── examples/           # Runnable apps you can poke
├── docs/               # End-user documentation
└── .github/            # CI, issue templates, the works
```

Both packages release together — see [release process](#releases) below.

## Prereqs

| Tool   | Version          | Why                                                                                  |
| ------ | ---------------- | ------------------------------------------------------------------------------------ |
| Node   | ≥ 20             | Runs the toolchain (pnpm, husky, commitlint, oxlint, oxfmt).                         |
| pnpm   | ≥ 9              | Workspace package manager. Don't use npm/yarn here.                                  |
| Python | ≥ 3.11           | Tythe leans on modern typing (`from __future__ import annotations`, `X \| Y`, etc.). |
| uv     | latest           | Python package manager. Way faster than pip.                                         |
| Git    | any sane version | Obvious.                                                                             |

> If you're on macOS, `brew install node pnpm uv python@3.12` covers it.

## First-time setup

```bash
pnpm install        # Node deps + husky hooks via the `prepare` script
uv sync             # Creates .venv and installs Python deps for all workspaces
```

That's it. There is no third step.

To verify:

```bash
pnpm lint           # oxlint + ruff
pnpm format         # oxfmt (TS/JS) + ruff (Python) + prettier (md/json/yaml)
pnpm typecheck      # tsc --noEmit + mypy
pnpm test           # vitest + pytest
```

> Formatter split: **oxfmt** handles `*.ts`/`*.tsx`/`*.js`/etc.,
> **ruff** handles Python, **prettier** handles `*.md`/`*.json`/`*.yaml`.
> Each tool owns its filetypes; nothing fights anything.

If all four are green on a fresh clone, you're good. If they aren't, that's a
bug — open an issue.

## Day-to-day

### Branches

Branch off `main`. Use whatever naming you like, but a hint:

```
feat/streaming-cancellation
fix/codegen-tagged-union
docs/getting-started-typo
chore/bump-msgspec
```

### Commits

We use [Conventional Commits](https://www.conventionalcommits.org/). The
`commit-msg` hook will reject anything that doesn't match. Examples:

```
feat(codegen): emit AbortSignal as second arg
fix(ir): handle Annotated[T, Body()] on optional params
docs: clarify streaming error semantics
chore(deps): bump msgspec to 0.18.7
```

Scopes are optional but appreciated. Common ones: `codegen`, `ir`, `cli`,
`client`, `docs`, `ci`, `deps`.

If you're touching one package only, prefer that package as the scope
(`feat(tythe): ...`, `fix(client): ...`).

### Pre-commit

`pnpm install` wires up:

- **commit-msg** → commitlint validates your message
- **pre-commit** → lint-staged runs oxlint/oxfmt on staged TS files and
  ruff on staged Python files

If the hook fails, fix the issue and re-stage. Don't bypass with
`--no-verify` unless you have a really good reason.

## Working on the Python package

```bash
cd packages/tythe
uv run pytest                  # full test suite
uv run pytest -k streaming     # one test
uv run ruff check .            # lint
uv run ruff format .           # format
uv run mypy src                # type-check
```

The package layout:

```
packages/tythe/
├── src/tythe/
│   ├── __init__.py     # public API re-exports
│   ├── app.py          # App, route decorators
│   ├── context.py      # request Context, Depends
│   ├── ir.py           # type extraction → IR
│   ├── codegen.py      # IR → client.ts
│   ├── streaming.py    # SSE encoder, stream[T]
│   ├── errors.py       # @raises, Result envelope
│   └── cli.py          # tythe dev / build / codegen / init
└── tests/
```

When adding a new public symbol, re-export it from `tythe/__init__.py`.

## Working on the TS client

```bash
cd packages/tythe-ts
pnpm test                      # vitest
pnpm test --watch              # watch mode
pnpm build                     # tsup → dist/
pnpm typecheck                 # tsc --noEmit
```

Hard constraints on this package:

- **Zero runtime dependencies.** If you find yourself reaching for one, talk
  to me first.
- **Tree-shakable.** Every entry point ESM-first.
- **< ~3 KB min+gz.** We check bundle size in CI.

## Working on examples

```bash
cd examples/nextjs-streaming
pnpm install
pnpm dev
```

Each example is self-contained. They are not part of the publish pipeline —
they exist to demo features and catch regressions in real-world setups.

## Tests

We don't enforce a coverage number, but we do enforce that:

- Every bug fix adds a regression test.
- Every new public API has at least one test.
- The streaming, codegen, and IR modules in particular should have generous
  tests — they are the load-bearing parts.

## Documentation

If you change behavior, update the relevant page in [`docs/`](./docs).
If you change a public API, update the docstring **and** the docs page.
If your change is interesting, write a paragraph about _why_ — future-you
will thank you.

## Releases

Releases are automated via [release-please](https://github.com/googleapis/release-please).

- Every merge to `main` updates a release PR.
- Merging that release PR cuts versions, generates changelogs, tags, and
  publishes both `tythe` (PyPI) and `@tythe/ts` (npm).
- Versioning is driven by Conventional Commits: `feat:` → minor, `fix:` →
  patch, `feat!:` / `BREAKING CHANGE:` → major.

You don't manually bump versions. Don't manually edit `CHANGELOG.md` either —
release-please owns it.

## Filing issues

Use the issue templates. They exist to save you time, not to gatekeep.

If you've found a bug:

1. **A minimal reproduction beats everything.** A 20-line script that fails
   is worth more than a 500-word description.
2. Tell us the version (`tythe --version`), Python version, and Node version.
3. If it's a codegen issue, paste both the Python handler and the generated
   TS output.

## Asking questions

Discussions for "how do I…?" and design questions.
Issues for "I think this is broken."

There is no Discord (yet). Sorry.

## Code of Conduct

Be kind. Disagree with ideas, not people. Read the
[full Code of Conduct](./CODE_OF_CONDUCT.md). Violators get one warning, then
they're out.

## Thanks

Seriously. Thanks for reading this. Now go break something.
