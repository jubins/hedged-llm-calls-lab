import asyncio

import pytest

from hedgekit import RetryBudget, RollingQuantile, hedged_call
from hedgekit.hedge import HedgeTimeout


def sequence(delays, fail=()):
    """Return a call() whose n-th run sleeps delays[n] and fails if n is in fail."""
    state = {"n": 0, "cancelled": 0}

    async def call():
        i = state["n"]
        state["n"] += 1
        try:
            await asyncio.sleep(delays[min(i, len(delays) - 1)])
        except asyncio.CancelledError:
            state["cancelled"] += 1
            raise
        if i in fail:
            raise RuntimeError("boom")
        return i

    call.state = state
    return call


async def test_fast_call_is_not_hedged():
    call = sequence([0.01])
    result = await hedged_call(call, delay=0.1, timeout=1)
    assert result.attempts == 1 and not result.hedged and result.value == 0


async def test_slow_first_attempt_loses_to_hedge():
    call = sequence([0.5, 0.01])
    result = await hedged_call(call, delay=0.05, timeout=1)
    assert result.hedged and result.winner == 2 and result.value == 1
    assert result.seconds < 0.3
    await asyncio.sleep(0.01)
    assert call.state["cancelled"] == 1  # the slow loser was cancelled


async def test_first_attempt_can_still_win_after_hedge():
    call = sequence([0.12, 0.5])
    result = await hedged_call(call, delay=0.05, timeout=1)
    assert result.hedged and result.winner == 1


async def test_error_starts_next_attempt_at_once():
    call = sequence([0.01, 0.01], fail={0})
    result = await hedged_call(call, delay=5, timeout=1)
    assert result.value == 1 and result.attempts == 2


async def test_error_with_no_attempts_left_is_raised():
    call = sequence([0.01], fail={0})
    with pytest.raises(RuntimeError):
        await hedged_call(call, delay=5, timeout=1, max_attempts=1)


async def test_overall_timeout():
    call = sequence([2.0])
    with pytest.raises(HedgeTimeout):
        await hedged_call(call, delay=0.05, timeout=0.2)


async def test_max_attempts_one_never_hedges():
    call = sequence([0.2])
    result = await hedged_call(call, delay=0.01, timeout=1, max_attempts=1)
    assert result.attempts == 1


async def test_empty_budget_skips_hedge():
    budget = RetryBudget(ratio=0.0, max_tokens=0.0)
    call = sequence([0.15, 0.01])
    result = await hedged_call(call, delay=0.03, timeout=1, budget=budget)
    assert not result.hedged and result.budget_denied


def test_budget_limits_share_of_extra_calls():
    budget = RetryBudget(ratio=0.1, max_tokens=1.0)
    budget.try_spend()  # drain the starting token
    spent = 0
    for _ in range(1000):
        budget.deposit()
        if budget.try_spend():
            spent += 1
    assert 95 <= spent <= 105


def test_budget_rejects_bad_ratio():
    with pytest.raises(ValueError):
        RetryBudget(ratio=2)


def test_rolling_quantile_uses_default_until_warm():
    w = RollingQuantile(size=100, default=0.3)
    assert w.quantile(0.95) == 0.3
    for i in range(100):
        w.add(i / 100)
    assert 0.9 <= w.quantile(0.95) <= 0.99
