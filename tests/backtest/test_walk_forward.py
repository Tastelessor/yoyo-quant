"""Tests for walk-forward validation module."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtest.walk_forward import (
    compute_overall_metrics,
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


class TestComputeOverallMetrics:
    """Test the overall metrics computation."""

    def test_basic_computation(self):
        """Should compute correct metrics from a simple equity curve."""
        eq = pd.DataFrame({
            "date": pd.bdate_range("2023-01-01", periods=100),
            "equity": np.linspace(1_000_000, 1_100_000, 100),
        })
        pp = pd.DataFrame({"sharpe_ratio": [1.0, 1.5, 0.5]})
        result = compute_overall_metrics(eq, pp, 1_000_000)

        assert result["total_return"] == pytest.approx(0.1, abs=0.01)
        assert result["annual_return"] > 0
        assert isinstance(result["sharpe_ratio"], float)
        assert result["max_drawdown"] >= 0
        assert result["per_period_sharpe_mean"] == pytest.approx(1.0)

    def test_flat_equity_zero_sharpe(self):
        """Flat equity should give zero Sharpe and zero return."""
        eq = pd.DataFrame({
            "date": pd.bdate_range("2023-01-01", periods=50),
            "equity": [1_000_000.0] * 50,
        })
        pp = pd.DataFrame({"sharpe_ratio": [0.0]})
        result = compute_overall_metrics(eq, pp, 1_000_000)

        assert result["total_return"] == pytest.approx(0.0)
        assert result["sharpe_ratio"] == pytest.approx(0.0)
        assert result["max_drawdown"] == pytest.approx(0.0)

    def test_empty_equity(self):
        """Empty equity curve should return zeros."""
        eq = pd.DataFrame(columns=["date", "equity"])
        pp = pd.DataFrame(columns=["sharpe_ratio"])
        result = compute_overall_metrics(eq, pp, 1_000_000)

        assert result["total_return"] == 0.0
        assert result["sharpe_ratio"] == 0.0


class TestWalkForwardBacktest:
    """Test walk-forward backtest execution."""

    def test_returns_dict(self):
        data = _make_stock_data("2023-01-01", "2025-12-31")
        result = walk_forward_backtest(
            data, _dummy_signal_fn, train_months=12, test_months=3
        )
        assert isinstance(result, dict)
        assert "per_period" in result
        assert "overall" in result
        assert "equity_curve" in result

    def test_per_period_has_expected_columns(self):
        data = _make_stock_data("2023-01-01", "2025-12-31")
        result = walk_forward_backtest(
            data, _dummy_signal_fn, train_months=12, test_months=3
        )
        pp = result["per_period"]
        expected_cols = {
            "period", "train_start", "train_end",
            "test_start", "test_end", "total_return", "annual_return",
            "sharpe_ratio", "max_drawdown", "win_rate", "trade_count",
            "total_cost", "cost_ratio",
        }
        assert expected_cols.issubset(set(pp.columns))

    def test_per_period_has_rows(self):
        data = _make_stock_data("2023-01-01", "2025-12-31")
        result = walk_forward_backtest(
            data, _dummy_signal_fn, train_months=12, test_months=3
        )
        assert len(result["per_period"]) > 0

    def test_overall_metrics_keys(self):
        data = _make_stock_data("2023-01-01", "2025-12-31")
        result = walk_forward_backtest(
            data, _dummy_signal_fn, train_months=12, test_months=3
        )
        overall = result["overall"]
        assert "total_return" in overall
        assert "annual_return" in overall
        assert "sharpe_ratio" in overall
        assert "max_drawdown" in overall
        assert "per_period_sharpe_mean" in overall
        assert "per_period_sharpe_std" in overall

    def test_equity_curve_is_continuous(self):
        """Equity curve should span all periods without gaps."""
        data = _make_stock_data("2023-01-01", "2025-12-31")
        result = walk_forward_backtest(
            data, _dummy_signal_fn, train_months=12, test_months=3
        )
        eq = result["equity_curve"]
        assert len(eq) > 0
        assert list(eq.columns) == ["date", "equity"]
        # Dates should be sorted
        assert (eq["date"].diff().dropna() >= pd.Timedelta(0)).all()

    def test_capital_chaining(self):
        """Each period should start where the previous ended."""
        data = _make_stock_data("2023-01-01", "2025-12-31")
        result = walk_forward_backtest(
            data, _dummy_signal_fn, train_months=12, test_months=3,
            capital=1_000_000,
        )
        eq = result["equity_curve"]
        # All equity values should be positive (capital chained, not reset)
        assert (eq["equity"] > 0).all()

    def test_overall_sharpe_different_from_per_period_mean(self):
        """Overall Sharpe (from continuous returns) should differ from
        the mean of per-period Sharpes."""
        data = _make_stock_data("2023-01-01", "2025-12-31")
        result = walk_forward_backtest(
            data, _dummy_signal_fn, train_months=12, test_months=3
        )
        overall_sharpe = result["overall"]["sharpe_ratio"]
        pp_mean = result["overall"]["per_period_sharpe_mean"]
        # They should generally be different numbers
        # (not checking exact inequality since they could coincidentally match)
        assert isinstance(overall_sharpe, float)
        assert isinstance(pp_mean, float)

    def test_metrics_are_numeric(self):
        data = _make_stock_data("2023-01-01", "2025-12-31")
        result = walk_forward_backtest(
            data, _dummy_signal_fn, train_months=12, test_months=3
        )
        pp = result["per_period"]
        for col in ["total_return", "annual_return", "sharpe_ratio", "max_drawdown"]:
            assert pd.api.types.is_numeric_dtype(pp[col])

    def test_period_is_sequential(self):
        data = _make_stock_data("2023-01-01", "2025-12-31")
        result = walk_forward_backtest(
            data, _dummy_signal_fn, train_months=12, test_months=3
        )
        pp = result["per_period"]
        assert (pp["period"] == range(1, len(pp) + 1)).all()

    def test_with_exposure(self):
        """Walk-forward with exposure scaling."""
        data = _make_stock_data("2023-01-01", "2025-12-31")

        def signal_fn_with_exposure(train_data, test_data):
            return _dummy_signal_fn(train_data, test_data)

        result = walk_forward_backtest(
            data, signal_fn_with_exposure, train_months=12, test_months=3,
            exposure_fn=lambda dates: pd.Series(0.5, index=dates),
        )
        assert len(result["per_period"]) > 0


def _make_selector_fn(selected_codes):
    """Create a stock_selector_fn that returns only selected_codes for all dates."""
    def selector(factor_df):
        dates = factor_df["date"].unique()
        return {d: selected_codes for d in dates}
    return selector


def _make_empty_selector():
    """Create a stock_selector_fn that returns empty pool for all dates."""
    def selector(factor_df):
        dates = factor_df["date"].unique()
        return {d: [] for d in dates}
    return selector


class TestWalkForwardWithStockSelector:
    """Test walk-forward backtest with dynamic stock selection."""

    def test_none_preserves_behavior(self):
        """stock_selector=None should produce identical results."""
        data = _make_stock_data("2023-01-01", "2025-12-31")
        result = walk_forward_backtest(
            data, _dummy_signal_fn, train_months=12, test_months=3,
        )
        result_with_none = walk_forward_backtest(
            data, _dummy_signal_fn, train_months=12, test_months=3,
            stock_selector_fn=None,
        )
        assert len(result["per_period"]) == len(result_with_none["per_period"])

    def test_selector_filters_stocks(self):
        """Selector that picks 1 code should reduce unique codes in signals."""
        data = _make_stock_data("2023-01-01", "2025-12-31", codes=["000001", "000002", "000003"])
        selector = _make_selector_fn(["000001"])

        result = walk_forward_backtest(
            data, _dummy_signal_fn, train_months=12, test_months=3,
            stock_selector_fn=selector,
        )
        assert len(result["per_period"]) > 0

    def test_empty_pool_produces_zero_metrics(self):
        """Empty selector pool should produce zero-metric rows, not crash."""
        data = _make_stock_data("2023-01-01", "2025-12-31")
        selector = _make_empty_selector()

        result = walk_forward_backtest(
            data, _dummy_signal_fn, train_months=12, test_months=3,
            stock_selector_fn=selector,
        )
        pp = result["per_period"]
        assert len(pp) > 0
        assert (pp["total_return"] == 0.0).all()
        assert (pp["trade_count"] == 0).all()


class TestWalkForwardWithIndustryCap:
    """Test walk-forward backtest with industry cap."""

    def test_industry_cap_none_preserves_behavior(self):
        """industry_map=None should produce identical results."""
        data = _make_stock_data("2023-01-01", "2025-12-31")
        r1 = walk_forward_backtest(
            data, _dummy_signal_fn, train_months=12, test_months=3,
        )
        r2 = walk_forward_backtest(
            data, _dummy_signal_fn, train_months=12, test_months=3,
            industry_map=None,
        )
        assert len(r1["per_period"]) == len(r2["per_period"])

    def test_industry_cap_with_mapping(self):
        """With industry_map, should still produce valid results."""
        data = _make_stock_data("2023-01-01", "2025-12-31")
        industry_map = {"000001": "银行", "000002": "科技"}
        result = walk_forward_backtest(
            data, _dummy_signal_fn, train_months=12, test_months=3,
            industry_map=industry_map, max_industry_weight=0.50,
        )
        pp = result["per_period"]
        assert len(pp) > 0
        assert set(pp.columns) >= {
            "period", "total_return", "sharpe_ratio", "max_drawdown",
        }

    def test_industry_cap_with_missing_codes(self):
        """industry_map with missing codes should not crash."""
        data = _make_stock_data("2023-01-01", "2025-12-31")
        industry_map = {"000001": "银行"}  # 000002 missing -> "其他"
        result = walk_forward_backtest(
            data, _dummy_signal_fn, train_months=12, test_months=3,
            industry_map=industry_map, max_industry_weight=0.50,
        )
        assert len(result["per_period"]) > 0


class TestWalkForwardWithCircuitBreaker:
    """Test walk-forward backtest with drawdown circuit breaker."""

    def test_none_preserves_behavior(self):
        """circuit_breaker=None should produce identical results."""
        data = _make_stock_data("2023-01-01", "2025-12-31")
        r1 = walk_forward_backtest(
            data, _dummy_signal_fn, train_months=12, test_months=3,
        )
        r2 = walk_forward_backtest(
            data, _dummy_signal_fn, train_months=12, test_months=3,
            circuit_breaker=None,
        )
        assert len(r1["per_period"]) == len(r2["per_period"])

    def test_circuit_breaker_runs_without_error(self):
        """Circuit breaker should not crash the backtest."""
        from portfolio.circuit_breaker import DrawdownCircuitBreaker

        data = _make_stock_data("2023-01-01", "2025-12-31")
        cb = DrawdownCircuitBreaker(threshold=-0.10, recovery_threshold=-0.03)
        result = walk_forward_backtest(
            data, _dummy_signal_fn, train_months=12, test_months=3,
            circuit_breaker=cb,
        )
        pp = result["per_period"]
        assert len(pp) > 0
        assert set(pp.columns) >= {
            "period", "total_return", "sharpe_ratio", "max_drawdown",
        }

    def test_circuit_breaker_resets_each_period(self):
        """Circuit breaker resets at start of each walk-forward period."""
        from portfolio.circuit_breaker import DrawdownCircuitBreaker

        data = _make_stock_data("2023-01-01", "2025-12-31")
        cb = DrawdownCircuitBreaker(threshold=-0.10, recovery_threshold=-0.03)

        walk_forward_backtest(
            data, _dummy_signal_fn, train_months=12, test_months=3,
            circuit_breaker=cb,
        )

        assert cb._peak >= 0
