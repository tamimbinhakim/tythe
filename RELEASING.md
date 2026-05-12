# Releasing Tythe

A maintainer-facing checklist. Everything in here must be true before
`tythe-v0.1.0` (PyPI) or `@tythe/*-v0.1.0` (npm) gets published. Run top
to bottom, tick boxes as you go.

> Tythe is a **monorepo with 5 publishable packages**:
>
> - `tythe` — PyPI
> - `@tythe/ts` — npm (public)
> - `@tythe/react` — npm (public)
> - `@tythe/svelte` — npm (public)
> - `@tythe/solid` — npm (public)
>
> Tags follow `release-please-config.json`: `<component>-vX.Y.Z`.

---

## 1. Code gates (must all pass locally on `main`)

```bash
# Python
cd packages/tythe
uv sync --all-extras --dev
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run --with pyright pyright src

# TypeScript
cd ../..
pnpm install --frozen-lockfile
pnpm -r --filter='./packages/*' build
pnpm -r --filter='./packages/*' test
pnpm -r --filter='./packages/*' typecheck
pnpm exec oxlint packages
pnpm exec oxfmt --ignore-path .oxfmtignore --check .
pnpm exec prettier --check "**/*.{md,json,yaml,yml}"
```

- [ ] Python: ruff lint, ruff format, mypy strict, pyright strict, pytest all green
- [ ] TS: oxlint 0/0, oxfmt clean, prettier clean, tsc clean, vitest green
- [ ] Build artifacts inspected (`uv build` wheel + sdist, `npm pack --dry-run` for each TS pkg)
- [ ] Generated client.ts in `examples/*` regenerated if codegen changed
- [ ] No `console.log` / `print(...)` debug statements in `packages/*/src`
- [ ] No `# TODO` / `# FIXME` left in publishable code paths

## 2. Package contents (per package)

For each publishable package, verify the tarball / wheel includes only
what should ship.

**Python (`packages/tythe`)**

```bash
cd packages/tythe
rm -rf dist
uv build
unzip -l dist/tythe-*-py3-none-any.whl
```

- [ ] `tythe/py.typed` is present (PEP 561 marker)
- [ ] All 12 modules included (`__init__`, `_idents`, `_pydantic`, `app`,
      `cli`, `codegen`, `context`, `errors`, `ir`, `openapi`, `otel`,
      `params`, `polyglot`, `runtime`, `streaming`, `tasks`)
- [ ] `METADATA` shows correct version, description, classifiers, license, optional extras
- [ ] `entry_points.txt` registers the `tythe` CLI script

**TypeScript (each of `tythe-ts`, `tythe-react`, `tythe-svelte`, `tythe-solid`)**

```bash
cd packages/<name>
pnpm build
npm pack --dry-run
```

Per package, confirm:

- [ ] `dist/` ships both ESM (`index.js`) and CJS (`index.cjs`) + maps + `.d.ts` + `.d.cts`
- [ ] `README.md` + `CHANGELOG.md` + `LICENSE` in tarball
- [ ] `package.json` `exports` covers `.` + `./package.json`
- [ ] No `node_modules`, no `tests/`, no `tsconfig*.json` leak
- [ ] Total unpacked size sane (< 50 KB for each — they're small by design)
- [ ] `peerDependencies` correct and `engines.node` set

## 3. Versions, changelogs, manifest

- [ ] `.release-please-manifest.json` reflects the version about to ship
      for every package
- [ ] `release-please-config.json` `extra-files` entries (e.g.
      `packages/tythe/src/tythe/__init__.py` `__version__`) match
- [ ] Each package's `CHANGELOG.md` has a real release section (not
      just `[Unreleased]`)
- [ ] `CHANGELOG.md` entries are user-facing (not commit-ese); breaking
      changes called out at the top of the section
- [ ] Root `CHANGELOG.md` links to per-package changelogs

## 4. Docs

- [ ] `README.md` quickstart copy-pastes without edits
- [ ] `docs/getting-started.md` walks end-to-end from clean install
- [ ] `docs/reference.md` matches actual exports (`__all__` in
      `packages/tythe/src/tythe/__init__.py` + `packages/tythe-ts/src/index.ts`)
- [ ] All package READMEs reference the right install commands
      (`uv add tythe`, `pnpm add @tythe/<name>`)
- [ ] `ROADMAP.md` reflects what shipped
- [ ] Badge URLs in `README.md` point at the correct workflows / registries
- [ ] No links go to `localhost`, `127.0.0.1`, or local file paths

## 5. CI / GitHub setup

- [ ] `.github/workflows/ci.yml` runs on the release commit and is green
- [ ] `.github/workflows/release.yml` exists and points at `release-please-config.json`
- [ ] `.github/workflows/codeql.yml` green on `main`
- [ ] Branch protection on `main`: require CI + 1 review, no force-push,
      no admin override
- [ ] Dependabot enabled, weekly cadence, security updates auto-merged

## 6. Registry / publish prerequisites

**PyPI**

- [ ] `tythe` project name not taken (check pypi.org/project/tythe/)
- [ ] PyPI Trusted Publisher configured for `tamimbinhakim/tythe`,
      `release.yml`, environment `pypi`
- [ ] No `PYPI_TOKEN` lying around in old workflows (we use OIDC)
- [ ] GitHub environment `pypi` exists with deployment protection on `main`

**npm**

- [ ] `@tythe` org claimed on npm
- [ ] `tamimbinhakim` is a member of `@tythe` with `publish` permission
- [ ] `NPM_TOKEN` (automation, 2FA-bypassing) added as repository secret
- [ ] `npm whoami` works locally if you need to debug

**Provenance**

- [ ] All TS `package.json` files have `"publishConfig": { "access": "public", "provenance": true }`
- [ ] PyPI publish step uses `pypa/gh-action-pypi-publish` (which signs)

## 7. Secrets present in the repo (Settings → Secrets and variables → Actions)

- [ ] `NPM_TOKEN` — for `npm publish` in `release.yml`
- [ ] `CODECOV_TOKEN` — for the codecov upload in `ci.yml` (optional but
      currently referenced)
- [ ] No leftover personal access tokens or stale API keys

## 8. Release notes draft

Drafted in GitHub Releases, **NOT** auto-published yet:

- [ ] One release per package (5 total): `tythe-v0.1.0`,
      `tythe-ts-v0.1.0`, `tythe-react-v0.1.0`, `tythe-svelte-v0.1.0`,
      `tythe-solid-v0.1.0`
- [ ] Each release links its CHANGELOG entry and lists install command
- [ ] Top-level "v0.1.0 — initial release" announcement post drafted
      separately if needed

## 9. Cold-machine smoke test

Run on a fresh checkout / fresh venv. If you can't do this in <10
minutes, the install path is broken.

```bash
# Server
mkdir /tmp/tythe-smoke && cd /tmp/tythe-smoke
uv init && uv add tythe
mkdir server && cat > server/app.py <<'EOF'
from tythe import App
app = App()
@app.get("/ping")
async def ping() -> dict[str, str]:
    return {"ok": "yes"}
EOF
uv run tythe dev server.app:app --out client.ts &
sleep 2

# Hit the live server
curl -s http://127.0.0.1:8000/ping
cat client.ts | head -20

# Cleanup
kill %1
```

- [ ] `uv add tythe` works
- [ ] `tythe dev` starts, writes a non-empty `client.ts`, server responds 200
- [ ] `pnpm add @tythe/ts` works in a fresh Node project
- [ ] The generated `client.ts` imports from `@tythe/ts` without errors

## 10. Pull the trigger

Once everything above is ticked:

1. Merge any final PRs into `main`. CI green.
2. release-please opens / updates a "release PR" with version bumps +
   CHANGELOG diffs across packages. Review and merge.
3. The merge triggers `release.yml`, which:
   - Creates GitHub Releases for each bumped component.
   - Publishes the Python wheel via PyPI Trusted Publishing.
   - Publishes each `@tythe/*` package to npm with provenance.
4. Verify install from a fresh machine (re-run §9 against the
   registry, not source).
5. Post the announcement.

If anything goes sideways mid-publish:

- **PyPI half-published, npm not:** unyanking PyPI is impossible —
  bump to the next patch, fix, republish. Don't try to delete.
- **One npm package published, others not:** finish the run; package
  versions can briefly drift. Don't try to unpublish.
- **Wrong tag pushed:** delete locally and on origin
  (`git push --delete origin <tag>`), re-tag, re-push. Only safe
  _before_ the publish workflow finishes.

## 11. Post-release

- [ ] Smoke test from a clean machine passes against published versions
- [ ] `git log --oneline` matches what's in GitHub Releases
- [ ] PyPI page renders the README correctly
- [ ] npm pages render the READMEs correctly
- [ ] Open issues triaged: anything tagged `pre-1.0` reviewed for
      v0.2 inclusion
- [ ] Update `ROADMAP.md` to reflect shipped state if anything moved

---

## Standing rules (don't violate at release time)

- **Never** force-push to `main`.
- **Never** publish from a dirty working tree.
- **Never** edit a published `CHANGELOG.md` — append a follow-up entry.
- **Never** skip CI on a release commit. If you have to, fix CI first.
- **Always** verify `git rev-parse HEAD` matches the tag right before
  publish.
