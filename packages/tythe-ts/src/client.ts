import { parseSSE } from "./sse.js";
import type { CallOptions, ClientConfig, Result, RouteDescriptor } from "./types.js";

type Args = Record<string, unknown>;
type FetchImpl = typeof globalThis.fetch;

export function createClient(config: ClientConfig): unknown {
  const baseUrl = (config.baseUrl ?? "").replace(/\/$/, "");
  const fetchImpl: FetchImpl = config.fetch ?? globalThis.fetch.bind(globalThis);
  const byName = new Map<string, RouteDescriptor>(config.routes.map((r) => [r.name, r]));

  return new Proxy(Object.create(null) as Record<string, unknown>, {
    get(_target, prop: string) {
      const route = byName.get(prop);
      if (!route) return undefined;
      return (args?: Args, opts: CallOptions = {}) => {
        const { url, init } = buildRequest(route, args ?? {}, opts, baseUrl, config.headers);
        return route.streams
          ? streamCall(url, init, fetchImpl)
          : unaryCall(route, url, init, fetchImpl);
      };
    },
  });
}

function buildRequest(
  route: RouteDescriptor,
  args: Args,
  opts: CallOptions,
  baseUrl: string,
  defaultHeaders: Record<string, string> | undefined,
): { url: string; init: RequestInit } {
  let path = route.path;
  const query = new URLSearchParams();
  const headers: Record<string, string> = { ...defaultHeaders, ...opts.headers };

  const bodyEmbed: Record<string, unknown> = {};
  let bodyWhole: unknown;
  let bodyMode: "none" | "json" | "multipart" = "none";
  let multipart: FormData | null = null;

  for (const p of route.params ?? []) {
    const v = args[p.name];
    if (v === undefined) continue;
    switch (p.in) {
      case "path": {
        path = path.replace(`{${p.alias}}`, encodeURIComponent(String(v)));
        break;
      }
      case "query": {
        query.append(p.alias, String(v));
        break;
      }
      case "header": {
        headers[p.alias] = String(v);
        break;
      }
      case "cookie": {
        // Browsers won't let JS set Cookie directly — userland can override.
        const prev = headers["cookie"];
        headers["cookie"] = (prev ? `${prev}; ` : "") + `${p.alias}=${String(v)}`;
        break;
      }
      case "file": {
        if (multipart == null) multipart = new FormData();
        multipart.append(p.alias, v instanceof Blob ? v : String(v));
        bodyMode = "multipart";
        break;
      }
      case "body": {
        if (p.embed) bodyEmbed[p.alias] = v;
        else bodyWhole = v;
        if (bodyMode === "none") bodyMode = "json";
        break;
      }
    }
  }

  let body: BodyInit | undefined;
  if (bodyMode === "json") {
    headers["content-type"] ??= "application/json";
    const payload = Object.keys(bodyEmbed).length > 0 ? bodyEmbed : bodyWhole;
    // camelCase → snake_case so the Python server sees the keys it expects.
    body = payload === undefined ? undefined : JSON.stringify(camelToSnakeDeep(payload));
  } else if (bodyMode === "multipart" && multipart != null) {
    // Let fetch set the multipart boundary; we must NOT pin content-type.
    delete headers["content-type"];
    body = multipart;
  }

  const qs = query.toString();
  return {
    url: `${baseUrl}${path}${qs ? `?${qs}` : ""}`,
    init: { method: route.method, headers, body, signal: opts.signal },
  };
}

async function unaryCall(
  route: RouteDescriptor,
  url: string,
  init: RequestInit,
  fetchImpl: FetchImpl,
): Promise<unknown> {
  const res = await fetchImpl(url, init);
  if (!res.ok) throw await httpError(res);

  const ct = res.headers.get("content-type") ?? "";
  if (ct.includes("application/json")) {
    const raw = (await res.json()) as unknown;
    const value = snakeToCamelDeep(raw);
    // `result: true` hands the envelope back untouched; the caller's static
    // type is `Result<T, E>` so TypeScript forces them to branch on `ok`.
    return route.result ? (value as Result<unknown, unknown>) : value;
  }
  if (res.status === 204 || ct === "") return undefined;
  return await res.text();
}

async function* streamCall(
  url: string,
  init: RequestInit,
  fetchImpl: FetchImpl,
): AsyncIterableIterator<unknown> {
  const res = await fetchImpl(url, init);
  if (!res.ok) throw await httpError(res);
  if (!res.body) return;

  for await (const ev of parseSSE(res.body)) {
    if (ev.event === "done") return;
    if (ev.event === "error") {
      throw Object.assign(new Error("stream error"), {
        kind: "error",
        payload: safeJsonParse(ev.data),
      });
    }
    if (ev.data === "") continue;
    yield snakeToCamelDeep(safeJsonParse(ev.data));
  }
}

async function httpError(res: Response): Promise<Error & { status: number; body: string }> {
  const body = await res.text();
  return Object.assign(new Error(`HTTP ${res.status}: ${body}`), {
    status: res.status,
    body,
  });
}

function safeJsonParse(s: string): unknown {
  try {
    return JSON.parse(s);
  } catch {
    return s;
  }
}

// ---- snake_case ↔ camelCase ----
// Tythe runs Python (snake_case) on the wire and TS (camelCase) in the editor.
// We walk plain-object trees only — arrays of objects descend, scalars and class
// instances (Blob, Date, FormData, …) pass through untouched.

const camelCache = new Map<string, string>();
const snakeCache = new Map<string, string>();

function snakeToCamel(s: string): string {
  const hit = camelCache.get(s);
  if (hit !== undefined) return hit;
  const out = s.replace(/_([a-z0-9])/g, (_, c: string) => c.toUpperCase());
  camelCache.set(s, out);
  return out;
}

function camelToSnake(s: string): string {
  const hit = snakeCache.get(s);
  if (hit !== undefined) return hit;
  const out = s.replace(/[A-Z]/g, (c) => `_${c.toLowerCase()}`);
  snakeCache.set(s, out);
  return out;
}

function isPlainObject(x: unknown): x is Record<string, unknown> {
  return (
    !!x &&
    typeof x === "object" &&
    (Object.getPrototypeOf(x) === Object.prototype || Object.getPrototypeOf(x) === null)
  );
}

function snakeToCamelDeep(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(snakeToCamelDeep);
  if (!isPlainObject(value)) return value;
  const out: Record<string, unknown> = {};
  for (const k of Object.keys(value)) out[snakeToCamel(k)] = snakeToCamelDeep(value[k]);
  return out;
}

function camelToSnakeDeep(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(camelToSnakeDeep);
  if (!isPlainObject(value)) return value;
  const out: Record<string, unknown> = {};
  for (const k of Object.keys(value)) out[camelToSnake(k)] = camelToSnakeDeep(value[k]);
  return out;
}
