"""Tests for walk-forward validation module."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.backtest.walk_forward import (
    generate_windows,
    walk_forward_backtest,
)


def _make_stock_data(start="2023-01-01", end="2025-12-31", codes=None):
    """Create synthetic stock data for testing."""
    if codes is None:
        codes = ["000001", "000002"]
    dates = pd.bdate_range(start, end)
    rows = []
    rng = np.random.RandomState(42)
    for code in codes:
        price = 100.0
        for d in dates:
            price *= 1 + rng.normal(0, 0.02)
            rows.append({
                "date": d, "code": code, "open": price,
                "high": price * 1.01, "low": price * 0.99,
                "close": price, "volume": 1_000_000,
                "limit_up": False, "limit_down": False,
                "is_suspended": False,
            })
    return pd.DataFrame(rows)


def _dummy_signal_fn(train_data, test_data):
    """Dummy signal function that buys everything in test data."""
    codes = test_data["code"].unique()
    dates = test_data["date"].unique()
    rows = []
    for d in dates:
        for c in codes:
            rows.append({"date": d, "code": c, "signal": 1, "confidence": 0.8})
    return pd.DataFrame(rows)


class TestGenerateWindows:
    """Test window generation logic."""

    def test_correct_number_of_windows(self):
        dates = pd.bdate_range("2023-01-01", "2025-12-31")
        windows = generate_windows(dates, train_months=12, test_months=3)
        # ~36 months total, 12+3=15 month windows stepping by 3
        # Should produce roughly (36-12)/3 = 8 windows
        assert len(windows) >= 5

    def test_window_boundaries(self):
        dates = pd.bdate_range("2023-01-01", "2025-12-31")
        windows = generate_windows(dates, train_months=12, test_months=3)
        for train_start, train_end, test_start, test_end in windows:
            assert train_start < train_end
            assert train_end <= test_start
            assert test_start < test_end

    def test_no_overlap_between_test_periods(self):
        dates = pd.bdate_range("2023-01-01", "2025-12-31")
        windows = generate_windows(dates, train_months=12, test_months=3)
        for i in range(len(windows) - 1):
            _, _, _, test_end_i = windows[i]
            _, _, test_start_j, _ = windows[i + 1]
            assert test_end_i <= test_start_j

    def test_windows_fit_within_data_range(self):
        dates = pd.bdate_range("2023-01-01", "2025-12-31")
        windows = generate_windows(dates, train_months=12, test_months=3)
        data_start = dates[0]
        data_end = dates[-1]
        for train_start, _, _, test_end in windows:
            assert train_start >= data_start
            assert test_end <= data_end

    def test_insufficient_data_returns_empty(self):
        dates = pd.bdate_range("2023-01-01", "2023-06-01")
        windows = generate_windows(dates, train_months=12, test_months=3)
        assert len(windows) == 0


class TestWalkForwardBacktest:
    """Test walk-forward backtest execution."""

    def test_returns_dataframe(self):
        data = _make_stock_data("2023-01-01", "2025-12-31")
        result = walk_forward_backtest(
            data, _dummy_signal_fn, train_months=12, test_months=3
        )
        assert isinstance(result, pd.DataFrame)

    def test_result_has_expected_columns(self):
        data = _make_stock_data("2023-01-01", "2025-12-31")
        result = walk_forward_backtest(
            data, _dummy_signal_fn, train_months=12, test_months=3
        )
        expected_cols = {
            "period", "train_start", "train_end",
            "test_start", "test_end", "total_return", "annual_return",
            "sharpe_ratio", "max_drawdown", "win_rate", "trade_count",
        }
        assert expected_cols.issubset(set(result.columns))

    def test_result_has_rows(self):
        data = _make_stock_data("2023-01-01", "2025-12-31")
        result = walk_forward_backtest(
            data, _dummy_signal_fn, train_months=12, test_months=3
        )
        assert len(result) > 0

    def test_metrics_are_numeric(self):
        data = _make_stock_data("2023-01-01", "2025-12-31")
        result = walk_forward_backtest(
            data, _dummy_signal_fn, train_months=12, test_months=3
        )
        for col in ["total_return", "annual_return", "sharpe_ratio", "max_drawdown"]:
            assert pd.api.types.is_numeric_dtype(result[col])

    def test_period_is_sequential(self):
        data = _make_stock_data("2023-01-01", "2025-12-31")
        result = walk_forward_backtest(
            data, _dummy_signal_fn, train_months=12, test_months=3
        )
        assert (result["period"] == range(1, len(result) + 1)).all()

    def test_with_exposure(self):
        """Walk-forward with exposure scaling."""
        data = _make_stock_data("2023-01-01", "2025-12-31")

        def signal_fn_with_exposure(train_data, test_data):
            return _dummy_signal_fn(train_data, test_data)

        result = walk_forward_backtest(
            data, signal_fn_with_exposure, train_months=12, test_months=3,
            exposure_fn=lambda dates: pd.Series(0.5, index=dates),
        )
        assert len(result) > 0
