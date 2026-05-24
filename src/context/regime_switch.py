"""Regime switch strategy: routes to different strategies based on market regime."""

from __future__ import annotations

import pandas as pd

from src.context.regime import detect_regime
from src.strategies.base import Strategy


class RegimeSwitchStrategy(Strategy):
    """Selects a strategy based on the detected market regime.

    Parameters
    ----------
    regimes : dict[str, Strategy]
        Mapping from regime label to strategy.
        Supported keys: "trend", "range", "neutral".
        If a regime is missing, signals are zero (hold).
    """

    def __init__(self, regimes: dict[str, Strategy]):
        self.regimes = regimes

    @property
    def name(self) -> str:
        return "regime_switch"

    def generate_signal(
        self, data: pd.DataFrame, factors: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        regime_series = detect_regime(data)

        all_signals = []
        for date, regime in regime_series.items():
            day_data = data[data["date"] == date].copy()
            if day_data.empty:
                continue

            strategy = self.regimes.get(regime)
            if strategy is None:
                # No strategy for this regime → hold
                sig = pd.DataFrame({
                    "date": day_data["date"],
                    "code": day_data["code"],
                    "signal": 0,
                    "confidence": 0.0,
                })
            else:
                sig = strategy.generate_signal(day_data, factors=factors)

            all_signals.append(sig)

        if not all_signals:
            return pd.DataFrame(
                columns=["date", "code", "signal", "confidence"],
            )

        return pd.concat(all_signals, ignore_index=True)
