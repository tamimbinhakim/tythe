import { describe, expect, it } from "vitest";

import { parseSSE } from "../src/sse.js";

function streamOf(...chunks: string[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const c of chunks) controller.enqueue(enc.encode(c));
      controller.close();
    },
  });
}

describe("parseSSE", () => {
  it("parses a single data frame", async () => {
    const events = [];
    for await (const ev of parseSSE(streamOf("data: hello\n\n"))) {
      events.push(ev);
    }
    expect(events).toEqual([{ data: "hello" }]);
  });

  it("concatenates multi-line data", async () => {
    const events = [];
    for await (const ev of parseSSE(streamOf("data: line1\ndata: line2\n\n"))) {
      events.push(ev);
    }
    expect(events[0]?.data).toBe("line1\nline2");
  });

  it("parses event and id fields", async () => {
    const events = [];
    for await (const ev of parseSSE(streamOf("event: token\nid: 7\ndata: x\n\n"))) {
      events.push(ev);
    }
    expect(events[0]).toEqual({ event: "token", id: "7", data: "x" });
  });

  it("ignores comments and blank lines", async () => {
    const events = [];
    for await (const ev of parseSSE(streamOf(":heartbeat\n\ndata: real\n\n"))) {
      events.push(ev);
    }
    expect(events).toEqual([{ data: "real" }]);
  });

  it("handles chunk boundaries that split a frame", async () => {
    const events = [];
    for await (const ev of parseSSE(streamOf("data: hel", "lo\n", "\n"))) {
      events.push(ev);
    }
    expect(events).toEqual([{ data: "hello" }]);
  });
});
