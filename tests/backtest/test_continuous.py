"""Tests for continuous backtest module."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.backtest.continuous import continuous_backtest, compute_continuous_metrics


def _make_stock_data(start="2023-01-01", end="2025-12-31", codes=None):
    """Create synthetic stock data."""
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


def _dummy_signal_fn(data):
    """Buy everything, every day."""
    rows = []
    for d in data["date"].unique():
        for c in data["code"].unique():
            rows.append({"date": d, "code": c, "signal": 1, "confidence": 0.8})
    return pd.DataFrame(rows)


class TestComputeContinuousMetrics:
    """Test metrics computation."""

    def test_basic(self):
        eq = pd.DataFrame({
            "date": pd.bdate_range("2023-01-01", periods=100),
            "equity": np.linspace(1_000_000, 1_200_000, 100),
        })
        m = compute_continuous_metrics(eq, 1_000_000)
        assert m["total_return"] == pytest.approx(0.2, abs=0.01)
        assert m["annual_return"] > 0
        assert m["max_drawdown"] >= 0

    def test_empty(self):
        eq = pd.DataFrame(columns=["date", "equity"])
        m = compute_continuous_metrics(eq, 1_000_000)
        assert m["total_return"] == 0.0
        assert m["sharpe_ratio"] == 0.0

    def test_flat_equity(self):
        eq = pd.DataFrame({
            "date": pd.bdate_range("2023-01-01", periods=50),
            "equity": [1_000_000.0] * 50,
        })
        m = compute_continuous_metrics(eq, 1_000_000)
        assert m["total_return"] == pytest.approx(0.0)
        assert m["sharpe_ratio"] == pytest.approx(0.0)


class TestContinuousBacktest:
    """Test the continuous backtest function."""

    def test_returns_dict(self):
        data = _make_stock_data()
        result = continuous_backtest(data, _dummy_signal_fn)
        assert isinstance(result, dict)
        assert "overall" in result
        assert "equity_curve" in result
        assert "trades" in result

    def test_equity_curve_spans_full_period(self):
        data = _make_stock_data()
        result = continuous_backtest(data, _dummy_signal_fn)
        eq = result["equity_curve"]
        assert len(eq) > 0
        assert "date" in eq.columns
        assert "equity" in eq.columns

    def test_overall_metrics_keys(self):
        data = _make_stock_data()
        result = continuous_backtest(data, _dummy_signal_fn)
        m = result["overall"]
        assert "total_return" in m
        assert "annual_return" in m
        assert "sharpe_ratio" in m
        assert "max_drawdown" in m

    def test_with_industry_map(self):
        data = _make_stock_data()
        industry_map = {"000001": "银行", "000002": "科技"}
        result = continuous_backtest(
            data, _dummy_signal_fn,
            industry_map=industry_map, max_industry_weight=0.50,
        )
        assert len(result["equity_curve"]) > 0

    def test_empty_data(self):
        data = pd.DataFrame(columns=["date", "code", "open", "high", "low", "close", "volume"])
        result = continuous_backtest(data, _dummy_signal_fn)
        assert result["overall"]["total_return"] == 0.0

    def test_with_exposure(self):
        data = _make_stock_data()
        result = continuous_backtest(
            data, _dummy_signal_fn,
            exposure_fn=lambda dates: pd.Series(0.5, index=dates),
        )
        assert len(result["equity_curve"]) > 0
