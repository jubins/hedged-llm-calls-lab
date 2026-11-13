"""Hedged calls: start a second attempt when the first one is slower than usual."""
from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from .budget import RetryBudget


@dataclass
class HedgeResult:
    value: Any
    attempts: int          # how many attempts were started
    winner: int            # 1 for the first attempt, 2 for the first hedge, and so on
    seconds: float
    hedged: bool           # True when at least one extra attempt was started
    budget_denied: bool    # True when a hedge was due but the budget was empty


class HedgeTimeout(Exception):
    """Raised when no attempt finished inside the overall timeout."""


async def hedged_call(
    call: Callable[[], Awaitable[Any]],
    *,
    delay: float,
    timeout: float,
    max_attempts: int = 2,
    budget: RetryBudget | None = None,
) -> HedgeResult:
    """Run `call`, and start another copy if no answer arrives within `delay` seconds.

    The first attempt to finish wins and the others are cancelled. If an attempt
    raises, the next one starts at once, still limited by `max_attempts` and the budget.
    `call` must be safe to run more than once (read-only or idempotent).
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    start = time.perf_counter()
    deadline = start + timeout
    tasks: dict[asyncio.Task, int] = {}
    denied = False
    last_error: BaseException | None = None

    def launch() -> None:
        tasks[asyncio.ensure_future(call())] = len(tasks) + 1

    if budget is not None:
        budget.deposit()
    launch()
    try:
        while True:
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                raise HedgeTimeout(f"no result within {timeout:.2f}s")
            can_hedge = len(tasks) < max_attempts
            wait_for = min(delay, remaining) if can_hedge else remaining
            pending = {t for t in tasks if not t.done()}
            done, _ = await asyncio.wait(
                pending, timeout=wait_for, return_when=asyncio.FIRST_COMPLETED
            ) if pending else (set(), set())
            for task in done:
                if task.exception() is None:
                    return HedgeResult(
                        value=task.result(),
                        attempts=len(tasks),
                        winner=tasks[task],
                        seconds=time.perf_counter() - start,
                        hedged=len(tasks) > 1,
                        budget_denied=denied,
                    )
                last_error = task.exception()
            failed_all = not any(not t.done() for t in tasks)
            if can_hedge and (failed_all or not done):
                if budget is None or budget.try_spend():
                    launch()
                else:
                    denied = True
                    if failed_all:
                        raise last_error  # type: ignore[misc]
            elif failed_all:
                raise last_error  # type: ignore[misc]
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
