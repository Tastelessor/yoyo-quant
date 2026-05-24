"""Tests for GTJA momentum strategy."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.strategies.builtin.gtja_momentum import (
    GTJAMomentumStrategy,
    gtja_momentum_signal,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def trending_up() -> pd.DataFrame:
    """30 stocks, 60 days, all trending up — should produce buy signals."""
    codes = [f"{i:06d}.SZ" for i in range(1, 31)]
    frames = []
    for code in codes:
        np.random.seed(hash(code) % 2**31)
        close = 100 + np.cumsum(np.random.randn(60) * 0.3 + 0.2)
        frames.append(pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=60, freq="B"),
            "code": code,
            "open": close - 0.1,
            "high": close + 0.3,
            "low": close - 0.3,
            "close": close,
            "volume": np.random.randint(1_000_000, 5_000_000, 60),
        }))
    return pd.concat(frames, ignore_index=True)


@pytest.fixture
def trending_down() -> pd.DataFrame:
    """30 stocks, 60 days, all trending down — should produce sell signals."""
    codes = [f"{i:06d}.SZ" for i in range(1, 31)]
    frames = []
    for code in codes:
        np.random.seed(hash(code) % 2**31)
        close = 100 + np.cumsum(np.random.randn(60) * 0.3 - 0.2)
        frames.append(pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=60, freq="B"),
            "code": code,
            "open": close + 0.1,
            "high": close + 0.3,
            "low": close - 0.3,
            "close": close,
            "volume": np.random.randint(1_000_000, 5_000_000, 60),
        }))
    return pd.concat(frames, ignore_index=True)


@pytest.fixture
def mixed_trend() -> pd.DataFrame:
    """30 stocks: half up, half down — should produce both buy and sell signals."""
    codes_up = [f"{i:06d}.SZ" for i in range(1, 16)]
    codes_down = [f"{i:06d}.SZ" for i in range(16, 31)]
    frames = []
    for code in codes_up:
        np.random.seed(hash(code) % 2**31)
        close = 100 + np.cumsum(np.random.randn(60) * 0.3 + 0.3)
        frames.append(pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=60, freq="B"),
            "code": code,
            "open": close - 0.1, "high": close + 0.3,
            "low": close - 0.3, "close": close,
            "volume": [1_000_000] * 60,
        }))
    for code in codes_down:
        np.random.seed(hash(code) % 2**31)
        close = 100 + np.cumsum(np.random.randn(60) * 0.3 - 0.3)
        frames.append(pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=60, freq="B"),
            "code": code,
            "open": close + 0.1, "high": close + 0.3,
            "low": close - 0.3, "close": close,
            "volume": [1_000_000] * 60,
        }))
    return pd.concat(frames, ignore_index=True)


@pytest.fixture
def single_stock() -> pd.DataFrame:
    """Single stock — not enough for cross-sectional ranking."""
    return pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=60, freq="B"),
        "code": "000001.SZ",
        "open": np.arange(60, dtype=float) + 100,
        "high": np.arange(60, dtype=float) + 101,
        "low": np.arange(60, dtype=float) + 99,
        "close": np.arange(60, dtype=float) + 100,
        "volume": [1_000_000] * 60,
    })


# ---------------------------------------------------------------------------
# Tests: Strategy class
# ---------------------------------------------------------------------------

class TestGTJAMomentumStrategy:
    def test_name(self) -> None:
        s = GTJAMomentumStrategy()
        assert s.name == "gtja_momentum"

    def test_returns_dataframe(self, mixed_trend: pd.DataFrame) -> None:
        s = GTJAMomentumStrategy(rebalance=20, top_n=3, bottom_n=3)
        result = s.generate_signal(mixed_trend)
        assert isinstance(result, pd.DataFrame)

    def test_has_required_columns(self, mixed_trend: pd.DataFrame) -> None:
        s = GTJAMomentumStrategy(rebalance=20, top_n=3, bottom_n=3)
        result = s.generate_signal(mixed_trend)
        assert set(result.columns) == {"date", "code", "signal", "confidence"}

    def test_signal_values_valid(self, mixed_trend: pd.DataFrame) -> None:
        s = GTJAMomentumStrategy(rebalance=20, top_n=3, bottom_n=3)
        result = s.generate_signal(mixed_trend)
        assert set(result["signal"].unique()).issubset({-1, 0, 1})

    def test_confidence_range(self, mixed_trend: pd.DataFrame) -> None:
        s = GTJAMomentumStrategy(rebalance=20, top_n=3, bottom_n=3)
        result = s.generate_signal(mixed_trend)
        assert (result["confidence"] >= 0).all()
        assert (result["confidence"] <= 1).all()

    def test_uses_factors_if_provided(self, mixed_trend: pd.DataFrame) -> None:
        """Strategy should use pre-computed factors if passed in."""
        s = GTJAMomentumStrategy(rebalance=20, top_n=3, bottom_n=3)
        # Provide factors with known values: all positive = all buy
        factors = pd.DataFrame({
            "date": mixed_trend["date"],
            "code": mixed_trend["code"],
            "gtja_14": [1.0] * len(mixed_trend),
            "gtja_18": [1.0] * len(mixed_trend),
            "gtja_20": [1.0] * len(mixed_trend),
            "gtja_88": [1.0] * len(mixed_trend),
            "gtja_106": [1.0] * len(mixed_trend),
        })
        result = s.generate_signal(mixed_trend, factors=factors)
        assert isinstance(result, pd.DataFrame)
        assert len(result) == len(mixed_trend)


# ---------------------------------------------------------------------------
# Tests: Signal function
# ---------------------------------------------------------------------------

class TestGTJAMomentumSignal:
    def test_returns_dataframe(self, mixed_trend: pd.DataFrame) -> None:
        result = gtja_momentum_signal(mixed_trend, rebalance=20, top_n=3, bottom_n=3)
        assert isinstance(result, pd.DataFrame)
        assert len(result) == len(mixed_trend)

    def test_buy_on_uptrend(self, trending_up: pd.DataFrame) -> None:
        result = gtja_momentum_signal(trending_up, rebalance=20, top_n=5, bottom_n=0)
        buy_signals = result[result["signal"] == 1]
        assert len(buy_signals) > 0

    def test_sell_on_downtrend(self, trending_down: pd.DataFrame) -> None:
        result = gtja_momentum_signal(trending_down, rebalance=20, top_n=0, bottom_n=5)
        sell_signals = result[result["signal"] == -1]
        assert len(sell_signals) > 0

    def test_no_signal_single_stock(self, single_stock: pd.DataFrame) -> None:
        result = gtja_momentum_signal(single_stock, rebalance=20, top_n=5, bottom_n=5)
        # Only 1 stock, can't rank cross-sectionally
        assert (result["signal"] == 0).all()

    def test_length_matches_input(self, mixed_trend: pd.DataFrame) -> None:
        result = gtja_momentum_signal(mixed_trend, rebalance=20, top_n=3, bottom_n=3)
        assert len(result) == len(mixed_trend)

    def test_custom_weights(self, mixed_trend: pd.DataFrame) -> None:
        weights = {
            "gtja_14": 2.0,
            "gtja_18": 1.0,
            "gtja_20": 1.0,
            "gtja_88": 1.0,
            "gtja_106": 1.0,
        }
        result = gtja_momentum_signal(
            mixed_trend, rebalance=20, top_n=3, bottom_n=3, weights=weights,
        )
        assert isinstance(result, pd.DataFrame)
