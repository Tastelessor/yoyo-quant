"""Reversed strategy wrapper: flips buy/sell signals of any strategy."""

from __future__ import annotations

import pandas as pd

from strategies.base import Strategy


class ReversedStrategy(Strategy):
    """Wrapper that reverses another strategy's signals.

    buy → sell, sell → buy, hold → hold.
    Useful when a strategy's signals are consistently inverted
    (e.g., mean reversion in a momentum-dominant market).
    """

    def __init__(self, strategy: Strategy):
        self._strategy = strategy

    @property
    def name(self) -> str:
        return f"reversed_{self._strategy.name}"

    def generate_signal(
        self, data: pd.DataFrame, factors: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        sig = self._strategy.generate_signal(data, factors=factors)
        result = sig.copy()
        result["signal"] = -result["signal"]
        return result
