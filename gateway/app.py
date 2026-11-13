"""Gateway that calls the slow upstream in three modes: plain, timeout and hedged."""
import os
import time

import httpx
from fastapi import FastAPI, HTTPException, Query
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from starlette.responses import Response

from hedgekit import RetryBudget, RollingQuantile, hedged_call
from hedgekit.hedge import HedgeTimeout

UPSTREAM = os.getenv("UPSTREAM_URL", "http://upstream:8080/generate")
TIMEOUT_S = float(os.getenv("TIMEOUT_S", "2.0"))
HEDGE_QUANTILE = float(os.getenv("HEDGE_QUANTILE", "0.95"))
HEDGE_FLOOR_S = float(os.getenv("HEDGE_FLOOR_S", "0.05"))
BUDGET_RATIO = float(os.getenv("BUDGET_RATIO", "0.1"))

BUCKETS = (0.05, 0.1, 0.15, 0.2, 0.3, 0.5, 0.75, 1, 1.5, 2, 3, 5)
CALL_SECONDS = Histogram("call_seconds", "Time to answer one request", ["mode"], buckets=BUCKETS)
UPSTREAM_CALLS = Counter("upstream_calls_total", "Calls sent to the upstream", ["mode"])
HEDGES = Counter("hedges_total", "Extra attempts started", ["mode"])
HEDGE_WINS = Counter("hedge_wins_total", "Requests answered by an extra attempt", ["mode"])
BUDGET_DENIED = Counter("budget_denied_total", "Hedges skipped because the budget was empty", ["mode"])
TIMEOUTS = Counter("timeouts_total", "Requests that hit the overall timeout", ["mode"])
HEDGE_DELAY = Gauge("hedge_delay_seconds", "Current hedge delay")

app = FastAPI(title="hedging-gateway")
client = httpx.AsyncClient(timeout=httpx.Timeout(30.0), limits=httpx.Limits(max_connections=500))
budget = RetryBudget(ratio=BUDGET_RATIO)
recent = RollingQuantile(size=1000, default=0.3)


async def _one_call(mode: str) -> float:
    UPSTREAM_CALLS.labels(mode).inc()
    start = time.perf_counter()
    response = await client.post(UPSTREAM)
    response.raise_for_status()
    return time.perf_counter() - start


@app.get("/healthz")
async def healthz() -> dict:
    return {"ok": True}


@app.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/ask")
async def ask(mode: str = Query("hedged", pattern="^(plain|timeout|hedged)$")) -> dict:
    start = time.perf_counter()
    try:
        if mode == "plain":
            await _one_call(mode)
            attempts, hedged = 1, False
        else:
            delay = max(HEDGE_FLOOR_S, recent.quantile(HEDGE_QUANTILE))
            HEDGE_DELAY.set(delay)
            result = await hedged_call(
                lambda: _one_call(mode),
                delay=delay,
                timeout=TIMEOUT_S,
                max_attempts=2 if mode == "hedged" else 1,
                budget=budget if mode == "hedged" else None,
            )
            attempts, hedged = result.attempts, result.hedged
            if hedged:
                HEDGES.labels(mode).inc(attempts - 1)
                if result.winner > 1:
                    HEDGE_WINS.labels(mode).inc()
            if result.budget_denied:
                BUDGET_DENIED.labels(mode).inc()
    except HedgeTimeout:
        TIMEOUTS.labels(mode).inc()
        CALL_SECONDS.labels(mode).observe(time.perf_counter() - start)
        raise HTTPException(status_code=504, detail="timeout")
    elapsed = time.perf_counter() - start
    if mode != "plain":
        recent.add(elapsed)  # what callers experienced, so the delay stays near the true P95
    CALL_SECONDS.labels(mode).observe(elapsed)
    return {"mode": mode, "attempts": attempts, "seconds": round(elapsed, 4)}
