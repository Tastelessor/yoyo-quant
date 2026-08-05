"""RSI mean-reversion strategy."""

from __future__ import annotations

import pandas as pd

from src.factors.registry import run_factor
from src.strategies.base import Strategy
from src.strategies.registry import register_strategy


@register_strategy("rsi_reversal")
class RSIReversalStrategy(Strategy):
    """Buy when RSI is oversold, sell when overbought."""

    name = "rsi_reversal"

    def __init__(
        self,
        window: int = 14,
        oversold: float = 30,
        overbought: float = 70,
    ):
        self.window = window
        self.oversold = oversold
        self.overbought = overbought

    def generate_signal(self, data, factors=None):
        if factors is not None and "rsi" in factors.columns:
            rsi = factors["rsi"].values
        else:
            rsi = run_factor("calc_rsi", data, window=self.window).values

        signal = pd.Series(0, index=data.index, dtype=int)
        signal[rsi < self.oversold] = 1
        signal[rsi > self.overbought] = -1

        confidence = (pd.Series(rsi, index=data.index) - 50).abs() / 50
        confidence = confidence.clip(upper=1.0)
        # NaN where RSI is NaN (insufficient window)
        confidence = confidence.fillna(0.0)

        return pd.DataFrame(
            {
                "date": data["date"],
                "code": data["code"],
                "signal": signal,
                "confidence": confidence,
            }
        )
