# Changelog · `tythe`

All notable changes to the `tythe` Python package will be documented in this
file. Managed automatically by [release-please](https://github.com/googleapis/release-please)
from [Conventional Commits](https://www.conventionalcommits.org/).

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1](https://github.com/tamimbinhakim/tythe/compare/tythe-v0.1.0...tythe-v0.1.1) (2026-05-13)


### Features

* **bidi:** [@app](https://github.com/app).websocket + BidiChannel[s, r] server-side primitive ([dbf4952](https://github.com/tamimbinhakim/tythe/commit/dbf4952fc7f713b884082d7e08d76dbdb5a70361))
* **cli:** tythe ir + tythe diff for breaking-change ci ([3645859](https://github.com/tamimbinhakim/tythe/commit/3645859c0c437f9de43d2e6d7b11faafdbf4231e))
* **codegen:** beautify generated client.ts ([16598da](https://github.com/tamimbinhakim/tythe/commit/16598da30e3e708a50a69304a48454e73da9a273))
* **codegen:** harden generated-name collision handling ([6debdc9](https://github.com/tamimbinhakim/tythe/commit/6debdc9b45a70cfa632b91e8ff305528e5e21936))
* **polyglot:** typed streaming wrappers for swift + kotlin ([233d26c](https://github.com/tamimbinhakim/tythe/commit/233d26c734831bf9f3439f9221cb79eec3afb5a9))
* **streaming:** sse last-event-id resumption with sse-payload framing ([3527103](https://github.com/tamimbinhakim/tythe/commit/352710338f59cdeb973cb4698a0b424a79cf4dc5))
* **tasks:** mount_task_routes wires submit/status/stream from one handler ([63edce9](https://github.com/tamimbinhakim/tythe/commit/63edce91f5723160bde2b736e204afd4b58614f2))
* **tythe:** field-level validation errors with structured 422 body ([2a6f358](https://github.com/tamimbinhakim/tythe/commit/2a6f35858a3a6593123e1ee70d7caaa5bceb8a99))
* **tythe:** pydantic deep parity — aliases, discriminators, computed fields ([f2b348f](https://github.com/tamimbinhakim/tythe/commit/f2b348f378ee1b2d9b0ff848986dd32469fadddb))


### Bug Fixes

* **ci:** silence mypy on dynamic state_type + skip TOML in oxfmt ([a9341cc](https://github.com/tamimbinhakim/tythe/commit/a9341cc5356562eab0ef0b380df07fac4c117b39))


### Performance

* **tythe:** cached typed decoder + lazy tasks + skip pydantic check ([cc51bb7](https://github.com/tamimbinhakim/tythe/commit/cc51bb74d7ac034b006d30077aceb931275d4e6a))

## [Unreleased]

### Added

- Initial package scaffold: `App`, route decorators, `Context`,
  `Depends`, `stream`, `@raises`, IR builder, codegen renderer, `tythe`
  CLI.
