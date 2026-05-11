// `@tythe/ts` — the tiny zero-dep runtime the generated `client.ts` imports.
// Static typing lives in the generated `.d.ts`; this file only does plumbing.

export { createClient } from "./client.js";
export { parseSSE } from "./sse.js";
export type {
  CallOptions,
  ClientConfig,
  Err,
  HttpMethod,
  Ok,
  ParamDescriptor,
  ParamLocation,
  Result,
  RouteDescriptor,
} from "./types.js";
