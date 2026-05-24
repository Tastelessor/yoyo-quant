"""Tests for regime detection and regime switch strategy."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.context.regime import detect_regime
from src.context.regime_switch import RegimeSwitchStrategy
from src.strategies.base import Strategy


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_trending_data() -> pd.DataFrame:
    """30 stocks, 60 days, all trending up strongly."""
    frames = []
    for i in range(1, 31):
        np.random.seed(i)
        close = 100 + np.cumsum(np.random.randn(60) * 0.3 + 0.5)
        frames.append(pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=60, freq="B"),
            "code": f"{i:06d}",
            "open": close - 0.1, "high": close + 0.3,
            "low": close - 0.3, "close": close,
            "volume": [1_000_000] * 60,
        }))
    return pd.concat(frames, ignore_index=True)


def _make_ranging_data() -> pd.DataFrame:
    """30 stocks, 60 days, independent random walks (no consensus)."""
    frames = []
    for i in range(1, 31):
        np.random.seed(i * 100)  # different seeds to decorrelate
        # Independent random walk with mean-reverting noise
        returns = np.random.randn(60) * 0.5
        close = 100 + np.cumsum(returns)
        frames.append(pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=60, freq="B"),
            "code": f"{i:06d}",
            "open": close - 0.1, "high": close + 0.3,
            "low": close - 0.3, "close": close,
            "volume": [1_000_000] * 60,
        }))
    return pd.concat(frames, ignore_index=True)


class _AlwaysBuyStrategy(Strategy):
    name = "always_buy"
    def generate_signal(self, data, factors=None):
        return pd.DataFrame({
            "date": data["date"], "code": data["code"],
            "signal": 1, "confidence": 0.5,
        })


class _AlwaysSellStrategy(Strategy):
    name = "always_sell"
    def generate_signal(self, data, factors=None):
        return pd.DataFrame({
            "date": data["date"], "code": data["code"],
            "signal": -1, "confidence": 0.5,
        })


# ---------------------------------------------------------------------------
# Tests: detect_regime
# ---------------------------------------------------------------------------

class TestDetectRegime:
    def test_returns_series(self) -> None:
        data = _make_trending_data()
        result = detect_regime(data)
        assert isinstance(result, pd.Series)

    def test_length_matches_dates(self) -> None:
        data = _make_trending_data()
        result = detect_regime(data)
        assert len(result) == data["date"].nunique()

    def test_values_in_domain(self) -> None:
        data = _make_trending_data()
        result = detect_regime(data)
        assert set(result.unique()).issubset({"trend_up", "trend_down", "range", "volatile"})

    def test_trending_data_likely_trend_up(self) -> None:
        data = _make_trending_data()
        result = detect_regime(data)
        trend_ratio = (result == "trend_up").mean()
        assert trend_ratio > 0.2, f"Expected >20% trend_up, got {trend_ratio:.1%}"

    def test_ranging_data_likely_range(self) -> None:
        data = _make_ranging_data()
        result = detect_regime(data)
        range_ratio = (result == "range").mean()
        assert range_ratio > 0.3, f"Expected >30% range, got {range_ratio:.1%}"

    def test_index_is_date(self) -> None:
        data = _make_trending_data()
        result = detect_regime(data)
        assert result.index[0] == data["date"].min()


# ---------------------------------------------------------------------------
# Tests: RegimeSwitchStrategy
# ---------------------------------------------------------------------------

class TestRegimeSwitchStrategy:
    def test_name(self) -> None:
        s = RegimeSwitchStrategy({"trend": _AlwaysBuyStrategy(), "range": _AlwaysSellStrategy()})
        assert s.name == "regime_switch"

    def test_returns_dataframe(self) -> None:
        data = _make_trending_data()
        s = RegimeSwitchStrategy({"trend": _AlwaysBuyStrategy(), "range": _AlwaysSellStrategy()})
        result = s.generate_signal(data)
        assert isinstance(result, pd.DataFrame)
        assert len(result) == len(data)

    def test_has_required_columns(self) -> None:
        data = _make_trending_data()
        s = RegimeSwitchStrategy({"trend": _AlwaysBuyStrategy(), "range": _AlwaysSellStrategy()})
        result = s.generate_signal(data)
        assert set(result.columns) == {"date", "code", "signal", "confidence"}

    def test_signal_values_valid(self) -> None:
        data = _make_trending_data()
        s = RegimeSwitchStrategy({"trend": _AlwaysBuyStrategy(), "range": _AlwaysSellStrategy()})
        result = s.generate_signal(data)
        assert set(result["signal"].unique()).issubset({-1, 0, 1})

    def test_uses_fallback_when_regime_missing(self) -> None:
        data = _make_trending_data()
        # Only provide "trend_up" strategy, no "range" — should use fallback
        s = RegimeSwitchStrategy({"trend_up": _AlwaysBuyStrategy()})
        result = s.generate_signal(data)
        assert isinstance(result, pd.DataFrame)
        assert len(result) == len(data)
