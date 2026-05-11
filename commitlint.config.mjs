/** @type {import('@commitlint/types').UserConfig} */
export default {
  extends: ["@commitlint/config-conventional"],
  rules: {
    "body-max-line-length": [2, "always", 100],
    "subject-case": [2, "never", ["sentence-case", "start-case", "pascal-case", "upper-case"]],
    "scope-enum": [
      1,
      "always",
      [
        "tythe",
        "client",
        "codegen",
        "ir",
        "cli",
        "streaming",
        "errors",
        "examples",
        "docs",
        "ci",
        "deps",
        "release",
        "repo",
      ],
    ],
    "type-enum": [
      2,
      "always",
      [
        "feat",
        "fix",
        "perf",
        "refactor",
        "docs",
        "test",
        "build",
        "ci",
        "chore",
        "revert",
        "style",
      ],
    ],
  },
};
