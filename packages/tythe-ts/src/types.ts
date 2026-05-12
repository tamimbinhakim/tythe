// Shared types between the runtime and the generated client.

export type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
export type ParamLocation = "path" | "query" | "body" | "header" | "cookie" | "file";

export interface ParamDescriptor {
  name: string;
  alias: string;
  in: ParamLocation;
  embed?: boolean;
}

export interface RouteDescriptor {
  method: HttpMethod;
  path: string;
  name: string;
  params?: ReadonlyArray<ParamDescriptor>;
  streams?: boolean;
  result?: boolean;
  /** Body is raw bytes (Blob / Uint8Array / ArrayBuffer) — skip JSON envelope. */
  binaryBody?: boolean;
  /** Response is raw bytes — decode with `res.blob()` instead of `res.json()`. */
  binaryResponse?: boolean;
}

export interface ClientConfig {
  baseUrl?: string;
  routes: ReadonlyArray<RouteDescriptor>;
  fetch?: typeof globalThis.fetch;
  headers?: Record<string, string>;
}

export interface CallOptions {
  signal?: AbortSignal;
  headers?: Record<string, string>;
}

export type Result<T, E> = { ok: true; data: T } | { ok: false; error: E };

/**
 * Unwrap a Result envelope: returns `data` on success, throws `error` on failure.
 * Plain (non-envelope) values pass through unchanged. Used by the framework
 * binding packages so a typed error union lands on the consumer's `.error`
 * slot rather than buried inside `.data`.
 */
type Envelope = { ok: boolean; data?: unknown; error?: unknown };
export function unwrapResult(value: unknown): unknown {
  if (value === null || typeof value !== "object") return value;
  const e = value as Envelope;
  if (typeof e.ok !== "boolean" || (!("data" in e) && !("error" in e))) return value;
  if (e.ok) return e.data;
  throw e.error;
}

// `OkOf` / `ErrOf` are the distributive workers; `Ok` / `Err` apply `Awaited`
// first so users can pass a `Promise<Result<…>>` directly (which is what the
// generated `Routes.X.Return` is for unary routes). Splitting in two stages
// matters: TS only distributes a conditional over a union when the LHS is a
// *naked* type parameter, so we route `Awaited<R>` through a fresh `X` to
// force the per-branch evaluation.
type OkOf<X> = X extends { ok: true; data: infer D } ? D : never;
type ErrOf<X> = X extends { ok: false; error: infer E } ? E : never;

/** Unwrap the success type from a `Result` or `Promise<Result>`. */
export type Ok<R> = OkOf<Awaited<R>>;

/** Unwrap the error union from a `Result` or `Promise<Result>`. */
export type Err<R> = ErrOf<Awaited<R>>;
