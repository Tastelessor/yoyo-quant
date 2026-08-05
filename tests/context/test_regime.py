"""Tests for regime detection and regime switch strategy."""

from __future__ import annotations

import numpy as np
import pandas as pd

from context.regime import detect_regime
from context.regime_switch import RegimeSwitchStrategy
from strategies.base import Strategy

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


def _make_strong_uptrend() -> pd.DataFrame:
    """30 stocks, 120 days, all trending up with strong drift."""
    frames = []
    for i in range(1, 31):
        np.random.seed(i + 500)
        close = 100 + np.cumsum(np.random.randn(120) * 0.2 + 0.8)
        frames.append(pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=120, freq="B"),
            "code": f"{i:06d}",
            "open": close - 0.1, "high": close + 0.3,
            "low": close - 0.3, "close": close,
            "volume": [1_000_000] * 120,
        }))
    return pd.concat(frames, ignore_index=True)


def _make_strong_downtrend() -> pd.DataFrame:
    """30 stocks, 120 days, all trending down."""
    frames = []
    for i in range(1, 31):
        np.random.seed(i + 600)
        close = 200 + np.cumsum(np.random.randn(120) * 0.2 - 0.8)
        frames.append(pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=120, freq="B"),
            "code": f"{i:06d}",
            "open": close + 0.1, "high": close + 0.3,
            "low": close - 0.3, "close": close,
            "volume": [1_000_000] * 120,
        }))
    return pd.concat(frames, ignore_index=True)


def _make_volatile_data() -> pd.DataFrame:
    """30 stocks, 120 days, alternating calm and wild periods."""
    frames = []
    for i in range(1, 31):
        np.random.seed(i + 700)
        # 60 days calm (std=0.3), then 60 days wild (std=2.5)
        ret_calm = np.random.randn(60) * 0.3
        ret_wild = np.random.randn(60) * 2.5
        returns = np.concatenate([ret_calm, ret_wild])
        close = 100 + np.cumsum(returns)
        frames.append(pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=120, freq="B"),
            "code": f"{i:06d}",
            "open": close - 0.5, "high": close + 1.0,
            "low": close - 1.0, "close": close,
            "volume": [1_000_000] * 120,
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
    """Tests use ema_span=0, min_persistence=1 to test classification logic
    without smoothing (synthetic data is too short for default smoothing)."""

    def test_returns_series(self) -> None:
        data = _make_trending_data()
        result = detect_regime(data, ema_span=0, min_persistence=1)
        assert isinstance(result, pd.Series)

    def test_length_matches_dates(self) -> None:
        data = _make_trending_data()
        result = detect_regime(data, ema_span=0, min_persistence=1)
        assert len(result) == data["date"].nunique()

    def test_values_in_domain(self) -> None:
        data = _make_trending_data()
        result = detect_regime(data, ema_span=0, min_persistence=1)
        assert set(result.unique()).issubset({"trend_up", "trend_down", "range", "volatile"})

    def test_trending_data_likely_trend_up(self) -> None:
        data = _make_trending_data()
        result = detect_regime(data, ema_span=0, min_persistence=1)
        trend_ratio = (result == "trend_up").mean()
        assert trend_ratio > 0.2, f"Expected >20% trend_up, got {trend_ratio:.1%}"

    def test_ranging_data_likely_range(self) -> None:
        data = _make_ranging_data()
        result = detect_regime(data, ema_span=0, min_persistence=1)
        range_ratio = (result == "range").mean()
        assert range_ratio > 0.3, f"Expected >30% range, got {range_ratio:.1%}"

    def test_index_is_date(self) -> None:
        data = _make_trending_data()
        result = detect_regime(data, ema_span=0, min_persistence=1)
        assert result.index[0] == data["date"].min()

    # --- New tests for improved regime detection ---

    def test_strong_uptrend_dominantly_trend_up(self) -> None:
        data = _make_strong_uptrend()
        result = detect_regime(data, ema_span=0, min_persistence=1)
        later = result.iloc[20:]
        trend_up_ratio = (later == "trend_up").mean()
        assert trend_up_ratio > 0.3, f"Expected >30% trend_up, got {trend_up_ratio:.1%}"

    def test_strong_downtrend_dominantly_trend_down(self) -> None:
        data = _make_strong_downtrend()
        result = detect_regime(data, ema_span=0, min_persistence=1)
        later = result.iloc[20:]
        trend_down_ratio = (later == "trend_down").mean()
        assert trend_down_ratio > 0.3, f"Expected >30% trend_down, got {trend_down_ratio:.1%}"

    def test_volatile_data_has_volatile_or_range(self) -> None:
        data = _make_volatile_data()
        result = detect_regime(data, ema_span=0, min_persistence=1)
        second_half = result.iloc[60:]
        non_trend = ((second_half == "volatile") | (second_half == "range")).mean()
        assert non_trend > 0.3, f"Expected >30% volatile/range in high-vol period, got {non_trend:.1%}"

    def test_regime_not_all_same(self) -> None:
        """Ranging data should produce mixed regimes, not all one label."""
        data = _make_ranging_data()
        result = detect_regime(data, ema_span=0, min_persistence=1)
        assert result.nunique() > 1, "Regime should vary, not be constant"

    def test_trending_more_trend_up_than_ranging(self) -> None:
        """Trending data should have more trend_up than ranging data."""
        trend_data = _make_strong_uptrend()
        range_data = _make_ranging_data()
        trend_result = detect_regime(trend_data, ema_span=0, min_persistence=1)
        range_result = detect_regime(range_data, ema_span=0, min_persistence=1)
        t_ratio = (trend_result.iloc[20:] == "trend_up").mean()
        r_ratio = (range_result.iloc[20:] == "trend_up").mean()
        assert t_ratio > r_ratio, (
            f"Uptrend ({t_ratio:.1%}) should have more trend_up than ranging ({r_ratio:.1%})"
        )

    def test_no_nan_in_output(self) -> None:
        data = _make_trending_data()
        result = detect_regime(data, ema_span=0, min_persistence=1)
        assert not result.isna().any(), "Regime output should have no NaN"

    def test_sorted_by_date(self) -> None:
        data = _make_trending_data()
        result = detect_regime(data, ema_span=0, min_persistence=1)
        assert result.index.is_monotonic_increasing, "Regime index should be sorted by date"

    def test_default_params_use_smoothing(self) -> None:
        """Default params should produce smoother output than raw."""
        data = _make_strong_uptrend()
        raw = detect_regime(data, ema_span=0, min_persistence=1)
        smooth = detect_regime(data)  # defaults: ema_span=5, min_persistence=7
        raw_trans = (raw != raw.shift()).sum()
        smooth_trans = (smooth != smooth.shift()).sum()
        assert smooth_trans <= raw_trans, (
            f"Smoothed ({smooth_trans}) should have <= transitions than raw ({raw_trans})"
        )


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
