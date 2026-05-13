import { forwardHeaders } from "@tythe/ts";

import type { ArgsOf, DataOf, UnaryKeys } from "./types.js";

type Unary = (args?: unknown, opts?: { headers?: Record<string, string> }) => Promise<unknown>;

/** Call a Tythe method from a SolidStart server function with auth/locale headers forwarded. */
export async function serverQuery<TApi extends object, K extends UnaryKeys<TApi> & string>(
  api: TApi,
  method: K,
  args: ArgsOf<TApi[K]>,
  request: Request,
  options: { forwardHeaders?: readonly string[] } = {},
): Promise<DataOf<TApi[K]>> {
  const headers = forwardHeaders(request, options.forwardHeaders);
  const fn = api[method] as unknown as Unary;
  const value = await fn(args as unknown, { headers });
  return unwrapEnvelope(value) as DataOf<TApi[K]>;
}

function unwrapEnvelope(value: unknown): unknown {
  if (value === null || typeof value !== "object") return value;
  const e = value as { ok?: unknown; data?: unknown; error?: unknown };
  if (typeof e.ok !== "boolean" || (!("data" in e) && !("error" in e))) return value;
  if (e.ok) return e.data;
  throw e.error;
}
