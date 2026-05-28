"""Tests for GTJA earnings surprise strategy."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.strategies.builtin.earnings_surprise import (
    GTJAEarningsSurpriseStrategy,
    gtja_earnings_surprise_signal,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def earnings_data() -> pd.DataFrame:
    """30 stocks, 60 days, with pre-merged earnings_surprise and earnings_acceleration."""
    codes = [f"{i:06d}" for i in range(1, 31)]
    frames = []
    for i, code in enumerate(codes):
        np.random.seed(hash(code) % 2**31)
        close = 100 + np.cumsum(np.random.randn(60) * 0.3 + 0.1)
        # Vary earnings_surprise by stock: some high, some low
        es_base = (i - 15) / 15.0  # range [-1, 1]
        ea_base = (i - 15) / 30.0  # range [-0.5, 0.5]
        frames.append(pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=60, freq="B"),
            "code": code,
            "open": close - 0.1,
            "high": close + 0.3,
            "low": close - 0.3,
            "close": close,
            "volume": np.random.randint(1_000_000, 5_000_000, 60),
            "earnings_surprise": [es_base + np.random.randn() * 0.1] * 60,
            "earnings_acceleration": [ea_base + np.random.randn() * 0.05] * 60,
        }))
    return pd.concat(frames, ignore_index=True)


@pytest.fixture
def single_stock() -> pd.DataFrame:
    """Single stock — not enough for cross-sectional ranking."""
    return pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=60, freq="B"),
        "code": "000001",
        "open": np.arange(60, dtype=float) + 100,
        "high": np.arange(60, dtype=float) + 101,
        "low": np.arange(60, dtype=float) + 99,
        "close": np.arange(60, dtype=float) + 100,
        "volume": [1_000_000] * 60,
        "earnings_surprise": [0.5] * 60,
        "earnings_acceleration": [0.1] * 60,
    })


# ---------------------------------------------------------------------------
# Tests: Strategy class
# ---------------------------------------------------------------------------

class TestGTJAEarningsSurpriseStrategy:
    def test_name(self):
        s = GTJAEarningsSurpriseStrategy()
        assert s.name == "gtja_earnings_surprise"

    def test_returns_dataframe(self, earnings_data):
        s = GTJAEarningsSurpriseStrategy(rebalance=20, top_n=3, bottom_n=3)
        result = s.generate_signal(earnings_data)
        assert isinstance(result, pd.DataFrame)

    def test_has_required_columns(self, earnings_data):
        s = GTJAEarningsSurpriseStrategy(rebalance=20, top_n=3, bottom_n=3)
        result = s.generate_signal(earnings_data)
        assert set(result.columns) == {"date", "code", "signal", "confidence"}

    def test_signal_values_valid(self, earnings_data):
        s = GTJAEarningsSurpriseStrategy(rebalance=20, top_n=3, bottom_n=3)
        result = s.generate_signal(earnings_data)
        assert set(result["signal"].unique()).issubset({-1, 0, 1})

    def test_confidence_range(self, earnings_data):
        s = GTJAEarningsSurpriseStrategy(rebalance=20, top_n=3, bottom_n=3)
        result = s.generate_signal(earnings_data)
        assert (result["confidence"] >= 0).all()
        assert (result["confidence"] <= 1).all()

    def test_uses_factors_if_provided(self, earnings_data):
        """Strategy should use pre-computed factors if passed in."""
        s = GTJAEarningsSurpriseStrategy(rebalance=20, top_n=3, bottom_n=3)
        factors = pd.DataFrame({
            "date": earnings_data["date"],
            "code": earnings_data["code"],
            "earnings_surprise": [0.5] * len(earnings_data),
            "earnings_acceleration": [0.2] * len(earnings_data),
        })
        result = s.generate_signal(earnings_data, factors=factors)
        assert isinstance(result, pd.DataFrame)
        assert len(result) == len(earnings_data)


# ---------------------------------------------------------------------------
# Tests: Signal function
# ---------------------------------------------------------------------------

class TestGTJAEarningsSurpriseSignal:
    def test_returns_dataframe(self, earnings_data):
        result = gtja_earnings_surprise_signal(earnings_data, rebalance=20, top_n=3, bottom_n=3)
        assert isinstance(result, pd.DataFrame)
        assert len(result) == len(earnings_data)

    def test_buy_high_surprise(self, earnings_data):
        """Stocks with high earnings_surprise should get buy signals."""
        result = gtja_earnings_surprise_signal(earnings_data, rebalance=20, top_n=5, bottom_n=0)
        buy_signals = result[result["signal"] == 1]
        assert len(buy_signals) > 0

    def test_sell_low_surprise(self, earnings_data):
        result = gtja_earnings_surprise_signal(earnings_data, rebalance=20, top_n=0, bottom_n=5)
        sell_signals = result[result["signal"] == -1]
        assert len(sell_signals) > 0

    def test_no_signal_single_stock(self, single_stock):
        result = gtja_earnings_surprise_signal(single_stock, rebalance=20, top_n=5, bottom_n=5)
        # Only 1 stock, can't rank cross-sectionally
        assert (result["signal"] == 0).all()

    def test_length_matches_input(self, earnings_data):
        result = gtja_earnings_surprise_signal(earnings_data, rebalance=20, top_n=3, bottom_n=3)
        assert len(result) == len(earnings_data)

    def test_custom_weights(self, earnings_data):
        weights = {"earnings_surprise": 2.0, "earnings_acceleration": 1.0}
        result = gtja_earnings_surprise_signal(
            earnings_data, rebalance=20, top_n=3, bottom_n=3, weights=weights,
        )
        assert isinstance(result, pd.DataFrame)
