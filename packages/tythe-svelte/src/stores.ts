import { readable, writable } from "svelte/store";
import type { Readable, Writable } from "svelte/store";

import type { ArgsOf, DataOf, ErrorOf, StreamItemOf, StreamKeys, UnaryKeys } from "./types.js";

type Unary = (args?: unknown, opts?: { signal?: AbortSignal }) => Promise<unknown>;
type Stream = (args?: unknown, opts?: { signal?: AbortSignal }) => AsyncIterable<unknown>;
interface Envelope {
  ok: boolean;
  data?: unknown;
  error?: unknown;
}

function unwrap(value: unknown): unknown {
  if (value === null || typeof value !== "object") {
    return value;
  }
  const e = value as Envelope;
  if (typeof e.ok !== "boolean" || (!("data" in e) && !("error" in e))) {
    return value;
  }
  if (e.ok) {
    return e.data;
  }
  throw e.error;
}

export interface QueryStoreOptions {
  enabled?: boolean;
}

export interface QueryStoreValue<TData, TError> {
  status: "idle" | "loading" | "success" | "error";
  data: TData | undefined;
  error: TError | undefined;
  refetch: () => void;
}

export interface MutationStoreValue<TData, TError, TArgs> {
  status: "idle" | "loading" | "success" | "error";
  data: TData | undefined;
  error: TError | undefined;
  mutate: (args: TArgs) => Promise<TData>;
  reset: () => void;
}

export interface SubscriptionStoreValue<TError> {
  status: "idle" | "connecting" | "open" | "closed" | "error";
  error: TError | undefined;
}

export interface TytheStores<TApi> {
  query: <K extends UnaryKeys<TApi>>(
    method: K,
    args: ArgsOf<TApi[K]>,
    options?: QueryStoreOptions,
  ) => Readable<QueryStoreValue<DataOf<TApi[K]>, ErrorOf<TApi[K]>>>;

  mutation: <K extends UnaryKeys<TApi>>(
    method: K,
  ) => Readable<MutationStoreValue<DataOf<TApi[K]>, ErrorOf<TApi[K]>, ArgsOf<TApi[K]>>>;

  subscription: <K extends StreamKeys<TApi>>(
    method: K,
    args: ArgsOf<TApi[K]>,
    onEvent: (event: StreamItemOf<TApi[K]>) => void,
    options?: { enabled?: boolean },
  ) => Readable<SubscriptionStoreValue<unknown>>;
}

export function createTytheStores<TApi extends object>(api: TApi): TytheStores<TApi> {
  function query<K extends UnaryKeys<TApi>>(
    method: K,
    args: ArgsOf<TApi[K]>,
    options: QueryStoreOptions = {},
  ) {
    const enabled = options.enabled ?? true;
    type V = QueryStoreValue<DataOf<TApi[K]>, ErrorOf<TApi[K]>>;
    const inner: Writable<V> = writable({
      data: undefined,
      error: undefined,
      refetch: () => run(),
      status: enabled ? "loading" : "idle",
    });

    let controller: AbortController | null = null;
    function run() {
      controller?.abort();
      controller = new AbortController();
      inner.update((s) => ({ ...s, error: undefined, status: "loading" }));
      const fn = api[method] as unknown as Unary;
      const { signal } = controller;
      void (async () => {
        try {
          const data = unwrap(await fn(args as unknown, { signal })) as DataOf<TApi[K]>;
          inner.update((s) => ({ ...s, data, error: undefined, status: "success" }));
        } catch (error) {
          if ((error as { name?: string })?.name === "AbortError") {
            return;
          }
          inner.update((s) => ({
            ...s,
            error: error as ErrorOf<TApi[K]>,
            status: "error",
          }));
        }
      })();
    }

    if (enabled) {
      run();
    }
    return { subscribe: inner.subscribe };
  }

  function mutation<K extends UnaryKeys<TApi>>(method: K) {
    type V = MutationStoreValue<DataOf<TApi[K]>, ErrorOf<TApi[K]>, ArgsOf<TApi[K]>>;
    const inner: Writable<V> = writable({
      data: undefined,
      error: undefined,
      mutate: async (vars: ArgsOf<TApi[K]>) => {
        inner.update((s) => ({ ...s, error: undefined, status: "loading" }));
        const fn = api[method] as unknown as Unary;
        try {
          const data = unwrap(await fn(vars as unknown)) as DataOf<TApi[K]>;
          inner.update((s) => ({ ...s, data, status: "success" }));
          return data;
        } catch (error) {
          inner.update((s) => ({
            ...s,
            error: error as ErrorOf<TApi[K]>,
            status: "error",
          }));
          throw error;
        }
      },
      reset: () =>
        inner.set({
          status: "idle",
          data: undefined,
          error: undefined,
          // Re-bind mutate / reset on reset
          mutate: getStore().mutate,
          reset: getStore().reset,
        }),
      status: "idle",
    });
    // Captured for `.reset()` so the same callbacks survive
    let captured: V;
    inner.subscribe((v) => (captured = v));
    function getStore(): V {
      return captured;
    }
    return { subscribe: inner.subscribe };
  }

  function subscription<K extends StreamKeys<TApi>>(
    method: K,
    args: ArgsOf<TApi[K]>,
    onEvent: (event: StreamItemOf<TApi[K]>) => void,
    options: { enabled?: boolean } = {},
  ) {
    const enabled = options.enabled ?? true;
    return readable<SubscriptionStoreValue<unknown>>(
      { error: undefined, status: enabled ? "connecting" : "idle" },
      (set) => {
        if (!enabled) {
          return;
        }
        const controller = new AbortController();
        set({ error: undefined, status: "connecting" });
        void (async () => {
          try {
            const fn = api[method] as unknown as Stream;
            const iter = fn(args as unknown, { signal: controller.signal });
            set({ error: undefined, status: "open" });
            for await (const ev of iter) {
              if (controller.signal.aborted) {
                return;
              }
              onEvent(ev as StreamItemOf<TApi[K]>);
            }
            if (controller.signal.aborted) {
              return;
            }
            set({ error: undefined, status: "closed" });
          } catch (error) {
            if (controller.signal.aborted) {
              return;
            }
            set({ error, status: "error" });
          }
        })();
        return () => controller.abort();
      },
    );
  }

  return { mutation, query, subscription };
}
