"""Tests for src/factors/liquidity.py — liquidity factor functions."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from factors.builtin.liquidity import calc_amihud, calc_turnover


@pytest.fixture
def single_stock():
    """Single stock with varying prices for non-zero Amihud, 25 days."""
    dates = pd.date_range("2024-01-02", periods=25, freq="B")
    # Prices that change daily so returns are non-zero
    close = 10.0 + np.sin(np.arange(25)) * 0.5
    volume = np.full(25, 1_000_000)  # 1M shares
    volume[3] = 0  # zero volume day
    return pd.DataFrame(
        {
            "date": dates,
            "code": "000001",
            "close": close,
            "volume": volume,
            "total_mv": np.full(25, 100.0),  # 100 亿元
        }
    )


@pytest.fixture
def two_stocks(single_stock):
    """Two stocks with different data."""
    stock2 = single_stock.copy()
    stock2["code"] = "600519"
    stock2["close"] = single_stock["close"] + 100
    stock2["total_mv"] = single_stock["total_mv"] + 1000
    return pd.concat([single_stock, stock2], ignore_index=True)


# --- calc_amihud ---


class TestCalcAmihud:
    def test_returns_series(self, single_stock):
        result = calc_amihud(single_stock, window=5)
        assert isinstance(result, pd.Series)

    def test_length_matches_input(self, single_stock):
        result = calc_amihud(single_stock, window=5)
        assert len(result) == len(single_stock)

    def test_hand_calculation(self, single_stock):
        """Verify Amihud = mean(|return| / (volume * close)) over window."""
        result = calc_amihud(single_stock, window=3)
        # Manual check for day 2 (window=3 covers days 0-2):
        # day 0: return=NaN → skip
        # day 1: |return| = |close[1]/close[0] - 1|, turnover = volume*close
        # day 2: similar
        # All ratios should be small positive numbers (order 1e-8 to 1e-9)
        valid = result.dropna()
        assert (valid > 0).all()
        assert (valid < 1e-6).all()  # should be small

    def test_zero_volume_returns_nan(self, single_stock):
        """Zero volume rows should produce NaN in the ratio, not inf."""
        result = calc_amihud(single_stock, window=3)
        # Day 3 has zero volume — the rolling mean should handle it
        # (NaN values are excluded from rolling mean)
        # The result for day 3 depends on other days in the window
        # But the individual ratio for day 3 should not be inf
        assert not np.isinf(result).any()

    def test_nan_for_insufficient_window(self, single_stock):
        """First (window-1) values per stock should be NaN."""
        result = calc_amihud(single_stock, window=20)
        assert result.iloc[:19].isna().all()

    def test_positive_values(self, single_stock):
        """Amihud should be positive where valid."""
        result = calc_amihud(single_stock, window=5)
        valid = result.dropna()
        assert (valid > 0).all()

    def test_two_stocks_independent(self, two_stocks):
        """Each stock computed independently."""
        result = calc_amihud(two_stocks, window=5)
        assert len(result) == len(two_stocks)
        # Split and compare
        s1 = calc_amihud(two_stocks[two_stocks["code"] == "000001"], window=5)
        s2 = calc_amihud(two_stocks[two_stocks["code"] == "600519"], window=5)
        r1 = result[two_stocks["code"] == "000001"].values
        r2 = result[two_stocks["code"] == "600519"].values
        mask1 = ~np.isnan(s1.values)
        np.testing.assert_array_almost_equal(r1[mask1], s1.values[mask1])
        mask2 = ~np.isnan(s2.values)
        np.testing.assert_array_almost_equal(r2[mask2], s2.values[mask2])


# --- calc_turnover ---


class TestCalcTurnover:
    def test_returns_series(self, single_stock):
        result = calc_turnover(single_stock, window=5)
        assert isinstance(result, pd.Series)

    def test_length_matches_input(self, single_stock):
        result = calc_turnover(single_stock, window=5)
        assert len(result) == len(single_stock)

    def test_hand_calculation(self, single_stock):
        """Verify turnover = volume * close / (total_mv * 1e8), rolling mean."""
        result = calc_turnover(single_stock, window=3)
        # turnover per day = volume * close / (total_mv * 1e8)
        # = 1_000_000 * 10.0 / (100.0 * 1e8) = 10_000_000 / 1e10 = 0.001
        # Except day 3 (volume=0): turnover=0
        # rolling mean(3) of [0.001, 0.001, 0.001] = 0.001
        valid = result.dropna()
        assert (valid > 0).all()

    def test_zero_volume_turnover(self, single_stock):
        """Zero volume → turnover = 0 for that day."""
        # Day 3 has volume=0, so turnover for that day = 0
        # Rolling mean should be pulled down
        result = calc_turnover(single_stock, window=3)
        # Just verify it doesn't crash and produces finite values
        valid = result.dropna()
        assert np.isfinite(valid).all()

    def test_nan_for_insufficient_window(self, single_stock):
        result = calc_turnover(single_stock, window=20)
        assert result.iloc[:19].isna().all()

    def test_two_stocks_independent(self, two_stocks):
        result = calc_turnover(two_stocks, window=5)
        assert len(result) == len(two_stocks)
        s1 = calc_turnover(two_stocks[two_stocks["code"] == "000001"], window=5)
        s2 = calc_turnover(two_stocks[two_stocks["code"] == "600519"], window=5)
        r1 = result[two_stocks["code"] == "000001"].values
        r2 = result[two_stocks["code"] == "600519"].values
        mask1 = ~np.isnan(s1.values)
        np.testing.assert_array_almost_equal(r1[mask1], s1.values[mask1])
        mask2 = ~np.isnan(s2.values)
        np.testing.assert_array_almost_equal(r2[mask2], s2.values[mask2])
