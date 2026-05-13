// @vitest-environment node
import { describe, expect, it } from "vitest";

describe("CSR safety", () => {
  it("loads `@tythe/react` without DOM globals", async () => {
    expect(typeof globalThis.window).toBe("undefined");
    expect(typeof globalThis.document).toBe("undefined");

    const mod = await import("../src/index.js");
    expect(typeof mod.createTytheHooks).toBe("function");
  });

  it("loads `@tythe/react/server` without DOM globals", async () => {
    expect(typeof globalThis.window).toBe("undefined");
    expect(typeof globalThis.document).toBe("undefined");

    const mod = await import("../src/server.js");
    expect(typeof mod.prefetchQuery).toBe("function");
    expect(typeof mod.prefetchQueries).toBe("function");
    expect(typeof mod.getQueryKey).toBe("function");
  });

  it("`getQueryKey` is deterministic for equal args", async () => {
    const { getQueryKey } = (await import("../src/server.js")) as unknown as {
      getQueryKey: (method: string, args: unknown) => readonly unknown[];
    };
    const a = getQueryKey("getUser", { userId: 1 });
    const b = getQueryKey("getUser", { userId: 1 });
    expect(a).toEqual(b);
  });
});
