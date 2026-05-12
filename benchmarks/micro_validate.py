"""Microbench: body validation hot path, isolated from HTTP.

Measures the cost Tythe pays to turn raw JSON bytes into a typed body
struct, comparing the fast path (one-shot ``msgspec.json.Decoder(T)``)
against the legacy two-pass (``msgspec.json.decode`` → ``msgspec.convert``).

Running this away from uvicorn / loopback isolates the framework cost so
the optimization is visible even at small payload sizes.

Usage::

    uv run micro_validate.py            # default 100k iterations
    uv run micro_validate.py --iter 1000000
"""

# pyright: basic

from __future__ import annotations

import argparse
import statistics
import time
from typing import Any

import msgspec


class EchoIn(msgspec.Struct):
    text: str


class NestedItem(msgspec.Struct):
    id: int
    name: str
    tags: list[str]


class NestedBody(msgspec.Struct):
    title: str
    items: list[NestedItem]
    flags: dict[str, bool]


def _fast(decoder: msgspec.json.Decoder[Any], raw: bytes) -> Any:
    """One-shot bytes → typed struct (the new hot path)."""
    return decoder.decode(raw)


def _legacy(raw: bytes, t: type[Any]) -> Any:
    """Two-pass bytes → dict → typed struct (the previous hot path)."""
    obj = msgspec.json.decode(raw)
    return msgspec.convert(obj, type=t, strict=False)


def _bench(label: str, fn: Any, iters: int) -> float:
    # Warmup.
    for _ in range(min(iters // 10, 1000)):
        fn()
    samples: list[float] = []
    for _ in range(5):
        t0 = time.perf_counter()
        for _ in range(iters):
            fn()
        samples.append((time.perf_counter() - t0) * 1e6 / iters)  # μs per call
    best = min(samples)
    median = statistics.median(samples)
    print(f"  {label:<24} best={best:>7.3f} μs  median={median:>7.3f} μs")
    return best


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iter", type=int, default=100_000)
    args = parser.parse_args()

    print(f"# microbench — {args.iter:,} iterations per row\n")

    print("Small payload (single string field):")
    small = b'{"text":"hello world"}'
    decoder_small: msgspec.json.Decoder[EchoIn] = msgspec.json.Decoder(EchoIn)
    fast_small = _bench("fast (typed Decoder)", lambda: _fast(decoder_small, small), args.iter)
    legacy_small = _bench("legacy (decode+convert)", lambda: _legacy(small, EchoIn), args.iter)
    print(f"  → fast is {legacy_small / fast_small:.2f}x the throughput\n")

    print("Nested payload (50 items, tags, flags):")
    items = [{"id": i, "name": f"item-{i}", "tags": ["a", "b", "c"]} for i in range(50)]
    nested = msgspec.json.encode({"title": "demo", "items": items, "flags": {"x": True, "y": False}})
    decoder_nested: msgspec.json.Decoder[NestedBody] = msgspec.json.Decoder(NestedBody)
    fast_nested = _bench("fast (typed Decoder)", lambda: _fast(decoder_nested, nested), args.iter)
    legacy_nested = _bench("legacy (decode+convert)", lambda: _legacy(nested, NestedBody), args.iter)
    print(f"  → fast is {legacy_nested / fast_nested:.2f}x the throughput")


if __name__ == "__main__":
    main()
