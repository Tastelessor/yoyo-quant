"""Tests for the unified backtest pipeline (src/backtest/pipeline.py).

Covers the three public functions:
- build_positions: signals -> positions (+ prices)
- run_backtest: positions -> BacktestEngine result
- run_pipeline: full chain signals -> positions -> engine result
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.backtest.engine import BacktestEngine, TradingCost
from src.backtest.pipeline import build_positions, run_backtest, run_pipeline
from src.portfolio.allocator import equal_weight
from src.risk.position_limit import apply_position_limit
from src.risk.tradability import enforce_t1, filter_tradable


def _make_stock_data(codes=None, days=10, seed=42, limit_up_codes=None):
    """Create synthetic OHLCV data with market-status columns."""
    if codes is None:
        codes = ["000001", "000002"]
    dates = pd.bdate_range("2024-01-01", periods=days)
    rows = []
    rng = np.random.RandomState(seed)
    limit_up_set = set(limit_up_codes or [])
    for code in codes:
        price = 100.0
        for d in dates:
            price *= 1 + rng.normal(0, 0.01)
            rows.append(
                {
                    "date": d,
                    "code": code,
                    "open": price,
                    "high": price * 1.01,
                    "low": price * 0.99,
                    "close": price,
                    "volume": 1_000_000,
                    "limit_up": code in limit_up_set,
                    "limit_down": False,
                    "is_suspended": False,
                }
            )
    return pd.DataFrame(rows)


def _buy_all_signals(data, signal=1):
    """Buy everything on every day."""
    rows = []
    for d in data["date"].unique():
        for c in data["code"].unique():
            rows.append({"date": d, "code": c, "signal": signal, "confidence": 0.8})
    return pd.DataFrame(rows)


class TestBuildPositions:
    """Tests for build_positions: signals -> positions + prices."""

    def test_returns_positions_and_prices(self):
        data = _make_stock_data()
        signals = _buy_all_signals(data)
        positions, prices = build_positions(signals, data, capital=1_000_000)
        assert list(positions.columns) == ["date", "code", "weight", "shares"]
        assert list(prices.columns) == ["date", "code", "close"]
        assert not positions.empty
        # prices deduplicated on (date, code)
        assert prices.duplicated(subset=["date", "code"]).sum() == 0
        # weights sum to 1 per date
        per_date = positions.groupby("date")["weight"].sum()
        assert per_date.max() == pytest.approx(1.0)

    def test_filters_limit_up_buy(self):
        data = _make_stock_data(limit_up_codes={"000001"})
        signals = _buy_all_signals(data)
        positions, _ = build_positions(signals, data, capital=1_000_000)
        # 000001 is limit-up on every day -> never bought
        assert positions["code"].isin(["000001"]).sum() == 0
        # 000002 still held
        assert positions["code"].isin(["000002"]).any()

    def test_exposure_scales_shares(self):
        data = _make_stock_data()
        signals = _buy_all_signals(data)
        dates = pd.DatetimeIndex(sorted(data["date"].unique()))
        exposure = pd.Series(0.5, index=dates)
        _, prices = build_positions(signals, data, capital=1_000_000)
        pos_full, _ = build_positions(signals, data, capital=1_000_000)
        pos_half, _ = build_positions(
            signals, data, capital=1_000_000, exposure=exposure
        )
        assert not pos_half.empty
        assert (pos_half["shares"] <= pos_full["shares"]).all()

    def test_rebalance_days_sparsifies_signals(self):
        data = _make_stock_data(days=10)
        signals = _buy_all_signals(data)
        positions, _ = build_positions(
            signals, data, capital=1_000_000, rebalance_days=2
        )
        n_dates = positions["date"].nunique()
        assert n_dates == 5  # every 2nd of 10 days

    def test_prev_positions_cold_start(self):
        """Dead-zone smoothing carries previous period positions into
        the current period (resurrected stock kept via init_state)."""
        data = _make_stock_data(days=10)
        # Period 1: hold A and B (equal weight 0.5 each)
        sig1 = _buy_all_signals(data)
        pos1, _ = build_positions(sig1, data, capital=1_000_000, dead_zone=0.01)
        assert not pos1.empty
        # Period 2: only A gets a buy signal; B is gone from signals.
        # With dead_zone=0.6 and prev init_state {A:0.5, B:0.5},
        # B's weight change (0 -> 0.5) is below the dead zone -> held.
        sig2 = _buy_all_signals(data)
        sig2 = sig2[sig2["code"] == "000001"]
        pos2, _ = build_positions(
            sig2,
            data,
            capital=1_000_000,
            dead_zone=0.6,
            prev_positions=pos1,
        )
        assert "000002" in pos2["code"].values
        b_w = pos2[pos2["code"] == "000002"]["weight"].iloc[0]
        assert 0.0 < b_w < 1.0

    def test_empty_signals_returns_empty(self):
        data = _make_stock_data()
        empty = pd.DataFrame(columns=["date", "code", "signal", "confidence"])
        positions, prices = build_positions(empty, data, capital=1_000_000)
        assert positions.empty
        assert list(positions.columns) == ["date", "code", "weight", "shares"]
        assert not prices.empty

    def test_missing_market_status_columns_raises(self):
        data = _make_stock_data()
        data = data.drop(columns=["limit_up", "limit_down", "is_suspended"])
        signals = _buy_all_signals(data)
        with pytest.raises((KeyError, ValueError)):
            build_positions(signals, data, capital=1_000_000)


class TestRunBacktest:
    """Tests for run_backtest: positions -> engine result."""

    def test_returns_full_result(self):
        data = _make_stock_data()
        signals = _buy_all_signals(data)
        positions, prices = build_positions(signals, data, capital=1_000_000)
        result = run_backtest(positions, prices, data, capital=1_000_000)
        assert set(result.keys()) == {"trades", "equity_curve", "metrics"}
        assert not result["equity_curve"].empty
        assert "total_return" in result["metrics"]

    def test_starting_capital_override(self):
        data = _make_stock_data()
        signals = _buy_all_signals(data)
        positions, prices = build_positions(signals, data, capital=1_000_000)
        result = run_backtest(
            positions,
            prices,
            data,
            capital=1_000_000,
            starting_capital=1_200_000,
        )
        assert result["equity_curve"]["equity"].iloc[0] == pytest.approx(1_200_000)

    def test_trading_cost_forwarded(self):
        data = _make_stock_data()
        signals = _buy_all_signals(data)
        positions, prices = build_positions(signals, data, capital=1_000_000)
        cost = TradingCost(commission=0.001, stamp_tax=0.0005, transfer_fee=0.00002)
        result = run_backtest(
            positions, prices, data, capital=1_000_000, trading_cost=cost
        )
        assert result["metrics"]["total_cost"] > 0

    def test_empty_positions_ok(self):
        data = _make_stock_data()
        empty = pd.DataFrame(columns=["date", "code", "weight", "shares"])
        prices = data[["date", "code", "close"]].drop_duplicates()
        result = run_backtest(empty, prices, data, capital=1_000_000)
        assert result["metrics"]["total_return"] == 0.0


class TestRunPipeline:
    """Tests for run_pipeline: full chain, single entry point."""

    def test_full_result_shape(self):
        data = _make_stock_data()
        signals = _buy_all_signals(data)
        result = run_pipeline(signals, data, capital=1_000_000)
        assert set(result.keys()) == {
            "positions",
            "carry_positions",
            "prices",
            "trades",
            "equity_curve",
            "metrics",
        }
        assert not result["positions"].empty
        assert not result["equity_curve"].empty

    def test_equivalence_with_manual_chain(self):
        """Default-config run_pipeline matches the manual chain that
        param_sweep/pool_matrix used to hand-write."""
        data = _make_stock_data()
        signals = _buy_all_signals(data)

        # Manual chain (old style)
        filtered = filter_tradable(data, signals)
        final = enforce_t1(filtered)
        prices = data[["date", "code", "close"]].drop_duplicates()
        positions = equal_weight(final, prices, capital=1_000_000)
        positions = apply_position_limit(positions, max_weight=0.3)
        engine = BacktestEngine(capital=1_000_000)
        manual = engine.run(positions, prices)["metrics"]

        result = run_pipeline(signals, data, capital=1_000_000)
        auto = result["metrics"]

        for key in [
            "total_return",
            "annual_return",
            "sharpe_ratio",
            "max_drawdown",
            "trade_count",
        ]:
            assert auto[key] == pytest.approx(manual[key], abs=1e-9)

    def test_carry_positions_equals_pre_cap_positions(self):
        """carry_positions is the pre-industry-cap/pre-position-limit state
        (used for cross-period smoothing cold start)."""
        data = _make_stock_data()
        signals = _buy_all_signals(data)
        industry_map = {"000001": "bank", "000002": "tech"}
        result = run_pipeline(
            signals,
            data,
            capital=1_000_000,
            industry_map=industry_map,
            max_industry_weight=0.5,
            max_weight=0.5,
        )
        # With no cap triggered (each industry has one stock, 0.5 <= cap)
        # and no position limit triggered (0.5 <= max_weight), carry == positions
        carry = (
            result["carry_positions"]
            .sort_values(["date", "code"])
            .reset_index(drop=True)
        )
        final = result["positions"].sort_values(["date", "code"]).reset_index(drop=True)
        pd.testing.assert_frame_equal(carry, final)

    def test_industry_cap_applied(self):
        data = _make_stock_data()
        signals = _buy_all_signals(data)
        industry_map = {"000001": "bank", "000002": "bank"}
        result = run_pipeline(
            signals,
            data,
            capital=1_000_000,
            industry_map=industry_map,
            max_industry_weight=0.5,
        )
        # Both stocks in one industry capped at 0.5 -> per-industry weight <= cap
        # (all-industries-over-cap case: excess becomes cash, sum may be < 1)
        pos = result["positions"].copy()
        pos["industry"] = pos["code"].map(industry_map)
        ind_w = pos.groupby(["date", "industry"])["weight"].sum()
        assert ind_w.max() <= 0.5 + 1e-9

    def test_position_limit_applied(self):
        # 2 stocks -> equal weight 0.5 each > max_weight 0.4 -> cap triggered
        data = _make_stock_data(codes=["000001", "000002"])
        signals = _buy_all_signals(data)
        result = run_pipeline(signals, data, capital=1_000_000, max_weight=0.4)
        max_w = result["positions"].groupby("date")["weight"].max()
        assert max_w.max() <= 0.4 + 1e-9

    def test_empty_signals_returns_empty_result(self):
        data = _make_stock_data()
        empty = pd.DataFrame(columns=["date", "code", "signal", "confidence"])
        result = run_pipeline(empty, data, capital=1_000_000)
        assert result["positions"].empty
        assert result["metrics"]["total_return"] == 0.0
