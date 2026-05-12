# Versioning policy

Tythe follows [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).
Each package (`tythe`, `@tythe/ts`, `@tythe/react`, `@tythe/svelte`,
`@tythe/solid`) versions independently — managed by `release-please` off
the manifest at `.release-please-manifest.json`.

## What semver means here

| Bump                            | Trigger                    | Examples                                                                                                     |
| ------------------------------- | -------------------------- | ------------------------------------------------------------------------------------------------------------ |
| **Patch** (`X.Y.Z` → `X.Y.Z+1`) | Bug fix, no surface change | A `msgspec.convert` edge case is fixed; doc typo; CI dep bump.                                               |
| **Minor** (`X.Y` → `X.Y+1`)     | Additive feature, no break | New primitive (`Bytes`, `Form`), new CLI command, new optional IR field, new `__all__` export.               |
| **Major** (`X` → `X+1`)         | Breaking change            | Field removed from IR, public API renamed, wire format altered, primitive removed, default behavior changed. |

## Breaking change examples

Anything below is breaking by default, regardless of how small it looks:

- Removing or renaming a public name in `__all__`.
- Changing the shape of the JSON wire format (envelope keys, SSE frame layout).
- Removing or renaming an `IR` field.
- Adding a required parameter to a public function.
- Tightening a type annotation in a way that rejects previously valid inputs.
- Changing default behavior (e.g. flipping a default from `False` to `True`).
- Changing a route's method or path in a generated client.

If you're unsure, treat it as breaking.

## Pre-1.0 behavior

Until 1.0:

- **Minor bumps may break.** That's why the README and per-package READMEs
  ask you to pin exact versions.
- **CHANGELOG entries call out breakage explicitly** at the top of each section.

After 1.0:

- **Patch and minor never break.**
- **Major bumps follow the deprecation cycle in `ir-stability.md`** — one
  full minor of deprecation warnings before removal.

## How CI enforces it

- **`tythe diff` in CI** compares the IR snapshot from `main` to the IR
  snapshot built from each PR. Breaking changes annotate the PR with
  GitHub error annotations and fail the required check.
- **release-please** classifies commits via Conventional Commits. A
  `feat!:` or `BREAKING CHANGE:` footer triggers a major bump in the
  release PR. A plain `feat:` triggers minor. `fix:` triggers patch.
  `chore:`, `docs:`, `ci:`, `test:`, `build:`, `refactor:` are hidden
  from the changelog and do not bump versions.

## What you can rely on

Once a name appears in `__all__` (Python) or `index.ts` (TS), it is
public and follows the rules above. Anything imported via a private
underscore-prefixed module (`tythe._pydantic`, `tythe._idents`, …) is
not part of the contract and may change in any release.

## What is _not_ semver-governed

- **Internal implementation details.** Refactors that don't change
  observable behavior or the public surface are not breaking, even if
  they reshape modules.
- **Performance characteristics.** Tythe aims to be fast, but a
  measurable regression in p99 latency is a bug to be fixed, not a
  semver event.
- **Dev dependencies.** Bumping ruff or vitest versions is never a
  breaking change for downstream consumers.
- **Examples (`examples/*`).** Examples are reference material, not API.
- **The `tythe-kit` meta-framework** (if and when it ships) versions
  separately.
