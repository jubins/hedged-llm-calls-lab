"""Measure plain, timeout-only and hedged calls against a simulated slow upstream.

Runs in one process with no network. Time is real but scaled, so 120 ms of
upstream latency becomes 12 ms here. Results are reported in unscaled seconds.

    python scripts/simulate.py --requests 20000 --concurrency 200 --scale 0.1
"""
from __future__ import annotations

import argparse
import asyncio
import math
import random
import time

from hedgekit import RetryBudget, RollingQuantile, hedged_call
from hedgekit.hedge import HedgeTimeout


def pct(values, q):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


async def run(mode, n, concurrency, scale, seed, median=0.120, sigma=0.35, stall=0.02, timeout=2.0):
    rng = random.Random(seed)
    sem = asyncio.Semaphore(concurrency)
    budget = RetryBudget(ratio=0.1)
    recent = RollingQuantile(size=1000, default=0.3)
    latencies, upstream_calls, timeouts, hedges, wins = [], 0, 0, 0, 0

    async def upstream():
        nonlocal upstream_calls
        upstream_calls += 1
        s = rng.uniform(1.5, 3.5) if rng.random() < stall else rng.lognormvariate(math.log(median), sigma)
        await asyncio.sleep(s * scale)

    async def one():
        nonlocal timeouts, hedges, wins
        async with sem:
            t0 = time.perf_counter()
            try:
                if mode == "plain":
                    await upstream()
                else:
                    delay = max(0.05, recent.quantile(0.95)) * scale
                    r = await hedged_call(
                        upstream, delay=delay, timeout=timeout * scale,
                        max_attempts=2 if mode == "hedged" else 1,
                        budget=budget if mode == "hedged" else None,
                    )
                    if r.hedged:
                        hedges += r.attempts - 1
                        wins += r.winner > 1
                    recent.add((time.perf_counter() - t0) / scale)
            except HedgeTimeout:
                timeouts += 1
            latencies.append((time.perf_counter() - t0) / scale)

    await asyncio.gather(*(one() for _ in range(n)))
    return {
        "mode": mode, "p50": pct(latencies, 0.50), "p95": pct(latencies, 0.95),
        "p99": pct(latencies, 0.99), "p999": pct(latencies, 0.999),
        "extra_calls_pct": 100 * (upstream_calls - n) / n,
        "hedge_wins": wins, "timeouts": timeouts,
    }


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--requests", type=int, default=20000)
    ap.add_argument("--concurrency", type=int, default=200)
    ap.add_argument("--scale", type=float, default=0.1)
    ap.add_argument("--seed", type=int, default=11)
    a = ap.parse_args()
    print(f"{'mode':8} {'P50':>7} {'P95':>7} {'P99':>7} {'P99.9':>7} {'extra calls':>12} {'timeouts':>9}")
    for mode in ("plain", "timeout", "hedged"):
        r = await run(mode, a.requests, a.concurrency, a.scale, a.seed)
        print(f"{r['mode']:8} {r['p50']:6.2f}s {r['p95']:6.2f}s {r['p99']:6.2f}s {r['p999']:6.2f}s "
              f"{r['extra_calls_pct']:11.1f}% {r['timeouts']:9d}")


if __name__ == "__main__":
    asyncio.run(main())
