// Type-level helpers for `createTytheHooks`. The hooks accept the literal
// method name on `api` and derive args / data / error / event types from the
// signature TypeScript already knows about — no runtime reflection.
//
// `DataOf<F>` and `ErrorOf<F>` are the function-level cousins of `@tythe/ts`'s
// `Ok<R>` and `Err<R>`. The difference: these unwrap the *function's* return
// type, and they fall through to the raw payload for routes that don't carry
// a `Result<…>` envelope (i.e. routes without `@raises(...)`).

import type { Result } from "@tythe/ts";

// eslint-disable-next-line @typescript-eslint/no-explicit-any -- generic over arbitrary callables
type AnyFn = (...args: any[]) => any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any -- match every function shape
type FirstArg<F> = F extends (a: infer A, ...rest: any[]) => unknown ? A : void;

export type UnaryKeys<TApi> = {
  [K in keyof TApi]: TApi[K] extends AnyFn
    ? ReturnType<TApi[K]> extends Promise<unknown>
      ? K
      : never
    : never;
}[keyof TApi];

export type StreamKeys<TApi> = {
  [K in keyof TApi]: TApi[K] extends AnyFn
    ? ReturnType<TApi[K]> extends AsyncIterable<unknown>
      ? K
      : never
    : never;
}[keyof TApi];

// Arg-less endpoints get `(opts?: CallOptions)` as their first param in the
// generated client. Detect that shape and surface `void` so the hook signature
// reads `useQuery("ping", undefined)` instead of leaking CallOptions.
type IsCallOptionsLike<T> = [T] extends [undefined]
  ? true
  : [Exclude<keyof NonNullable<T>, "signal" | "headers">] extends [never]
    ? true
    : false;

export type ArgsOf<F> = IsCallOptionsLike<FirstArg<F>> extends true ? void : FirstArg<F>;

// Two-stage to force distribution over union members. See the matching note in
// `@tythe/ts/src/types.ts` for the same pattern on `Ok` / `Err`.
type DataOfResolved<X> = X extends Result<infer T, unknown> ? T : X;
type ErrorOfResolved<X> = X extends Result<unknown, infer E> ? E : Error;

export type DataOf<F> = F extends AnyFn ? DataOfResolved<Awaited<ReturnType<F>>> : never;
export type ErrorOf<F> = F extends AnyFn ? ErrorOfResolved<Awaited<ReturnType<F>>> : Error;

export type StreamItemOf<F> = F extends AnyFn
  ? ReturnType<F> extends AsyncIterable<infer I>
    ? I
    : never
  : never;

export type SubscriptionStatus = "idle" | "connecting" | "open" | "closed" | "error";
