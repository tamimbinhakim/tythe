import {
  useMutation as useRQMutation,
  useQuery as useRQQuery,
  type UseMutationOptions,
  type UseMutationResult,
  type UseQueryOptions,
  type UseQueryResult,
} from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";

import type {
  ArgsOf,
  DataOf,
  ErrorOf,
  StreamItemOf,
  StreamKeys,
  SubscriptionStatus,
  UnaryKeys,
} from "./types.js";

type Unary = (args?: unknown, opts?: { signal?: AbortSignal }) => Promise<unknown>;
type Stream = (args?: unknown, opts?: { signal?: AbortSignal }) => AsyncIterable<unknown>;
type Envelope = { ok: boolean; data?: unknown; error?: unknown };

// Routes with `@raises(...)` on the Python side return `{ ok, data | error }`.
// Unwrap so TanStack sees a plain success/throw split and the typed error union
// lands on `.error` instead of buried inside `.data`.
function unwrap(value: unknown): unknown {
  if (value === null || typeof value !== "object") return value;
  const e = value as Envelope;
  if (typeof e.ok !== "boolean" || (!("data" in e) && !("error" in e))) return value;
  if (e.ok) return e.data;
  throw e.error;
}

export interface UseTytheSubscriptionOptions<TEvent> {
  enabled?: boolean;
  onEvent: (event: TEvent) => void;
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (error: unknown) => void;
}

export interface UseTytheSubscriptionResult {
  status: SubscriptionStatus;
  error: unknown;
}

export interface TytheHooks<TApi> {
  useQuery: <K extends UnaryKeys<TApi>>(
    method: K,
    args: ArgsOf<TApi[K]>,
    options?: Omit<
      UseQueryOptions<DataOf<TApi[K]>, ErrorOf<TApi[K]>, DataOf<TApi[K]>, readonly unknown[]>,
      "queryKey" | "queryFn"
    > & { queryKey?: readonly unknown[] },
  ) => UseQueryResult<DataOf<TApi[K]>, ErrorOf<TApi[K]>>;

  useMutation: <K extends UnaryKeys<TApi>>(
    method: K,
    options?: Omit<
      UseMutationOptions<DataOf<TApi[K]>, ErrorOf<TApi[K]>, ArgsOf<TApi[K]>>,
      "mutationFn"
    >,
  ) => UseMutationResult<DataOf<TApi[K]>, ErrorOf<TApi[K]>, ArgsOf<TApi[K]>>;

  useSubscription: <K extends StreamKeys<TApi>>(
    method: K,
    args: ArgsOf<TApi[K]>,
    options: UseTytheSubscriptionOptions<StreamItemOf<TApi[K]>>,
  ) => UseTytheSubscriptionResult;
}

export function createTytheHooks<TApi extends object>(api: TApi): TytheHooks<TApi> {
  function useQuery<K extends UnaryKeys<TApi>>(
    method: K,
    args: ArgsOf<TApi[K]>,
    options?: Omit<
      UseQueryOptions<DataOf<TApi[K]>, ErrorOf<TApi[K]>, DataOf<TApi[K]>, readonly unknown[]>,
      "queryKey" | "queryFn"
    > & { queryKey?: readonly unknown[] },
  ) {
    return useRQQuery<DataOf<TApi[K]>, ErrorOf<TApi[K]>, DataOf<TApi[K]>, readonly unknown[]>({
      queryKey: [method, args],
      ...options,
      queryFn: async ({ signal }) => {
        const fn = api[method] as unknown as Unary;
        return unwrap(await fn(args as unknown, { signal })) as DataOf<TApi[K]>;
      },
    });
  }

  function useMutation<K extends UnaryKeys<TApi>>(
    method: K,
    options?: Omit<
      UseMutationOptions<DataOf<TApi[K]>, ErrorOf<TApi[K]>, ArgsOf<TApi[K]>>,
      "mutationFn"
    >,
  ) {
    return useRQMutation<DataOf<TApi[K]>, ErrorOf<TApi[K]>, ArgsOf<TApi[K]>>({
      ...options,
      mutationFn: async (vars) => {
        const fn = api[method] as unknown as Unary;
        return unwrap(await fn(vars as unknown)) as DataOf<TApi[K]>;
      },
    });
  }

  function useSubscription<K extends StreamKeys<TApi>>(
    method: K,
    args: ArgsOf<TApi[K]>,
    options: UseTytheSubscriptionOptions<StreamItemOf<TApi[K]>>,
  ): UseTytheSubscriptionResult {
    const { enabled = true, onEvent, onOpen, onClose, onError } = options;
    const [status, setStatus] = useState<SubscriptionStatus>("idle");
    const [error, setError] = useState<unknown>(null);

    // Latest callbacks held in a ref so an inline `onEvent={(e) => ...}` doesn't
    // tear down the stream every render.
    const cb = useRef({ onEvent, onOpen, onClose, onError });
    cb.current = { onEvent, onOpen, onClose, onError };

    // Stable key over structurally-equal args.
    const argsKey = useMemo(() => stableKey(args), [args]);

    useEffect(() => {
      if (!enabled) {
        setStatus("idle");
        return;
      }
      const controller = new AbortController();
      setStatus("connecting");
      setError(null);

      void (async () => {
        try {
          const fn = api[method] as unknown as Stream;
          const iter = fn(args as unknown, { signal: controller.signal });
          setStatus("open");
          cb.current.onOpen?.();
          for await (const ev of iter) {
            if (controller.signal.aborted) break;
            cb.current.onEvent(ev as StreamItemOf<TApi[K]>);
          }
          if (controller.signal.aborted) return;
          setStatus("closed");
          cb.current.onClose?.();
        } catch (err) {
          if (controller.signal.aborted) return;
          setError(err);
          setStatus("error");
          cb.current.onError?.(err);
        }
      })();

      return () => controller.abort();
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [enabled, method, argsKey]);

    return { status, error };
  }

  return { useQuery, useMutation, useSubscription };
}

function stableKey(value: unknown): string {
  if (value === undefined) return "";
  return JSON.stringify(value, (_k, v: unknown) => {
    if (v && typeof v === "object" && !Array.isArray(v)) {
      const out: Record<string, unknown> = {};
      // Fresh array from Object.keys — sorting in place is fine.
      // eslint-disable-next-line unicorn/no-array-sort
      for (const k of Object.keys(v as Record<string, unknown>).sort()) {
        out[k] = (v as Record<string, unknown>)[k];
      }
      return out;
    }
    return v;
  });
}
