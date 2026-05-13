import { describe, expect, it } from "vitest";

describe("CSR safety", () => {
  it("loads `@tythe/svelte` without DOM globals", async () => {
    expect(typeof globalThis.window).toBe("undefined");
    expect(typeof globalThis.document).toBe("undefined");

    const mod = await import("../src/index.js");
    expect(typeof mod.createTytheStores).toBe("function");
  });

  it("loads `@tythe/svelte/server` without DOM globals", async () => {
    expect(typeof globalThis.window).toBe("undefined");
    expect(typeof globalThis.document).toBe("undefined");

    const mod = await import("../src/server.js");
    expect(typeof mod.loadQuery).toBe("function");
  });
});
