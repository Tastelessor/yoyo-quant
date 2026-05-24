"""Tests for GTJA mean reversion factors."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.factors.mean_reversion import (
    calc_directional_balance_12d,
    calc_mfi_14d,
    calc_rsi_12d,
    calc_rsi_6d,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def single_stock() -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=30, freq="B")
    np.random.seed(42)
    close = 100 + np.cumsum(np.random.randn(30) * 0.5)
    return pd.DataFrame({
        "date": dates, "code": "000001.SZ",
        "open": close - 0.2, "high": close + 0.5,
        "low": close - 0.5, "close": close,
        "volume": np.random.randint(1_000_000, 5_000_000, 30),
    })


@pytest.fixture
def uptrend() -> pd.DataFrame:
    """Consistent uptrend — RSI should be high."""
    return pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=30, freq="B"),
        "code": "A",
        "open": np.arange(30, dtype=float) + 100,
        "high": np.arange(30, dtype=float) + 101,
        "low": np.arange(30, dtype=float) + 99,
        "close": np.arange(30, dtype=float) + 100,
        "volume": [1_000_000] * 30,
    })


@pytest.fixture
def downtrend() -> pd.DataFrame:
    """Consistent downtrend — RSI should be low."""
    return pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=30, freq="B"),
        "code": "A",
        "open": np.arange(30, dtype=float)[::-1] + 100,
        "high": np.arange(30, dtype=float)[::-1] + 101,
        "low": np.arange(30, dtype=float)[::-1] + 99,
        "close": np.arange(30, dtype=float)[::-1] + 100,
        "volume": [1_000_000] * 30,
    })


# ---------------------------------------------------------------------------
# TestCalcRsi6d — GTJA #63
# ---------------------------------------------------------------------------

class TestCalcRsi6d:
    def test_returns_series(self, single_stock: pd.DataFrame) -> None:
        result = calc_rsi_6d(single_stock)
        assert isinstance(result, pd.Series)

    def test_range_0_100(self, single_stock: pd.DataFrame) -> None:
        result = calc_rsi_6d(single_stock)
        valid = result.dropna()
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_uptrend_high_rsi(self, uptrend: pd.DataFrame) -> None:
        result = calc_rsi_6d(uptrend)
        valid = result.dropna()
        assert valid.mean() > 70

    def test_downtrend_low_rsi(self, downtrend: pd.DataFrame) -> None:
        result = calc_rsi_6d(downtrend)
        valid = result.dropna()
        assert valid.mean() < 30

    def test_length_matches_input(self, single_stock: pd.DataFrame) -> None:
        result = calc_rsi_6d(single_stock)
        assert len(result) == len(single_stock)


# ---------------------------------------------------------------------------
# TestCalcRsi12d — GTJA #79
# ---------------------------------------------------------------------------

class TestCalcRsi12d:
    def test_returns_series(self, single_stock: pd.DataFrame) -> None:
        result = calc_rsi_12d(single_stock)
        assert isinstance(result, pd.Series)

    def test_range_0_100(self, single_stock: pd.DataFrame) -> None:
        result = calc_rsi_12d(single_stock)
        valid = result.dropna()
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_uptrend_high_rsi(self, uptrend: pd.DataFrame) -> None:
        result = calc_rsi_12d(uptrend)
        valid = result.dropna()
        assert valid.mean() > 70


# ---------------------------------------------------------------------------
# TestCalcDirectionalBalance12d — GTJA #112
# ---------------------------------------------------------------------------

class TestCalcDirectionalBalance12d:
    def test_returns_series(self, single_stock: pd.DataFrame) -> None:
        result = calc_directional_balance_12d(single_stock)
        assert isinstance(result, pd.Series)

    def test_range_neg100_100(self, single_stock: pd.DataFrame) -> None:
        result = calc_directional_balance_12d(single_stock)
        valid = result.dropna()
        assert (valid >= -100).all() and (valid <= 100).all()

    def test_uptrend_positive(self, uptrend: pd.DataFrame) -> None:
        result = calc_directional_balance_12d(uptrend)
        valid = result.dropna()
        assert valid.mean() > 50


# ---------------------------------------------------------------------------
# TestCalcMfi14d — GTJA #128
# ---------------------------------------------------------------------------

class TestCalcMfi14d:
    def test_returns_series(self, single_stock: pd.DataFrame) -> None:
        result = calc_mfi_14d(single_stock)
        assert isinstance(result, pd.Series)

    def test_range_0_100(self, single_stock: pd.DataFrame) -> None:
        result = calc_mfi_14d(single_stock)
        valid = result.dropna()
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_length_matches_input(self, single_stock: pd.DataFrame) -> None:
        result = calc_mfi_14d(single_stock)
        assert len(result) == len(single_stock)
