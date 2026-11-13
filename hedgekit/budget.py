"""A retry budget: extra attempts may use at most a fixed share of normal traffic."""
from __future__ import annotations


class RetryBudget:
    """Token bucket where every request earns a little and every extra attempt spends one.

    With ratio=0.1, ten requests earn one token, so hedging can add at most
    about 10% more calls to the upstream service.
    """

    def __init__(self, ratio: float = 0.1, max_tokens: float = 10.0) -> None:
        if not 0 <= ratio <= 1:
            raise ValueError("ratio must be between 0 and 1")
        self.ratio = ratio
        self.max_tokens = max_tokens
        self._tokens = max_tokens

    @property
    def tokens(self) -> float:
        return self._tokens

    def deposit(self) -> None:
        """Call once for every first attempt."""
        self._tokens = min(self.max_tokens, self._tokens + self.ratio)

    def try_spend(self) -> bool:
        """Call before every extra attempt. Returns False when the budget is empty."""
        if self._tokens >= 1.0 - 1e-9:
            self._tokens -= 1.0
            return True
        return False
