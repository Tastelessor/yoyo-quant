"""Tests for GTJA base operators."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from factors.operators import (
    corr,
    delay,
    delta,
    rank,
    rolling_cov,
    rolling_mean,
    rolling_std,
    rolling_sum,
    sma,
    ts_max,
    ts_min,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def single_stock() -> pd.DataFrame:
    """10-day single stock with known close values."""
    return pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=10, freq="B"),
        "code": "000001.SZ",
        "open": [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0],
        "high": [11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0, 20.0],
        "low": [9.0, 10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0],
        "close": [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0],
        "volume": [1_000_000] * 10,
    })


@pytest.fixture
def two_stocks() -> pd.DataFrame:
    """Two stocks with different price levels, 5 days each."""
    stock_a = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=5, freq="B"),
        "code": "000001.SZ",
        "open": [10.0, 11.0, 12.0, 13.0, 14.0],
        "high": [11.0, 12.0, 13.0, 14.0, 15.0],
        "low": [9.0, 10.0, 11.0, 12.0, 13.0],
        "close": [10.0, 11.0, 12.0, 13.0, 14.0],
        "volume": [1_000_000] * 5,
    })
    stock_b = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=5, freq="B"),
        "code": "600519.SH",
        "open": [100.0, 102.0, 104.0, 106.0, 108.0],
        "high": [101.0, 103.0, 105.0, 107.0, 109.0],
        "low": [99.0, 101.0, 103.0, 105.0, 107.0],
        "close": [100.0, 102.0, 104.0, 106.0, 108.0],
        "volume": [2_000_000] * 5,
    })
    return pd.concat([stock_a, stock_b], ignore_index=True).sort_values(["code", "date"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# TestDelay
# ---------------------------------------------------------------------------

class TestDelay:
    def test_returns_series(self, single_stock: pd.DataFrame) -> None:
        result = delay(single_stock, "close", 2)
        assert isinstance(result, pd.Series)

    def test_length_matches_input(self, single_stock: pd.DataFrame) -> None:
        result = delay(single_stock, "close", 2)
        assert len(result) == len(single_stock)

    def test_shifts_by_n(self) -> None:
        df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=5, freq="B"),
            "code": "A",
            "close": [10.0, 20.0, 30.0, 40.0, 50.0],
        })
        result = delay(df, "close", 2)
        expected = pd.Series([np.nan, np.nan, 10.0, 20.0, 30.0])
        pd.testing.assert_series_equal(result, expected, check_names=False)

    def test_first_n_rows_are_nan(self, single_stock: pd.DataFrame) -> None:
        result = delay(single_stock, "close", 3)
        assert result.iloc[:3].isna().all()
        assert result.iloc[3:].notna().all()

    def test_delay_zero_returns_same(self, single_stock: pd.DataFrame) -> None:
        result = delay(single_stock, "close", 0)
        pd.testing.assert_series_equal(result, single_stock["close"], check_names=False)

    def test_multi_stock_independence(self, two_stocks: pd.DataFrame) -> None:
        result = delay(two_stocks, "close", 1)
        # First row of each stock should be NaN
        stock_a_mask = two_stocks["code"] == "000001.SZ"
        stock_b_mask = two_stocks["code"] == "600519.SH"
        assert result[stock_a_mask].iloc[0] != 100.0  # Should not cross stock boundary
        assert pd.isna(result[stock_a_mask].iloc[0])
        assert pd.isna(result[stock_b_mask].iloc[0])

    def test_negative_n_raises(self, single_stock: pd.DataFrame) -> None:
        with pytest.raises(ValueError, match="n must be >= 0"):
            delay(single_stock, "close", -1)


# ---------------------------------------------------------------------------
# TestDelta
# ---------------------------------------------------------------------------

class TestDelta:
    def test_delta_is_delay_subtraction(self, single_stock: pd.DataFrame) -> None:
        result = delta(single_stock, "close", 2)
        expected = single_stock["close"] - delay(single_stock, "close", 2)
        pd.testing.assert_series_equal(result, expected, check_names=False)

    def test_delta_multi_stock(self, two_stocks: pd.DataFrame) -> None:
        result = delta(two_stocks, "close", 1)
        assert len(result) == len(two_stocks)
        # First row of each stock group should be NaN
        stock_a_mask = two_stocks["code"] == "000001.SZ"
        stock_b_mask = two_stocks["code"] == "600519.SH"
        assert pd.isna(result[stock_a_mask].iloc[0])
        assert pd.isna(result[stock_b_mask].iloc[0])


# ---------------------------------------------------------------------------
# TestRollingMean
# ---------------------------------------------------------------------------

class TestRollingMean:
    def test_matches_pandas(self, single_stock: pd.DataFrame) -> None:
        result = rolling_mean(single_stock, "close", 3)
        expected = (
            single_stock.groupby("code")["close"]
            .rolling(window=3, min_periods=3)
            .mean()
            .droplevel(0)
            .sort_index()
        )
        pd.testing.assert_series_equal(result, expected, check_names=False)

    def test_nan_for_insufficient_window(self, single_stock: pd.DataFrame) -> None:
        result = rolling_mean(single_stock, "close", 5)
        assert result.iloc[:4].isna().all()
        assert result.iloc[4:].notna().all()


# ---------------------------------------------------------------------------
# TestRollingStd
# ---------------------------------------------------------------------------

class TestRollingStd:
    def test_constant_price_zero_std(self) -> None:
        df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=5, freq="B"),
            "code": "A",
            "close": [100.0] * 5,
        })
        result = rolling_std(df, "close", 3)
        assert result.iloc[2:].notna().all()
        np.testing.assert_allclose(result.iloc[2:].values, 0.0, atol=1e-10)

    def test_nan_for_insufficient_window(self, single_stock: pd.DataFrame) -> None:
        result = rolling_std(single_stock, "close", 4)
        assert result.iloc[:3].isna().all()


# ---------------------------------------------------------------------------
# TestRollingSum
# ---------------------------------------------------------------------------

class TestRollingSum:
    def test_known_values(self) -> None:
        df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=5, freq="B"),
            "code": "A",
            "close": [1.0, 2.0, 3.0, 4.0, 5.0],
        })
        result = rolling_sum(df, "close", 3)
        assert np.isclose(result.iloc[2], 6.0)   # 1+2+3
        assert np.isclose(result.iloc[3], 9.0)   # 2+3+4
        assert np.isclose(result.iloc[4], 12.0)  # 3+4+5

    def test_nan_for_insufficient_window(self, single_stock: pd.DataFrame) -> None:
        result = rolling_sum(single_stock, "close", 6)
        assert result.iloc[:5].isna().all()
        assert result.iloc[5:].notna().all()


# ---------------------------------------------------------------------------
# TestSma
# ---------------------------------------------------------------------------

class TestSma:
    def test_returns_series(self, single_stock: pd.DataFrame) -> None:
        result = sma(single_stock, "close", n=5, m=1)
        assert isinstance(result, pd.Series)
        assert len(result) == len(single_stock)

    def test_matches_pandas_ewm(self, single_stock: pd.DataFrame) -> None:
        n, m = 5, 1
        result = sma(single_stock, "close", n=n, m=m)
        expected = (
            single_stock.groupby("code")["close"]
            .ewm(alpha=m / n, min_periods=n)
            .mean()
            .droplevel(0)
            .sort_index()
        )
        pd.testing.assert_series_equal(result, expected, check_names=False)

    def test_constant_price_constant_ema(self) -> None:
        df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=10, freq="B"),
            "code": "A",
            "close": [100.0] * 10,
        })
        result = sma(df, "close", n=5, m=1)
        # After warmup, EMA of constant = constant
        assert result.iloc[4:].notna().all()
        np.testing.assert_allclose(result.iloc[4:].values, 100.0, atol=1e-10)


# ---------------------------------------------------------------------------
# TestCorr
# ---------------------------------------------------------------------------

class TestCorr:
    def test_returns_series(self, single_stock: pd.DataFrame) -> None:
        result = corr(single_stock, "close", "volume", window=5)
        assert isinstance(result, pd.Series)
        assert len(result) == len(single_stock)

    def test_perfect_correlation(self) -> None:
        df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=10, freq="B"),
            "code": "A",
            "close": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
            "volume": [2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 14.0, 16.0, 18.0, 20.0],
        })
        result = corr(df, "close", "volume", window=5)
        # Perfect positive correlation
        np.testing.assert_allclose(result.iloc[4:].values, 1.0, atol=1e-10)

    def test_nan_for_insufficient_window(self) -> None:
        df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=10, freq="B"),
            "code": "A",
            "close": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
            "volume": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0],
        })
        result = corr(df, "close", "volume", window=5)
        assert result.iloc[:4].isna().all()
        assert result.iloc[4:].notna().all()

    def test_multi_stock_independence(self, two_stocks: pd.DataFrame) -> None:
        result = corr(two_stocks, "close", "volume", window=3)
        assert len(result) == len(two_stocks)
        stock_a_mask = two_stocks["code"] == "000001.SZ"
        stock_b_mask = two_stocks["code"] == "600519.SH"
        assert result[stock_a_mask].iloc[:2].isna().all()
        assert result[stock_b_mask].iloc[:2].isna().all()


# ---------------------------------------------------------------------------
# TestRank
# ---------------------------------------------------------------------------


class TestRank:
    def test_returns_series(self, two_stocks: pd.DataFrame) -> None:
        result = rank(two_stocks, "close")
        assert isinstance(result, pd.Series)
        assert len(result) == len(two_stocks)

    def test_values_between_0_and_1(self, two_stocks: pd.DataFrame) -> None:
        result = rank(two_stocks, "close")
        assert result.notna().all()
        assert (result >= 0).all()
        assert (result <= 1).all()

    def test_cross_sectional_per_date(self, two_stocks: pd.DataFrame) -> None:
        result = rank(two_stocks, "close")
        # On each date, stock B (higher close) should always rank higher than stock A
        for d in two_stocks["date"].unique():
            day_mask = two_stocks["date"] == d
            a_val = result[day_mask & (two_stocks["code"] == "000001.SZ")].iloc[0]
            b_val = result[day_mask & (two_stocks["code"] == "600519.SH")].iloc[0]
            assert b_val > a_val

    def test_equal_values_get_same_rank(self) -> None:
        df = pd.DataFrame({
            "date": ["2024-01-01", "2024-01-01", "2024-01-01"],
            "code": ["A", "B", "C"],
            "close": [100.0, 100.0, 100.0],
        })
        df["date"] = pd.to_datetime(df["date"])
        result = rank(df, "close")
        # tied ranks use average, so all 3 equal values → all get avg rank = 2/3
        np.testing.assert_allclose(result.values, 2 / 3)

    def test_single_stock_returns_one(self, single_stock: pd.DataFrame) -> None:
        result = rank(single_stock, "close")
        assert result.notna().all()
        np.testing.assert_allclose(result.values, 1.0)


# ---------------------------------------------------------------------------
# TestTsMax
# ---------------------------------------------------------------------------


class TestTsMax:
    def test_returns_series(self, single_stock: pd.DataFrame) -> None:
        result = ts_max(single_stock, "close", window=3)
        assert isinstance(result, pd.Series)
        assert len(result) == len(single_stock)

    def test_nan_for_insufficient_window(self, single_stock: pd.DataFrame) -> None:
        result = ts_max(single_stock, "close", window=5)
        assert result.iloc[:4].isna().all()
        assert result.iloc[4:].notna().all()

    def test_known_values(self) -> None:
        df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=5, freq="B"),
            "code": "A",
            "close": [10.0, 15.0, 13.0, 17.0, 12.0],
        })
        result = ts_max(df, "close", window=3)
        assert np.isclose(result.iloc[2], 15.0)  # max(10,15,13)
        assert np.isclose(result.iloc[3], 17.0)  # max(15,13,17)
        assert np.isclose(result.iloc[4], 17.0)  # max(13,17,12)

    def test_multi_stock_independence(self, two_stocks: pd.DataFrame) -> None:
        result = ts_max(two_stocks, "close", window=3)
        a_mask = two_stocks["code"] == "000001.SZ"
        b_mask = two_stocks["code"] == "600519.SH"
        assert result[a_mask].iloc[:2].isna().all()
        assert result[b_mask].iloc[:2].isna().all()


# ---------------------------------------------------------------------------
# TestTsMin
# ---------------------------------------------------------------------------


class TestTsMin:
    def test_returns_series(self, single_stock: pd.DataFrame) -> None:
        result = ts_min(single_stock, "close", window=3)
        assert isinstance(result, pd.Series)
        assert len(result) == len(single_stock)

    def test_nan_for_insufficient_window(self, single_stock: pd.DataFrame) -> None:
        result = ts_min(single_stock, "close", window=5)
        assert result.iloc[:4].isna().all()
        assert result.iloc[4:].notna().all()

    def test_known_values(self) -> None:
        df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=5, freq="B"),
            "code": "A",
            "close": [10.0, 15.0, 13.0, 17.0, 12.0],
        })
        result = ts_min(df, "close", window=3)
        assert np.isclose(result.iloc[2], 10.0)  # min(10,15,13)
        assert np.isclose(result.iloc[3], 13.0)  # min(15,13,17)
        assert np.isclose(result.iloc[4], 12.0)  # min(13,17,12)

    def test_multi_stock_independence(self, two_stocks: pd.DataFrame) -> None:
        result = ts_min(two_stocks, "close", window=3)
        a_mask = two_stocks["code"] == "000001.SZ"
        b_mask = two_stocks["code"] == "600519.SH"
        assert result[a_mask].iloc[:2].isna().all()
        assert result[b_mask].iloc[:2].isna().all()


# ---------------------------------------------------------------------------
# TestRollingCov
# ---------------------------------------------------------------------------


class TestRollingCov:
    def test_returns_series(self, single_stock: pd.DataFrame) -> None:
        result = rolling_cov(single_stock, "close", "volume", window=5)
        assert isinstance(result, pd.Series)
        assert len(result) == len(single_stock)

    def test_nan_for_insufficient_window(self, single_stock: pd.DataFrame) -> None:
        result = rolling_cov(single_stock, "close", "volume", window=5)
        assert result.iloc[:4].isna().all()

    def test_known_linear_relationship(self) -> None:
        df = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=10, freq="B"),
            "code": "A",
            "close": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
            "volume": [3.0, 5.0, 7.0, 9.0, 11.0, 13.0, 15.0, 17.0, 19.0, 21.0],
        })
        result = rolling_cov(df, "close", "volume", window=5)
        # volume = 2*close + 1, so covariance should be 2 * var(close)
        # var(1,2,3,4,5) = 2.5, so cov = 5.0
        expected_cov = 5.0
        assert np.isclose(result.iloc[4], expected_cov)
        # var(2,3,4,5,6) = 2.5, so cov = 5.0
        assert np.isclose(result.iloc[5], expected_cov)

    def test_multi_stock_independence(self, two_stocks: pd.DataFrame) -> None:
        result = rolling_cov(two_stocks, "close", "volume", window=3)
        a_mask = two_stocks["code"] == "000001.SZ"
        b_mask = two_stocks["code"] == "600519.SH"
        assert result[a_mask].iloc[:2].isna().all()
        assert result[b_mask].iloc[:2].isna().all()
