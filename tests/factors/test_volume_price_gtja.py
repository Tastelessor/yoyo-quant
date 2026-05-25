"""Tests for GTJA volume-price factors."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.factors.volume_price_gtja import (
    calc_money_flow_6d,
    calc_obv_6d,
    calc_up_down_vol_ratio_26d,
    calc_candle_body_vol_composite,
    calc_close_vol_rank_cov_5d,
    calc_dollar_vol_std_6d,
    calc_high_vol_rank_corr_3d,
    calc_open_vol_corr_10d,
    calc_open_vwap_close_vwap,
    calc_return_1d_times_vol,
    calc_return_6d_times_vol,
    calc_shadow_ratio_20d,
    calc_vol_change_pct_5d,
    calc_vol_macd_9_26_12,
    calc_vol_rank_intraday_corr_6d,
    calc_vol_rsi_6d,
    calc_vwap_vol_rank_corr_5d,
    calc_williams_r_smoothed_6d,
)


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
def two_stocks() -> pd.DataFrame:
    """Two stocks with different price levels for cross-sectional rank tests."""
    dates = pd.date_range("2024-01-01", periods=30, freq="B")
    np.random.seed(42)
    close_a = 100 + np.cumsum(np.random.randn(30) * 0.5)
    close_b = 200 + np.cumsum(np.random.randn(30) * 0.5)
    df = pd.concat([
        pd.DataFrame({
            "date": dates, "code": "000001.SZ",
            "open": close_a - 0.2, "high": close_a + 0.5,
            "low": close_a - 0.5, "close": close_a,
            "volume": np.random.randint(1_000_000, 5_000_000, 30),
        }),
        pd.DataFrame({
            "date": dates, "code": "600519.SH",
            "open": close_b - 0.2, "high": close_b + 0.5,
            "low": close_b - 0.5, "close": close_b,
            "volume": np.random.randint(2_000_000, 6_000_000, 30),
        }),
    ], ignore_index=True)
    return df.sort_values(["code", "date"]).reset_index(drop=True)


class TestCalcMoneyFlow6d:
    def test_returns_series(self, single_stock: pd.DataFrame) -> None:
        result = calc_money_flow_6d(single_stock)
        assert isinstance(result, pd.Series)
        assert len(result) == len(single_stock)

    def test_first_rows_nan(self, single_stock: pd.DataFrame) -> None:
        result = calc_money_flow_6d(single_stock)
        assert result.iloc[:5].isna().all()


class TestCalcUpDownVolRatio26d:
    def test_returns_series(self, single_stock: pd.DataFrame) -> None:
        result = calc_up_down_vol_ratio_26d(single_stock)
        assert isinstance(result, pd.Series)

    def test_positive_values(self, single_stock: pd.DataFrame) -> None:
        result = calc_up_down_vol_ratio_26d(single_stock)
        valid = result.dropna()
        assert (valid >= 0).all()


class TestCalcObv6d:
    def test_returns_series(self, single_stock: pd.DataFrame) -> None:
        result = calc_obv_6d(single_stock)
        assert isinstance(result, pd.Series)
        assert len(result) == len(single_stock)

    def test_first_rows_nan(self, single_stock: pd.DataFrame) -> None:
        result = calc_obv_6d(single_stock)
        assert result.iloc[:5].isna().all()


# --- new volume/sentiment factors ---


class TestCalcVolChangePct5d:
    def test_returns_series(self, single_stock: pd.DataFrame) -> None:
        result = calc_vol_change_pct_5d(single_stock)
        assert isinstance(result, pd.Series)
        assert len(result) == len(single_stock)

    def test_first_rows_nan(self, single_stock: pd.DataFrame) -> None:
        result = calc_vol_change_pct_5d(single_stock)
        assert result.iloc[:5].isna().all()


class TestCalcReturn6dTimesVol:
    def test_returns_series(self, single_stock: pd.DataFrame) -> None:
        result = calc_return_6d_times_vol(single_stock)
        assert isinstance(result, pd.Series)
        assert len(result) == len(single_stock)

    def test_first_rows_nan(self, single_stock: pd.DataFrame) -> None:
        result = calc_return_6d_times_vol(single_stock)
        assert result.iloc[:6].isna().all()


class TestCalcReturn1dTimesVol:
    def test_returns_series(self, single_stock: pd.DataFrame) -> None:
        result = calc_return_1d_times_vol(single_stock)
        assert isinstance(result, pd.Series)
        assert len(result) == len(single_stock)

    def test_first_rows_nan(self, single_stock: pd.DataFrame) -> None:
        result = calc_return_1d_times_vol(single_stock)
        assert pd.isna(result.iloc[0])
        assert result.iloc[1:].notna().all()


class TestCalcOpenVolCorr10d:
    def test_returns_series(self, single_stock: pd.DataFrame) -> None:
        result = calc_open_vol_corr_10d(single_stock)
        assert isinstance(result, pd.Series)
        assert len(result) == len(single_stock)

    def test_first_rows_nan(self, single_stock: pd.DataFrame) -> None:
        result = calc_open_vol_corr_10d(single_stock)
        assert result.iloc[:9].isna().all()


class TestCalcHighVolRankCorr3d:
    def test_returns_series(self, two_stocks: pd.DataFrame) -> None:
        result = calc_high_vol_rank_corr_3d(two_stocks)
        assert isinstance(result, pd.Series)
        assert len(result) == len(two_stocks)

    def test_first_rows_nan(self, two_stocks: pd.DataFrame) -> None:
        result = calc_high_vol_rank_corr_3d(two_stocks)
        a_mask = two_stocks["code"] == "000001.SZ"
        assert result[a_mask].iloc[:2].isna().all()


class TestCalcCloseVolRankCov5d:
    def test_returns_series(self, two_stocks: pd.DataFrame) -> None:
        result = calc_close_vol_rank_cov_5d(two_stocks)
        assert isinstance(result, pd.Series)
        assert len(result) == len(two_stocks)

    def test_first_rows_nan(self, two_stocks: pd.DataFrame) -> None:
        result = calc_close_vol_rank_cov_5d(two_stocks)
        a_mask = two_stocks["code"] == "000001.SZ"
        assert result[a_mask].iloc[:4].isna().all()


class TestCalcVwapVolRankCorr5d:
    def test_returns_series(self, two_stocks: pd.DataFrame) -> None:
        result = calc_vwap_vol_rank_corr_5d(two_stocks)
        assert isinstance(result, pd.Series)
        assert len(result) == len(two_stocks)

    def test_first_rows_nan(self, two_stocks: pd.DataFrame) -> None:
        result = calc_vwap_vol_rank_corr_5d(two_stocks)
        a_mask = two_stocks["code"] == "000001.SZ"
        assert result[a_mask].iloc[:4].isna().all()


class TestCalcVolRankIntradayCorr6d:
    def test_returns_series(self, two_stocks: pd.DataFrame) -> None:
        result = calc_vol_rank_intraday_corr_6d(two_stocks)
        assert isinstance(result, pd.Series)
        assert len(result) == len(two_stocks)

    def test_first_rows_nan(self, two_stocks: pd.DataFrame) -> None:
        result = calc_vol_rank_intraday_corr_6d(two_stocks)
        a_mask = two_stocks["code"] == "000001.SZ"
        assert result[a_mask].iloc[:5].isna().all()


class TestCalcWilliamsRSmoothed6d:
    def test_returns_series(self, single_stock: pd.DataFrame) -> None:
        result = calc_williams_r_smoothed_6d(single_stock)
        assert isinstance(result, pd.Series)
        assert len(result) == len(single_stock)

    def test_first_rows_nan(self, single_stock: pd.DataFrame) -> None:
        result = calc_williams_r_smoothed_6d(single_stock)
        assert result.iloc[:8].isna().all()


class TestCalcShadowRatio20d:
    def test_returns_series(self, single_stock: pd.DataFrame) -> None:
        result = calc_shadow_ratio_20d(single_stock)
        assert isinstance(result, pd.Series)
        assert len(result) == len(single_stock)

    def test_first_rows_nan(self, single_stock: pd.DataFrame) -> None:
        result = calc_shadow_ratio_20d(single_stock)
        assert result.iloc[:19].isna().all()


class TestCalcCandleBodyVolComposite:
    def test_returns_series(self, two_stocks: pd.DataFrame) -> None:
        result = calc_candle_body_vol_composite(two_stocks)
        assert isinstance(result, pd.Series)
        assert len(result) == len(two_stocks)

    def test_first_rows_nan(self, two_stocks: pd.DataFrame) -> None:
        result = calc_candle_body_vol_composite(two_stocks)
        a_mask = two_stocks["code"] == "000001.SZ"
        assert result[a_mask].iloc[:9].isna().all()


class TestCalcOpenVwapCloseVwap:
    def test_returns_series(self, two_stocks: pd.DataFrame) -> None:
        result = calc_open_vwap_close_vwap(two_stocks)
        assert isinstance(result, pd.Series)
        assert len(result) == len(two_stocks)

    def test_first_rows_nan(self, two_stocks: pd.DataFrame) -> None:
        result = calc_open_vwap_close_vwap(two_stocks)
        a_mask = two_stocks["code"] == "000001.SZ"
        assert result[a_mask].iloc[:9].isna().all()


class TestCalcDollarVolStd6d:
    def test_returns_series(self, single_stock: pd.DataFrame) -> None:
        result = calc_dollar_vol_std_6d(single_stock)
        assert isinstance(result, pd.Series)
        assert len(result) == len(single_stock)

    def test_first_rows_nan(self, single_stock: pd.DataFrame) -> None:
        result = calc_dollar_vol_std_6d(single_stock)
        assert result.iloc[:5].isna().all()


class TestCalcVolMacd9_26_12:
    def test_returns_series(self, single_stock: pd.DataFrame) -> None:
        result = calc_vol_macd_9_26_12(single_stock)
        assert isinstance(result, pd.Series)
        assert len(result) == len(single_stock)

    def test_first_rows_nan(self, single_stock: pd.DataFrame) -> None:
        result = calc_vol_macd_9_26_12(single_stock)
        assert result.iloc[:25].isna().all()


class TestCalcVolRsi6d:
    def test_returns_series(self, single_stock: pd.DataFrame) -> None:
        result = calc_vol_rsi_6d(single_stock)
        assert isinstance(result, pd.Series)
        assert len(result) == len(single_stock)

    def test_first_rows_nan(self, single_stock: pd.DataFrame) -> None:
        result = calc_vol_rsi_6d(single_stock)
        assert result.iloc[:5].isna().all()
