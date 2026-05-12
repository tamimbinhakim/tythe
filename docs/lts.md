# Long-term support

This page describes the support window for Tythe releases.

## Active lines

| Line              | Status | Bug fixes | Security fixes | EOL                |
| ----------------- | ------ | --------- | -------------- | ------------------ |
| **1.x** (current) | Active | ✓         | ✓              | TBD when 2.0 ships |

Pre-1.0 versions (0.x) are not LTS-eligible — they exist for
preview only and should be pinned to an exact version.

## Support guarantees on the 1.x line

Once 1.0 ships:

- **Patch releases (`1.x.y` → `1.x.y+1`)** ship as needed for bug fixes
  and security issues. No new features.
- **Minor releases (`1.x` → `1.x+1`)** ship additive features. Backwards
  compatible.
- **Major (`2.0`)** ships only when there is a strongly motivated
  breaking change. The previous major (`1.x`) gets at least 12 months
  of bug-fix and security backports after `2.0` ships.

## What backporting covers

A fix lands on `main` and is then backported to the latest supported
`1.x` minor line if:

- It's a **security issue** (any severity).
- It's a **regression** introduced in `1.x`.
- It's a **user-blocking bug** with no documented workaround.

A fix is **not** backported if:

- It depends on a `feat` that only landed on a newer minor.
- It would require a behavior change inconsistent with the LTS line's
  `1.x.y` semver contract.

## How to pin

For pre-1.0 (now):

```bash
uv add 'tythe==0.1.0'              # PyPI
pnpm add '@tythe/ts@0.1.0' \
        '@tythe/react@0.1.0' \
        '@tythe/svelte@0.1.0' \
        '@tythe/solid@0.1.0'       # npm
```

After 1.0, pin to a minor with `^1.x` (or `>=1.x.y,<2`) and trust
patch-level updates.

## Security disclosure

See [`SECURITY.md`](../SECURITY.md). Patches land in a same-day point
release on the active line; the supported `1.x` LTS line gets the same
backport on the next business day at the latest.

## What gets EOL'd

A line goes EOL when a strictly newer line has been available for ≥12
months. EOL versions stop receiving bug fixes and security patches.
Critical CVEs may still get an out-of-band patch at the maintainer's
discretion, but it's not guaranteed.

EOL is announced in CHANGELOG and on the GitHub release for the final
patch on that line.
