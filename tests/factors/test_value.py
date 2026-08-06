"""Tests for src/factors/value.py — value factor functions."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from factors.builtin.value import calc_bp, calc_ep


@pytest.fixture
def single_stock():
    """Single stock with PE/PB data, 10 days."""
    dates = pd.date_range("2024-01-02", periods=10, freq="B")
    return pd.DataFrame(
        {
            "date": dates,
            "code": "000001",
            "close": 10.0,
            "pe": [15.0, 20.0, -5.0, 0.0, 100.0, np.nan, 8.0, 500.0, 1000.0, 12.0],
            "pb": [1.5, 2.0, -0.5, 0.0, 10.0, np.nan, 0.8, 50.0, 100.0, 1.2],
        }
    )


@pytest.fixture
def two_stocks(single_stock):
    """Two stocks with different PE/PB."""
    stock2 = single_stock.copy()
    stock2["code"] = "600519"
    stock2["pe"] = single_stock["pe"] + 5
    stock2["pb"] = single_stock["pb"] + 0.5
    return pd.concat([single_stock, stock2], ignore_index=True)


# --- calc_ep ---


class TestCalcEP:
    def test_returns_series(self, single_stock):
        result = calc_ep(single_stock)
        assert isinstance(result, pd.Series)

    def test_length_matches_input(self, single_stock):
        result = calc_ep(single_stock)
        assert len(result) == len(single_stock)

    def test_positive_pe_returns_reciprocal(self, single_stock):
        """EP = 1/PE for positive PE values."""
        result = calc_ep(single_stock)
        # PE=15 → EP=1/15
        np.testing.assert_almost_equal(result.iloc[0], 1.0 / 15.0)
        # PE=20 → EP=1/20
        np.testing.assert_almost_equal(result.iloc[1], 1.0 / 20.0)

    def test_negative_pe_returns_nan(self, single_stock):
        """PE <= 0 → NaN (not inf)."""
        result = calc_ep(single_stock)
        assert np.isnan(result.iloc[2])  # PE=-5

    def test_zero_pe_returns_nan(self, single_stock):
        """PE = 0 → NaN (not inf)."""
        result = calc_ep(single_stock)
        assert np.isnan(result.iloc[3])  # PE=0

    def test_nan_pe_returns_nan(self, single_stock):
        """PE = NaN → NaN."""
        result = calc_ep(single_stock)
        assert np.isnan(result.iloc[5])  # PE=NaN

    def test_extreme_pe_linear(self, single_stock):
        """EP is linear: PE=500 and PE=1000 should be close in EP space."""
        result = calc_ep(single_stock)
        ep_500 = result.iloc[7]   # PE=500 → EP=0.002
        ep_1000 = result.iloc[8]  # PE=1000 → EP=0.001
        np.testing.assert_almost_equal(ep_500, 0.002)
        np.testing.assert_almost_equal(ep_1000, 0.001)
        # Difference is small in EP space
        assert abs(ep_500 - ep_1000) < 0.002

    def test_two_stocks_independent(self, two_stocks):
        """Each stock computed independently."""
        result = calc_ep(two_stocks)
        assert len(result) == len(two_stocks)
        # Split and verify against single-stock computation
        s1 = calc_ep(two_stocks[two_stocks["code"] == "000001"]).values
        s2 = calc_ep(two_stocks[two_stocks["code"] == "600519"]).values
        r1 = result[two_stocks["code"] == "000001"].values
        r2 = result[two_stocks["code"] == "600519"].values
        # Compare non-NaN values
        mask1 = ~np.isnan(s1)
        np.testing.assert_array_almost_equal(r1[mask1], s1[mask1])
        mask2 = ~np.isnan(s2)
        np.testing.assert_array_almost_equal(r2[mask2], s2[mask2])

    def test_missing_pe_column_raises(self):
        """Missing 'pe' column → KeyError."""
        df = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-02", periods=3),
                "code": "000001",
                "close": 10.0,
            }
        )
        with pytest.raises(KeyError):
            calc_ep(df)


# --- calc_bp ---


class TestCalcBP:
    def test_returns_series(self, single_stock):
        result = calc_bp(single_stock)
        assert isinstance(result, pd.Series)

    def test_length_matches_input(self, single_stock):
        result = calc_bp(single_stock)
        assert len(result) == len(single_stock)

    def test_positive_pb_returns_reciprocal(self, single_stock):
        """BP = 1/PB for positive PB values."""
        result = calc_bp(single_stock)
        np.testing.assert_almost_equal(result.iloc[0], 1.0 / 1.5)
        np.testing.assert_almost_equal(result.iloc[1], 1.0 / 2.0)

    def test_negative_pb_returns_nan(self, single_stock):
        result = calc_bp(single_stock)
        assert np.isnan(result.iloc[2])  # PB=-0.5

    def test_zero_pb_returns_nan(self, single_stock):
        result = calc_bp(single_stock)
        assert np.isnan(result.iloc[3])  # PB=0

    def test_nan_pb_returns_nan(self, single_stock):
        result = calc_bp(single_stock)
        assert np.isnan(result.iloc[5])  # PB=NaN

    def test_two_stocks_independent(self, two_stocks):
        result = calc_bp(two_stocks)
        assert len(result) == len(two_stocks)

    def test_missing_pb_column_raises(self):
        df = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-02", periods=3),
                "code": "000001",
                "close": 10.0,
            }
        )
        with pytest.raises(KeyError):
            calc_bp(df)
