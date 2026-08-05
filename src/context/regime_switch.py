"""Regime switch strategy: routes to different strategies based on market regime.

Supports confirmation lag to filter out rapid regime flips that cause
whipsaw costs (validated 2026-05-26: 46 flips / 2426 days without lag).
"""

from __future__ import annotations

import pandas as pd

from context.regime import detect_regime
from strategies.base import Strategy


class RegimeSwitchStrategy(Strategy):
    """Selects a strategy based on the detected market regime.

    Parameters
    ----------
    regimes : dict[str, Strategy]
        Mapping from regime label to strategy.
        If a regime is missing, signals are zero (hold).
    confirmation_lag : int
        Number of trading days to wait before confirming a regime change.
        Prevents whipsaw from rapid regime flips. Default 10 (empirically
        validated: 46→32 flips, MaxDD -3.5% vs no lag).
    """

    def __init__(
        self,
        regimes: dict[str, Strategy],
        confirmation_lag: int = 10,
    ):
        self.regimes = regimes
        self.confirmation_lag = confirmation_lag

    @property
    def name(self) -> str:
        return "regime_switch"

    def generate_signal(
        self, data: pd.DataFrame, factors: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        regime_series = detect_regime(data)
        data = data.sort_values(["code", "date"]).reset_index(drop=True)

        # Apply confirmation lag: only switch after N consecutive days of new regime
        if self.confirmation_lag > 0:
            regime_series = _apply_confirmation_lag(regime_series, self.confirmation_lag)

        all_signals = []
        for date, regime in regime_series.items():
            hist_data = data[data["date"] <= date].copy()

            strategy = self.regimes.get(regime)
            if strategy is None:
                day_codes = data[data["date"] == date]["code"]
                sig = pd.DataFrame({
                    "date": date,
                    "code": day_codes.values,
                    "signal": 0,
                    "confidence": 0.0,
                })
            else:
                full_sig = strategy.generate_signal(hist_data, factors=factors)
                sig = full_sig[full_sig["date"] == date].copy()

            all_signals.append(sig)

        if not all_signals:
            return pd.DataFrame(
                columns=["date", "code", "signal", "confidence"],
            )

        return pd.concat(all_signals, ignore_index=True)


def _apply_confirmation_lag(
    regime_series: pd.Series, lag: int,
) -> pd.Series:
    """Delay regime switches until confirmed for *lag* consecutive days.

    A regime change is only applied after the new regime has persisted
    for *lag* consecutive trading days. During the confirmation period,
    the previous confirmed regime is used.

    Parameters
    ----------
    regime_series : Series
        Index: dates. Values: regime labels.
    lag : int
        Confirmation lag in trading days.

    Returns
    -------
    Series
        Lagged regime series, same index as input.
    """
    if lag <= 0 or len(regime_series) <= 1:
        return regime_series

    labels = regime_series.values
    dates = regime_series.index
    result = labels.copy()
    confirmed = labels[0]  # initial confirmed regime
    pending_regime = None
    pending_start = 0

    for i in range(len(labels)):
        current = labels[i]

        if pending_regime is not None:
            if current == pending_regime:
                # Same pending regime continues
                days_in_pending = i - pending_start
                if days_in_pending >= lag:
                    confirmed = pending_regime
                    pending_regime = None
                    pending_start = 0
                # else: still pending, use old confirmed
            else:
                # Regime changed again during confirmation → reset pending
                pending_regime = current
                pending_start = i
        elif current != confirmed:
            # New regime detected → start confirmation
            pending_regime = current
            pending_start = i

        result[i] = confirmed

    return pd.Series(result, index=dates)
