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
        data = data.sort_values(["code", "date"]).reset_index(drop=True)

        all_signals = []
        for date, regime in regime_series.items():
            # Pass all data up to and including this date (for lookback)
            hist_data = data[data["date"] <= date].copy()

            strategy = self.regimes.get(regime)
            if strategy is None:
                # No strategy for this regime → hold
                day_codes = data[data["date"] == date]["code"]
                sig = pd.DataFrame({
                    "date": date,
                    "code": day_codes.values,
                    "signal": 0,
                    "confidence": 0.0,
                })
            else:
                full_sig = strategy.generate_signal(hist_data, factors=factors)
                # Keep only the signal for this date
                sig = full_sig[full_sig["date"] == date].copy()

            all_signals.append(sig)

        if not all_signals:
            return pd.DataFrame(
                columns=["date", "code", "signal", "confidence"],
            )

        return pd.concat(all_signals, ignore_index=True)
