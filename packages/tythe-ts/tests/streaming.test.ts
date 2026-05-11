import { describe, expect, it, vi } from "vitest";

import { createClient } from "../src/client.js";
import type { RouteDescriptor } from "../src/types.js";

const routes: RouteDescriptor[] = [
  {
    method: "GET",
    path: "/chat",
    name: "chat",
    streams: true,
  },
];

function sseStream(frames: string[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();

  return new ReadableStream({
    start(controller) {
      for (const f of frames) controller.enqueue(enc.encode(f));
      controller.close();
    },
  });
}

describe("streaming client", () => {
  it("yields parsed JSON frames as a typed AsyncIterable", async () => {
    const body = sseStream([
      'data: {"kind":"token","text":"hi"}\n\n',
      'data: {"kind":"token","text":"there"}\n\n',
      "event: done\ndata: {}\n\n",
    ]);

    const fetchMock = vi.fn<typeof fetch>(
      async () =>
        new Response(body, {
          status: 200,
          headers: { "content-type": "text/event-stream" },
        }),
    );

    const api = createClient({ routes, fetch: fetchMock }) as {
      chat: () => AsyncIterable<{ kind: string; text?: string }>;
    };

    const got: unknown[] = [];
    for await (const ev of api.chat()) got.push(ev);

    expect(got).toEqual([
      { kind: "token", text: "hi" },
      { kind: "token", text: "there" },
    ]);
  });

  it("throws on event: error frames", async () => {
    const body = sseStream(['event: error\ndata: {"kind":"RateLimited","retry_after":5}\n\n']);

    const fetchMock = vi.fn<typeof fetch>(
      async () =>
        new Response(body, {
          status: 200,
          headers: { "content-type": "text/event-stream" },
        }),
    );

    const api = createClient({ routes, fetch: fetchMock }) as {
      chat: () => AsyncIterable<unknown>;
    };

    const run = async () => {
      for await (const ev of api.chat()) {
        void ev;
      }
    };

    await expect(run()).rejects.toThrow(/stream error/);
  });
});
