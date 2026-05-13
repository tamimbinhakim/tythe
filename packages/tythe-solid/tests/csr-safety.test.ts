// @vitest-environment node
import { describe, expect, it } from "vitest";

describe("CSR safety", () => {
  it("loads `@tythe/solid/server` without DOM globals", async () => {
    expect(typeof globalThis.window).toBe("undefined");
    expect(typeof globalThis.document).toBe("undefined");

    const mod = await import("../src/server.js");
    expect(typeof mod.serverQuery).toBe("function");
  });
});
