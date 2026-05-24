"""Tests for GTJA volume-price factors."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.factors.volume_price_gtja import (
    calc_money_flow_6d,
    calc_obv_6d,
    calc_up_down_vol_ratio_26d,
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
