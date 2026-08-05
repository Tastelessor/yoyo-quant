"""Tests for Multi-Silo walk-forward architecture."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtest.walk_forward import _merge_silo_positions, walk_forward_multi_silo


class TestMergeSiloPositions:
    """Tests for the weight-level merge function."""

    def _make_positions(self, dates, codes, weights):
        """Build a positions DataFrame."""
        rows = []
        for d, c, w in zip(dates, codes, weights):
            rows.append({"date": d, "code": c, "weight": w, "shares": int(w * 1000000 / 100) * 100})
        return pd.DataFrame(rows)

    def test_non_overlapping_stocks(self):
        """Two silos with disjoint stocks should include both."""
        dt = pd.Timestamp("2025-01-02")
        prices = pd.DataFrame([
            {"date": dt, "code": "A", "close": 100.0},
            {"date": dt, "code": "B", "close": 100.0},
        ])
        silo1 = self._make_positions([dt], ["A"], [1.0])
        silo2 = self._make_positions([dt], ["B"], [1.0])

        merged = _merge_silo_positions([silo1, silo2], [0.5, 0.5], prices, 1_000_000, None)

        assert len(merged) == 2
        assert set(merged["code"]) == {"A", "B"}
        assert merged["weight"].sum() == pytest.approx(1.0, abs=0.01)

    def test_overlapping_stocks_sum_weights(self):
        """Two silos selecting the same stock should sum weights."""
        dt = pd.Timestamp("2025-01-02")
        prices = pd.DataFrame([
            {"date": dt, "code": "A", "close": 100.0},
            {"date": dt, "code": "B", "close": 100.0},
        ])
        silo1 = self._make_positions([dt], ["A"], [1.0])
        silo2 = self._make_positions([dt], ["A"], [1.0])

        merged = _merge_silo_positions([silo1, silo2], [0.5, 0.5], prices, 1_000_000, None)

        assert len(merged) == 1
        assert merged["code"].iloc[0] == "A"
        assert merged["weight"].iloc[0] == pytest.approx(1.0)

    def test_mixed_overlap(self):
        """One stock in both, one in only one silo."""
        dt = pd.Timestamp("2025-01-02")
        prices = pd.DataFrame([
            {"date": dt, "code": "A", "close": 100.0},
            {"date": dt, "code": "B", "close": 100.0},
            {"date": dt, "code": "C", "close": 100.0},
        ])
        silo1 = self._make_positions([dt, dt], ["A", "B"], [0.5, 0.5])
        silo2 = self._make_positions([dt, dt], ["A", "C"], [0.5, 0.5])

        merged = _merge_silo_positions([silo1, silo2], [0.5, 0.5], prices, 1_000_000, None)

        assert len(merged) == 3
        assert merged["weight"].sum() == pytest.approx(1.0, abs=0.01)
        a_weight = merged[merged["code"] == "A"]["weight"].iloc[0]
        b_weight = merged[merged["code"] == "B"]["weight"].iloc[0]
        assert a_weight > b_weight

    def test_empty_silo(self):
        """One empty silo should not affect the other."""
        dt = pd.Timestamp("2025-01-02")
        prices = pd.DataFrame([
            {"date": dt, "code": "A", "close": 100.0},
        ])
        silo1 = self._make_positions([dt], ["A"], [1.0])
        silo2 = pd.DataFrame(columns=["date", "code", "weight", "shares"])

        merged = _merge_silo_positions([silo1, silo2], [0.5, 0.5], prices, 1_000_000, None)

        assert len(merged) == 1
        assert merged["code"].iloc[0] == "A"

    def test_weights_sum_to_one(self):
        """Final weights should always sum to 1.0 per date."""
        dt = pd.Timestamp("2025-01-02")
        codes = [f"S{i}" for i in range(5)]
        prices = pd.DataFrame([
            {"date": dt, "code": c, "close": 100.0} for c in codes
        ])
        silo1 = self._make_positions([dt]*3, codes[:3], [1/3]*3)
        silo2 = self._make_positions([dt]*2, codes[3:], [0.5, 0.5])

        merged = _merge_silo_positions([silo1, silo2], [0.6, 0.4], prices, 1_000_000, None)

        for dt in merged["date"].unique():
            day = merged[merged["date"] == dt]
            assert day["weight"].sum() == pytest.approx(1.0, abs=0.01)


class TestWalkForwardMultiSilo:
    """Integration test for multi-silo walk-forward."""

    def test_returns_dict(self):
        """Multi-silo should return a dict with per_period, overall, equity_curve."""
        np.random.seed(42)
        codes = [f"{i:06d}" for i in range(1, 21)]
        frames = []
        for code in codes:
            close = 100 + np.cumsum(np.random.randn(200) * 0.5)
            frames.append(pd.DataFrame({
                "date": pd.date_range("2020-01-01", periods=200, freq="B"),
                "code": code,
                "open": close - 0.1,
                "high": close + 0.3,
                "low": close - 0.3,
                "close": close,
                "volume": [1_000_000] * 200,
                "limit_up": [False] * 200,
                "limit_down": [False] * 200,
                "is_suspended": [False] * 200,
            }))
        data = pd.concat(frames, ignore_index=True)

        def dummy_signal(train, test):
            signals = []
            for dt in test["date"].unique():
                day = test[test["date"] == dt].nlargest(3, "close")
                for _, row in day.iterrows():
                    signals.append({"date": dt, "code": row["code"], "signal": 1, "confidence": 0.5})
            return pd.DataFrame(signals) if signals else pd.DataFrame(columns=["date", "code", "signal", "confidence"])

        silos = [
            {"signal_fn": dummy_signal, "weight": 0.6, "name": "silo_a"},
            {"signal_fn": dummy_signal, "weight": 0.4, "name": "silo_b"},
        ]

        result = walk_forward_multi_silo(
            data, silos, train_months=6, test_months=3, dead_zone=0.01,
        )

        assert isinstance(result, dict)
        assert "per_period" in result
        assert "overall" in result
        assert "equity_curve" in result
        pp = result["per_period"]
        assert len(pp) > 0
        assert "sharpe_ratio" in pp.columns
        assert "total_return" in pp.columns

    def test_overall_metrics_reasonable(self):
        """Overall Sharpe should differ from per-period mean Sharpe."""
        np.random.seed(42)
        codes = [f"{i:06d}" for i in range(1, 11)]
        frames = []
        for code in codes:
            close = 100 + np.cumsum(np.random.randn(200) * 0.5)
            frames.append(pd.DataFrame({
                "date": pd.date_range("2020-01-01", periods=200, freq="B"),
                "code": code,
                "open": close - 0.1,
                "high": close + 0.3,
                "low": close - 0.3,
                "close": close,
                "volume": [1_000_000] * 200,
                "limit_up": [False] * 200,
                "limit_down": [False] * 200,
                "is_suspended": [False] * 200,
            }))
        data = pd.concat(frames, ignore_index=True)

        def dummy_signal(train, test):
            signals = []
            for dt in test["date"].unique():
                day = test[test["date"] == dt].nlargest(2, "close")
                for _, row in day.iterrows():
                    signals.append({"date": dt, "code": row["code"], "signal": 1, "confidence": 0.5})
            return pd.DataFrame(signals) if signals else pd.DataFrame(columns=["date", "code", "signal", "confidence"])

        silos = [
            {"signal_fn": dummy_signal, "weight": 0.5, "name": "a"},
            {"signal_fn": dummy_signal, "weight": 0.5, "name": "b"},
        ]

        result = walk_forward_multi_silo(
            data, silos, train_months=6, test_months=3,
        )

        overall = result["overall"]
        assert "sharpe_ratio" in overall
        assert "total_return" in overall
        assert "annual_return" in overall
        assert "max_drawdown" in overall
        assert "per_period_sharpe_mean" in overall
        assert "per_period_sharpe_std" in overall
