"""Volume-price factor tests."""

import numpy as np
import pandas as pd
import pytest

from factors.builtin.volume_price import calc_atr, calc_obv, calc_rsi, calc_volume_ratio


@pytest.fixture
def single_stock():
    """Single stock, 30 days of data."""
    dates = pd.date_range("2024-01-02", periods=30, freq="B")
    np.random.seed(42)
    close = 10.0 + np.cumsum(np.random.randn(30) * 0.2)
    return pd.DataFrame(
        {
            "date": dates,
            "code": "000001",
            "open": close - 0.1,
            "high": close + 0.3,
            "low": close - 0.3,
            "close": close,
            "volume": np.random.randint(100_000, 1_000_000, 30),
        }
    )


@pytest.fixture
def two_stocks(single_stock):
    """Two stocks with different data."""
    stock2 = single_stock.copy()
    stock2["code"] = "600519"
    stock2["close"] = single_stock["close"] + 100
    stock2["high"] = single_stock["high"] + 100
    stock2["low"] = single_stock["low"] + 100
    stock2["open"] = single_stock["open"] + 100
    return pd.concat([single_stock, stock2], ignore_index=True)


# --- RSI ---


class TestRSI:
    def test_returns_series(self, single_stock):
        result = calc_rsi(single_stock, window=14)
        assert isinstance(result, pd.Series)

    def test_length_matches_input(self, single_stock):
        result = calc_rsi(single_stock, window=14)
        assert len(result) == len(single_stock)

    def test_rsi_range(self, single_stock):
        """RSI should be in [0, 100]."""
        result = calc_rsi(single_stock, window=14)
        valid = result.dropna()
        assert (valid >= 0).all()
        assert (valid <= 100).all()

    def test_nan_for_insufficient_window(self, single_stock):
        """First (window) values per stock should be NaN."""
        result = calc_rsi(single_stock, window=14)
        # diff() produces NaN at index 0, so rolling(window=14) first valid at index 14
        assert result.iloc[:14].isna().all()
        assert result.iloc[14:].notna().all()

    def test_multi_stock_independence(self, two_stocks):
        """Each stock computed independently."""
        result = calc_rsi(two_stocks, window=14)
        assert len(result) == len(two_stocks)
        # Split and compare
        r1 = calc_rsi(
            two_stocks[two_stocks["code"] == "000001"], window=14
        ).values
        r2 = calc_rsi(
            two_stocks[two_stocks["code"] == "600519"], window=14
        ).values
        result_s1 = result[two_stocks["code"] == "000001"].values
        result_s2 = result[two_stocks["code"] == "600519"].values
        np.testing.assert_array_equal(result_s1[~np.isnan(r1)], r1[~np.isnan(r1)])
        np.testing.assert_array_equal(result_s2[~np.isnan(r2)], r2[~np.isnan(r2)])

    def test_constant_price_rsi_50(self):
        """Constant price → no gains or losses → RSI undefined, but shouldn't crash."""
        dates = pd.date_range("2024-01-02", periods=20, freq="B")
        df = pd.DataFrame(
            {
                "date": dates,
                "code": "000001",
                "open": 10.0,
                "high": 10.0,
                "low": 10.0,
                "close": 10.0,
                "volume": 1_000_000,
            }
        )
        result = calc_rsi(df, window=14)
        # avg_loss = 0 → division by 0 → should handle gracefully
        assert len(result) == 20


# --- OBV ---


class TestOBV:
    def test_returns_series(self, single_stock):
        result = calc_obv(single_stock)
        assert isinstance(result, pd.Series)

    def test_length_matches_input(self, single_stock):
        result = calc_obv(single_stock)
        assert len(result) == len(single_stock)

    def test_first_value_zero(self, single_stock):
        """First OBV value should be 0 (no previous close)."""
        result = calc_obv(single_stock)
        assert result.iloc[0] == 0

    def test_obv_increases_on_up_close(self, single_stock):
        """When close > prev_close, OBV should increase by volume."""
        result = calc_obv(single_stock)
        for i in range(1, len(single_stock)):
            if single_stock["close"].iloc[i] > single_stock["close"].iloc[i - 1]:
                assert result.iloc[i] > result.iloc[i - 1]

    def test_obv_decreases_on_down_close(self, single_stock):
        """When close < prev_close, OBV should decrease by volume."""
        result = calc_obv(single_stock)
        for i in range(1, len(single_stock)):
            if single_stock["close"].iloc[i] < single_stock["close"].iloc[i - 1]:
                assert result.iloc[i] < result.iloc[i - 1]

    def test_multi_stock_independence(self, two_stocks):
        result = calc_obv(two_stocks)
        assert len(result) == len(two_stocks)
        # Each stock's OBV should start from 0
        for code in two_stocks["code"].unique():
            stock_obv = result[two_stocks["code"] == code]
            assert stock_obv.iloc[0] == 0


# --- Volume Ratio ---


class TestVolumeRatio:
    def test_returns_series(self, single_stock):
        result = calc_volume_ratio(single_stock, window=5)
        assert isinstance(result, pd.Series)

    def test_length_matches_input(self, single_stock):
        result = calc_volume_ratio(single_stock, window=5)
        assert len(result) == len(single_stock)

    def test_nan_for_insufficient_window(self, single_stock):
        result = calc_volume_ratio(single_stock, window=5)
        assert result.iloc[:4].isna().all()

    def test_ratio_positive(self, single_stock):
        result = calc_volume_ratio(single_stock, window=5)
        valid = result.dropna()
        assert (valid > 0).all()

    def test_ratio_around_1_for_constant_volume(self):
        """Constant volume → ratio ≈ 1.0."""
        dates = pd.date_range("2024-01-02", periods=20, freq="B")
        df = pd.DataFrame(
            {
                "date": dates,
                "code": "000001",
                "open": 10.0,
                "high": 10.5,
                "low": 9.5,
                "close": 10.0,
                "volume": 500_000,
            }
        )
        result = calc_volume_ratio(df, window=5)
        valid = result.dropna()
        np.testing.assert_allclose(valid, 1.0, atol=1e-8)

    def test_multi_stock_independence(self, two_stocks):
        result = calc_volume_ratio(two_stocks, window=5)
        assert len(result) == len(two_stocks)


# --- ATR ---


class TestATR:
    def test_returns_series(self, single_stock):
        result = calc_atr(single_stock, window=14)
        assert isinstance(result, pd.Series)

    def test_length_matches_input(self, single_stock):
        result = calc_atr(single_stock, window=14)
        assert len(result) == len(single_stock)

    def test_nan_for_insufficient_window(self, single_stock):
        result = calc_atr(single_stock, window=14)
        assert result.iloc[:13].isna().all()

    def test_atr_positive(self, single_stock):
        result = calc_atr(single_stock, window=14)
        valid = result.dropna()
        assert (valid > 0).all()

    def test_multi_stock_independence(self, two_stocks):
        result = calc_atr(two_stocks, window=14)
        assert len(result) == len(two_stocks)

    def test_constant_price_atr_zero(self):
        """Constant price → TR = 0 → ATR = 0."""
        dates = pd.date_range("2024-01-02", periods=20, freq="B")
        df = pd.DataFrame(
            {
                "date": dates,
                "code": "000001",
                "open": 10.0,
                "high": 10.0,
                "low": 10.0,
                "close": 10.0,
                "volume": 1_000_000,
            }
        )
        result = calc_atr(df, window=3)
        valid = result.dropna()
        np.testing.assert_allclose(valid, 0.0, atol=1e-10)
