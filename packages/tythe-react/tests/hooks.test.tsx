/* eslint-disable require-yield -- intentional in test fixtures */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { createTytheHooks } from "../src/index.js";

type Result<T, E> = { ok: true; data: T } | { ok: false; error: E };

interface Issue {
  id: number;
  title: string;
}
interface IssueNotFound {
  kind: "IssueNotFound";
  issueId: number;
}

interface TestApi {
  getIssue(args: { issueId: number }): Promise<Result<Issue, IssueNotFound>>;
  rawPing(): Promise<{ ok: true; pong: true }>;
  createIssue(args: { data: { title: string } }): Promise<Result<Issue, IssueNotFound>>;
  events(args: { topic: string }): AsyncIterable<{ kind: "tick"; n: number }>;
}

function makeWrapper() {
  // retry: false so a single rejection lands on `.error` immediately.
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

function renderHook<T>(hook: () => T, Wrapper: (p: { children: ReactNode }) => ReactNode) {
  const result: { current: T | null } = { current: null };
  function Probe() {
    result.current = hook();
    return null;
  }
  const utils = render(<Probe />, { wrapper: Wrapper });
  return { result, ...utils };
}

describe("useQuery", () => {
  it("unwraps a Result.ok envelope into .data", async () => {
    const getIssue = vi.fn(async () => ({ ok: true as const, data: { id: 1, title: "hi" } }));
    const { useQuery } = createTytheHooks({ getIssue } as unknown as TestApi);

    const { result } = renderHook(() => useQuery("getIssue", { issueId: 1 }), makeWrapper());

    await waitFor(() => expect(result.current?.isSuccess).toBe(true));
    expect(result.current?.data).toEqual({ id: 1, title: "hi" });
  });

  it("surfaces Result.error on .error", async () => {
    const err = { kind: "IssueNotFound" as const, issueId: 99 };
    const getIssue = vi.fn(async () => ({ ok: false as const, error: err }));
    const { useQuery } = createTytheHooks({ getIssue } as unknown as TestApi);

    const { result } = renderHook(() => useQuery("getIssue", { issueId: 99 }), makeWrapper());

    await waitFor(() => expect(result.current?.isError).toBe(true));
    expect(result.current?.error).toEqual(err);
  });

  it("passes non-Result returns through untouched", async () => {
    // `{ ok: true, pong: true }` has no `data`/`error` keys — not an envelope.
    const rawPing = vi.fn(async () => ({ ok: true as const, pong: true as const }));
    const { useQuery } = createTytheHooks({ rawPing } as unknown as TestApi);

    const { result } = renderHook(() => useQuery("rawPing", undefined as never), makeWrapper());

    await waitFor(() => expect(result.current?.isSuccess).toBe(true));
    expect(result.current?.data).toEqual({ ok: true, pong: true });
  });

  it("forwards args and signal to the api method", async () => {
    const getIssue = vi.fn(async () => ({ ok: true as const, data: { id: 7, title: "x" } }));
    const { useQuery } = createTytheHooks({ getIssue } as unknown as TestApi);

    const { result } = renderHook(() => useQuery("getIssue", { issueId: 7 }), makeWrapper());

    await waitFor(() => expect(result.current?.isSuccess).toBe(true));
    expect(getIssue).toHaveBeenCalledWith(
      { issueId: 7 },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  });
});

describe("useMutation", () => {
  it("unwraps Result.ok on success", async () => {
    const createIssue = vi.fn(async () => ({ ok: true as const, data: { id: 5, title: "new" } }));
    const { useMutation } = createTytheHooks({ createIssue } as unknown as TestApi);

    const { result } = renderHook(() => useMutation("createIssue"), makeWrapper());

    await act(async () => {
      await result.current!.mutateAsync({ data: { title: "new" } });
    });
    await waitFor(() => expect(result.current?.data).toEqual({ id: 5, title: "new" }));
  });

  it("rejects with Result.error and lands it on .error", async () => {
    const err = { kind: "IssueNotFound" as const, issueId: 1 };
    const createIssue = vi.fn(async () => ({ ok: false as const, error: err }));
    const { useMutation } = createTytheHooks({ createIssue } as unknown as TestApi);

    const { result } = renderHook(() => useMutation("createIssue"), makeWrapper());

    await act(async () => {
      await expect(result.current!.mutateAsync({ data: { title: "x" } })).rejects.toEqual(err);
    });
    await waitFor(() => expect(result.current?.error).toEqual(err));
  });
});

async function* twoTicks(): AsyncIterable<{ kind: "tick"; n: number }> {
  yield { kind: "tick", n: 1 };
  yield { kind: "tick", n: 2 };
}

async function* immediateThrow(): AsyncIterable<unknown> {
  throw new Error("boom");
}

describe("useSubscription", () => {
  it("delivers events and transitions to closed when the stream ends", async () => {
    const { useSubscription } = createTytheHooks({
      events: () => twoTicks(),
    } as unknown as TestApi);

    const received: unknown[] = [];
    const { result } = renderHook(
      () => useSubscription("events", { topic: "x" }, { onEvent: (ev) => received.push(ev) }),
      makeWrapper(),
    );

    await waitFor(() => expect(result.current?.status).toBe("closed"));
    expect(received).toEqual([
      { kind: "tick", n: 1 },
      { kind: "tick", n: 2 },
    ]);
  });

  it("aborts on unmount", async () => {
    let aborted = false;
    // Held open indefinitely; resolves only on abort so the hook tears it down.
    async function* events(_a: unknown, opts: { signal?: AbortSignal }): AsyncIterable<unknown> {
      opts.signal?.addEventListener("abort", () => {
        aborted = true;
      });
      await new Promise((resolve) => opts.signal?.addEventListener("abort", resolve));
    }
    const { useSubscription } = createTytheHooks({ events } as unknown as TestApi);

    const { unmount, result } = renderHook(
      () => useSubscription("events", { topic: "y" }, { onEvent: () => {} }),
      makeWrapper(),
    );

    await waitFor(() => expect(result.current?.status).toBe("open"));
    unmount();
    await waitFor(() => expect(aborted).toBe(true));
  });

  it("stays idle when enabled is false", () => {
    const events = vi.fn();
    const { useSubscription } = createTytheHooks({ events } as unknown as TestApi);

    const { result } = renderHook(
      () => useSubscription("events", { topic: "z" }, { enabled: false, onEvent: () => {} }),
      makeWrapper(),
    );

    expect(result.current?.status).toBe("idle");
    expect(events).not.toHaveBeenCalled();
  });

  it("transitions to error and surfaces the thrown value", async () => {
    const { useSubscription } = createTytheHooks({ events: immediateThrow } as unknown as TestApi);

    const { result } = renderHook(
      () => useSubscription("events", { topic: "q" }, { onEvent: () => {} }),
      makeWrapper(),
    );

    await waitFor(() => expect(result.current?.status).toBe("error"));
    expect(result.current?.error).toBeInstanceOf(Error);
  });
});
