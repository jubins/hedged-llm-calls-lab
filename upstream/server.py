"""A slow upstream that behaves like a busy model endpoint.

Most calls take about MEDIAN_MS. A small share (STALL_RATE) stalls for much longer.
Each call is independent, so a second copy of a stalled call usually finishes fast.
"""
import asyncio
import math
import os
import random

from fastapi import FastAPI

MEDIAN_MS = float(os.getenv("MEDIAN_MS", "120"))
SIGMA = float(os.getenv("SIGMA", "0.35"))
STALL_RATE = float(os.getenv("STALL_RATE", "0.02"))
STALL_MIN_MS = float(os.getenv("STALL_MIN_MS", "1500"))
STALL_MAX_MS = float(os.getenv("STALL_MAX_MS", "3500"))

app = FastAPI(title="slow-upstream")


def sample_ms(rng: random.Random = random) -> float:
    if rng.random() < STALL_RATE:
        return rng.uniform(STALL_MIN_MS, STALL_MAX_MS)
    return rng.lognormvariate(math.log(MEDIAN_MS), SIGMA)


@app.get("/healthz")
async def healthz() -> dict:
    return {"ok": True}


@app.post("/generate")
async def generate() -> dict:
    ms = sample_ms()
    await asyncio.sleep(ms / 1000)
    return {"text": "ok", "upstream_ms": round(ms, 1)}
