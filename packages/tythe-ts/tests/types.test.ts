// Type-only checks for `Ok<R>` and `Err<R>`. These don't run any assertions —
// vitest's `expectTypeOf` is purely a tsc-time check that fails the build.

import { describe, expectTypeOf, it } from "vitest";

import type { Err, Ok, Result } from "../src/types.js";

interface User {
  id: number;
}
interface NotFound {
  kind: "NotFound";
}
interface Forbidden {
  kind: "Forbidden";
}

describe("Ok / Err", () => {
  it("extracts the success branch", () => {
    expectTypeOf<Ok<Result<User, NotFound | Forbidden>>>().toEqualTypeOf<User>();
  });

  it("extracts the error union", () => {
    expectTypeOf<Err<Result<User, NotFound | Forbidden>>>().toEqualTypeOf<NotFound | Forbidden>();
  });

  it("returns never on a non-Result type", () => {
    expectTypeOf<Ok<User>>().toBeNever();
    expectTypeOf<Err<User>>().toBeNever();
  });
});
