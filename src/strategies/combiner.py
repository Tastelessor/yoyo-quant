"""Signal combiners: weighted vote and filter-based."""

from __future__ import annotations

import pandas as pd

from strategies.base import Strategy


class WeightedVoteCombiner:
    """Combine signals from multiple strategies via weighted voting.

    Each strategy produces a signal in {-1, 0, 1} with a confidence.
    The weighted sum determines the final signal:
        sum > threshold  → buy  (1)
        sum < -threshold → sell (-1)
        otherwise        → hold (0)
    """

    def __init__(
        self,
        strategies: list[tuple[Strategy, float]],
        threshold: float = 0.0,
    ):
        self.strategies = strategies
        self.threshold = threshold

    def combine(
        self, data: pd.DataFrame, factors: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        if not self.strategies:
            raise ValueError("WeightedVoteCombiner requires at least one strategy")

        weighted_signals = None
        weighted_confidence = None
        total_weight = sum(w for _, w in self.strategies)

        for strategy, weight in self.strategies:
            sig = strategy.generate_signal(data, factors=factors)
            if len(sig) != len(data):
                raise ValueError(
                    f"Strategy {strategy.name!r} returned {len(sig)} rows, "
                    f"expected {len(data)}"
                )
            ws = sig["signal"].values * weight
            wc = sig["confidence"].values * weight
            if weighted_signals is None:
                weighted_signals = ws
                weighted_confidence = wc
            else:
                weighted_signals = weighted_signals + ws
                weighted_confidence = weighted_confidence + wc

        # Normalize by total weight
        weighted_signals = weighted_signals / total_weight
        weighted_confidence = weighted_confidence / total_weight

        # Convert to discrete signal
        final_signal = pd.Series(0, index=data.index, dtype=int)
        final_signal[weighted_signals > self.threshold] = 1
        final_signal[weighted_signals < -self.threshold] = -1

        return pd.DataFrame(
            {
                "date": data["date"],
                "code": data["code"],
                "signal": final_signal,
                "confidence": pd.Series(weighted_confidence).clip(upper=1.0),
            }
        )


class FilterCombiner:
    """Combine a primary strategy with filter strategies.

    The primary strategy determines signal direction.
    Filter strategies act as gates — if any filter produces signal=0,
    the final signal is zeroed out.

    Agreement means "non-zero", not "same direction". A filter returning
    signal=1 while the primary returns signal=-1 is considered agreement
    (both want to act). Use WeightedVoteCombiner if directional consensus
    is needed.
    """

    def __init__(self, primary: Strategy, filters: list[Strategy]):
        self.primary = primary
        self.filters = filters

    def combine(
        self, data: pd.DataFrame, factors: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        primary_sig = self.primary.generate_signal(data, factors=factors)

        if not self.filters:
            return primary_sig

        # All filters must agree (non-zero) for the signal to pass
        mask = pd.Series(True, index=data.index)
        for f in self.filters:
            f_sig = f.generate_signal(data, factors=factors)
            mask = mask & (f_sig["signal"] != 0)

        result = primary_sig.copy()
        result.loc[~mask, "signal"] = 0
        result.loc[~mask, "confidence"] = 0.0
        return result
