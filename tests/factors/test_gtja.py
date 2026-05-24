"""Tests for GTJA momentum factors."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.factors.momentum import (
    calc_momentum_5d_change,
    calc_momentum_5d_ratio,
    calc_momentum_6d_return,
    calc_momentum_20d_change,
    calc_momentum_20d_return,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def single_stock() -> pd.DataFrame:
    """30 days of synthetic OHLCV for one stock."""
    dates = pd.date_range("2024-01-01", periods=30, freq="B")
    np.random.seed(42)
    close = 100 + np.cumsum(np.random.randn(30) * 0.5)
    return pd.DataFrame({
        "date": dates,
        "code": "000001.SZ",
        "open": close - 0.2,
        "high": close + 0.5,
        "low": close - 0.5,
        "close": close,
        "volume": np.random.randint(1_000_000, 5_000_000, 30),
    })


@pytest.fixture
def two_stocks() -> pd.DataFrame:
    """Two stocks with different price levels, 25 days each."""
    dates = pd.date_range("2024-01-01", periods=25, freq="B")
    np.random.seed(42)
    close_a = 100 + np.cumsum(np.random.randn(25) * 0.5)
    close_b = 200 + np.cumsum(np.random.randn(25) * 1.0)
    stock_a = pd.DataFrame({
        "date": dates, "code": "000001.SZ",
        "open": close_a - 0.2, "high": close_a + 0.5,
        "low": close_a - 0.5, "close": close_a,
        "volume": [1_000_000] * 25,
    })
    stock_b = pd.DataFrame({
        "date": dates, "code": "600519.SH",
        "open": close_b - 0.2, "high": close_b + 0.5,
        "low": close_b - 0.5, "close": close_b,
        "volume": [2_000_000] * 25,
    })
    return pd.concat([stock_a, stock_b], ignore_index=True)


@pytest.fixture
def known_prices() -> pd.DataFrame:
    """10-day single stock with linearly increasing prices for exact math."""
    return pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=10, freq="B"),
        "code": "A",
        "open": [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0],
        "high": [11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0, 20.0],
        "low": [9.0, 10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0],
        "close": [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0],
        "volume": [1_000_000] * 10,
    })


# ---------------------------------------------------------------------------
# GTJA #14: calc_momentum_5d_change  (close - delay(close, 5))
# ---------------------------------------------------------------------------

class TestCalcMomentum5dChange:
    def test_returns_series(self, single_stock: pd.DataFrame) -> None:
        result = calc_momentum_5d_change(single_stock)
        assert isinstance(result, pd.Series)

    def test_length_matches_input(self, single_stock: pd.DataFrame) -> None:
        result = calc_momentum_5d_change(single_stock)
        assert len(result) == len(single_stock)

    def test_first_five_rows_nan(self, single_stock: pd.DataFrame) -> None:
        result = calc_momentum_5d_change(single_stock)
        assert result.iloc[:5].isna().all()
        assert result.iloc[5:].notna().all()

    def test_known_values(self, known_prices: pd.DataFrame) -> None:
        # close = [10,11,12,13,14,15,16,17,18,19] (linear, +1/day)
        # delay(close, 5) at index 5 = 10, delta = 15 - 10 = 5
        # delay(close, 5) at index 6 = 11, delta = 16 - 11 = 5
        result = calc_momentum_5d_change(known_prices)
        assert np.isclose(result.iloc[5], 5.0)
        assert np.isclose(result.iloc[6], 5.0)

    def test_constant_price_zero(self) -> None:
        df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=10, freq="B"),
            "code": "A",
            "open": [100.0] * 10, "high": [101.0] * 10,
            "low": [99.0] * 10, "close": [100.0] * 10,
            "volume": [1_000_000] * 10,
        })
        result = calc_momentum_5d_change(df)
        np.testing.assert_allclose(result.iloc[5:].values, 0.0)

    def test_multi_stock_independence(self, two_stocks: pd.DataFrame) -> None:
        result = calc_momentum_5d_change(two_stocks)
        assert len(result) == len(two_stocks)
        # First 5 rows of each stock should be NaN
        stock_a = two_stocks["code"] == "000001.SZ"
        stock_b = two_stocks["code"] == "600519.SH"
        assert result[stock_a].iloc[:5].isna().all()
        assert result[stock_b].iloc[:5].isna().all()


# ---------------------------------------------------------------------------
# GTJA #18: calc_momentum_5d_ratio  (close / delay(close, 5))
# ---------------------------------------------------------------------------

class TestCalcMomentum5dRatio:
    def test_returns_series(self, single_stock: pd.DataFrame) -> None:
        result = calc_momentum_5d_ratio(single_stock)
        assert isinstance(result, pd.Series)

    def test_first_five_rows_nan(self, single_stock: pd.DataFrame) -> None:
        result = calc_momentum_5d_ratio(single_stock)
        assert result.iloc[:5].isna().all()

    def test_known_values(self, known_prices: pd.DataFrame) -> None:
        # close[5]=15, delay(close,5)[5]=10, ratio = 15/10 = 1.5
        result = calc_momentum_5d_ratio(known_prices)
        assert np.isclose(result.iloc[5], 1.5)

    def test_constant_price_one(self) -> None:
        df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=10, freq="B"),
            "code": "A",
            "open": [100.0] * 10, "high": [101.0] * 10,
            "low": [99.0] * 10, "close": [100.0] * 10,
            "volume": [1_000_000] * 10,
        })
        result = calc_momentum_5d_ratio(df)
        np.testing.assert_allclose(result.iloc[5:].values, 1.0)

    def test_multi_stock_independence(self, two_stocks: pd.DataFrame) -> None:
        result = calc_momentum_5d_ratio(two_stocks)
        assert len(result) == len(two_stocks)


# ---------------------------------------------------------------------------
# GTJA #20: calc_momentum_6d_return  ((close - delay(close, 6)) / delay(close, 6) * 100)
# ---------------------------------------------------------------------------

class TestCalcMomentum6dReturn:
    def test_returns_series(self, single_stock: pd.DataFrame) -> None:
        result = calc_momentum_6d_return(single_stock)
        assert isinstance(result, pd.Series)

    def test_first_six_rows_nan(self, single_stock: pd.DataFrame) -> None:
        result = calc_momentum_6d_return(single_stock)
        assert result.iloc[:6].isna().all()
        assert result.iloc[6:].notna().all()

    def test_known_values_10_percent(self) -> None:
        # Price goes from 100 to 110 in 6 days -> 10% return
        close = [100.0] * 6 + [110.0] * 4
        df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=10, freq="B"),
            "code": "A",
            "open": close, "high": close, "low": close, "close": close,
            "volume": [1_000_000] * 10,
        })
        result = calc_momentum_6d_return(df)
        assert np.isclose(result.iloc[6], 10.0)

    def test_constant_price_zero(self) -> None:
        df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=10, freq="B"),
            "code": "A",
            "open": [100.0] * 10, "high": [101.0] * 10,
            "low": [99.0] * 10, "close": [100.0] * 10,
            "volume": [1_000_000] * 10,
        })
        result = calc_momentum_6d_return(df)
        np.testing.assert_allclose(result.iloc[6:].values, 0.0)

    def test_multi_stock_independence(self, two_stocks: pd.DataFrame) -> None:
        result = calc_momentum_6d_return(two_stocks)
        assert len(result) == len(two_stocks)


# ---------------------------------------------------------------------------
# GTJA #88: calc_momentum_20d_return  ((close - delay(close, 20)) / delay(close, 20) * 100)
# ---------------------------------------------------------------------------

class TestCalcMomentum20dReturn:
    def test_returns_series(self, single_stock: pd.DataFrame) -> None:
        result = calc_momentum_20d_return(single_stock)
        assert isinstance(result, pd.Series)

    def test_first_twenty_rows_nan(self, single_stock: pd.DataFrame) -> None:
        result = calc_momentum_20d_return(single_stock)
        assert result.iloc[:20].isna().all()
        assert result.iloc[20:].notna().all()

    def test_known_values(self) -> None:
        # 25 days: price 100 for first 20 days, then 110 for last 5
        close = [100.0] * 20 + [110.0] * 5
        df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=25, freq="B"),
            "code": "A",
            "open": close, "high": close, "low": close, "close": close,
            "volume": [1_000_000] * 25,
        })
        result = calc_momentum_20d_return(df)
        assert np.isclose(result.iloc[20], 10.0)

    def test_constant_price_zero(self) -> None:
        df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=25, freq="B"),
            "code": "A",
            "open": [100.0] * 25, "high": [101.0] * 25,
            "low": [99.0] * 25, "close": [100.0] * 25,
            "volume": [1_000_000] * 25,
        })
        result = calc_momentum_20d_return(df)
        np.testing.assert_allclose(result.iloc[20:].values, 0.0)

    def test_multi_stock_independence(self, two_stocks: pd.DataFrame) -> None:
        result = calc_momentum_20d_return(two_stocks)
        assert len(result) == len(two_stocks)


# ---------------------------------------------------------------------------
# GTJA #106: calc_momentum_20d_change  (close - delay(close, 20))
# ---------------------------------------------------------------------------

class TestCalcMomentum20dChange:
    def test_returns_series(self, single_stock: pd.DataFrame) -> None:
        result = calc_momentum_20d_change(single_stock)
        assert isinstance(result, pd.Series)

    def test_first_twenty_rows_nan(self, single_stock: pd.DataFrame) -> None:
        result = calc_momentum_20d_change(single_stock)
        assert result.iloc[:20].isna().all()
        assert result.iloc[20:].notna().all()

    def test_known_values(self) -> None:
        # 25 days: price 100 for first 20, then 120 for last 5
        close = [100.0] * 20 + [120.0] * 5
        df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=25, freq="B"),
            "code": "A",
            "open": close, "high": close, "low": close, "close": close,
            "volume": [1_000_000] * 25,
        })
        result = calc_momentum_20d_change(df)
        assert np.isclose(result.iloc[20], 20.0)

    def test_constant_price_zero(self) -> None:
        df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=25, freq="B"),
            "code": "A",
            "open": [100.0] * 25, "high": [101.0] * 25,
            "low": [99.0] * 25, "close": [100.0] * 25,
            "volume": [1_000_000] * 25,
        })
        result = calc_momentum_20d_change(df)
        np.testing.assert_allclose(result.iloc[20:].values, 0.0)

    def test_multi_stock_independence(self, two_stocks: pd.DataFrame) -> None:
        result = calc_momentum_20d_change(two_stocks)
        assert len(result) == len(two_stocks)
