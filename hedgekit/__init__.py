"""hedgekit: timeouts, hedged requests and a retry budget for slow calls."""
from .budget import RetryBudget
from .hedge import HedgeResult, hedged_call
from .window import RollingQuantile

__all__ = ["HedgeResult", "RetryBudget", "RollingQuantile", "hedged_call"]
