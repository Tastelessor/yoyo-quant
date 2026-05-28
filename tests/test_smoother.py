"""Tests for portfolio position smoothing (dead-zone state machine)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.portfolio.smoother import smooth_positions


# ── Helpers ──────────────────────────────────────────────────────────


def _pos(date, code, weight, shares=0):
    """Build a single-row positions dict."""
    return {"date": pd.Timestamp(date), "code": code, "weight": weight, "shares": shares}


def _price(date, code, close):
    return {"date": pd.Timestamp(date), "code": code, "close": close}


def _positions_df(rows):
    return pd.DataFrame(rows)


def _prices_df(rows):
    return pd.DataFrame(rows)


# ── Normal path ──────────────────────────────────────────────────────


class TestSmoothPositions:
    """Core smoothing logic tests."""

    def test_single_day_passthrough(self):
        """Single day: nothing to smooth, return as-is."""
        current = _positions_df([
            _pos("2026-01-01", "A", 0.5, 100),
            _pos("2026-01-01", "B", 0.5, 200),
        ])
        prices = _prices_df([
            _price("2026-01-01", "A", 10.0),
            _price("2026-01-01", "B", 20.0),
        ])
        result = smooth_positions(current, None, prices, capital=100_000, exposure=None, dead_zone=0.01)

        assert len(result) == 2
        assert set(result["code"]) == {"A", "B"}
        # Weights should sum to 1.0
        assert result["weight"].sum() == pytest.approx(1.0, abs=1e-10)

    def test_dead_zone_blocks_small_drift(self):
        """Day 2: stock A drifts from 0.50 to 0.49 (delta=0.01 < dead_zone=0.015).
        State machine should hold A at 0.50."""
        current = _positions_df([
            # Day 1
            _pos("2026-01-01", "A", 0.50, 5000),
            _pos("2026-01-01", "B", 0.50, 2500),
            # Day 2: A drifted slightly down
            _pos("2026-01-02", "A", 0.49, 4900),
            _pos("2026-01-02", "B", 0.51, 2550),
        ])
        prices = _prices_df([
            _price("2026-01-01", "A", 10.0),
            _price("2026-01-01", "B", 20.0),
            _price("2026-01-02", "A", 10.0),
            _price("2026-01-02", "B", 20.0),
        ])
        result = smooth_positions(current, None, prices, capital=100_000, exposure=None, dead_zone=0.015)

        day2 = result[result["date"] == pd.Timestamp("2026-01-02")]
        a_w = day2[day2["code"] == "A"]["weight"].iloc[0]
        b_w = day2[day2["code"] == "B"]["weight"].iloc[0]

        # A should be held at 0.50 (drift 0.01 < 0.015 dead zone)
        assert a_w == pytest.approx(0.50, abs=1e-10)
        # B should also be held (drift 0.01 < 0.015)
        assert b_w == pytest.approx(0.50, abs=1e-10)

    def test_dead_zone_allows_large_change(self):
        """Day 2: stock A jumps from 0.50 to 0.80 (delta=0.30 > dead_zone=0.01).
        State machine should update A to 0.80."""
        current = _positions_df([
            _pos("2026-01-01", "A", 0.50, 5000),
            _pos("2026-01-01", "B", 0.50, 2500),
            _pos("2026-01-02", "A", 0.80, 8000),
            _pos("2026-01-02", "B", 0.20, 1000),
        ])
        prices = _prices_df([
            _price("2026-01-01", "A", 10.0),
            _price("2026-01-01", "B", 20.0),
            _price("2026-01-02", "A", 10.0),
            _price("2026-01-02", "B", 20.0),
        ])
        result = smooth_positions(current, None, prices, capital=100_000, exposure=None, dead_zone=0.01)

        day2 = result[result["date"] == pd.Timestamp("2026-01-02")]
        a_w = day2[day2["code"] == "A"]["weight"].iloc[0]

        # A should be updated to 0.80 (drift 0.30 > 0.01 dead zone)
        assert a_w == pytest.approx(0.80, abs=1e-10)

    def test_exit_stock_preserved_by_dead_zone(self):
        """Stock A has 5% weight on day 1, strategy drops it on day 2 (target=0%).
        delta = 5% > dead_zone=0.01, so A should exit (not preserved).
        But with dead_zone=0.06, delta=5% < 6%, so A should be preserved."""
        current = _positions_df([
            _pos("2026-01-01", "A", 0.05, 500),
            _pos("2026-01-01", "B", 0.45, 2250),
            _pos("2026-01-01", "C", 0.50, 2500),
            # Day 2: A dropped by strategy
            _pos("2026-01-02", "B", 0.48, 2400),
            _pos("2026-01-02", "C", 0.52, 2600),
        ])
        prices = _prices_df([
            _price("2026-01-01", "A", 10.0),
            _price("2026-01-01", "B", 20.0),
            _price("2026-01-01", "C", 30.0),
            _price("2026-01-02", "A", 10.0),
            _price("2026-01-02", "B", 20.0),
            _price("2026-01-02", "C", 30.0),
        ])

        # With small dead_zone (0.01), A exits normally (delta=0.05 > 0.01)
        result_small = smooth_positions(current, None, prices, capital=100_000, exposure=None, dead_zone=0.01)
        day2_small = result_small[result_small["date"] == pd.Timestamp("2026-01-02")]
        assert "A" not in day2_small["code"].values

        # With large dead_zone (0.06), A is preserved (delta=0.05 < 0.06)
        result_large = smooth_positions(current, None, prices, capital=100_000, exposure=None, dead_zone=0.06)
        day2_large = result_large[result_large["date"] == pd.Timestamp("2026-01-02")]
        assert "A" in day2_large["code"].values
        a_w = day2_large[day2_large["code"] == "A"]["weight"].iloc[0]
        assert a_w > 0

    def test_empty_dataframe(self):
        """Empty input returns empty output."""
        current = pd.DataFrame(columns=["date", "code", "weight", "shares"])
        prices = pd.DataFrame(columns=["date", "code", "close"])
        result = smooth_positions(current, None, prices, capital=100_000, exposure=None)
        assert result.empty

    def test_all_weights_unchanged(self):
        """When all weights are identical day-over-day, output is unchanged."""
        current = _positions_df([
            _pos("2026-01-01", "A", 0.50, 5000),
            _pos("2026-01-01", "B", 0.50, 2500),
            _pos("2026-01-02", "A", 0.50, 5000),
            _pos("2026-01-02", "B", 0.50, 2500),
        ])
        prices = _prices_df([
            _price("2026-01-01", "A", 10.0),
            _price("2026-01-01", "B", 20.0),
            _price("2026-01-02", "A", 10.0),
            _price("2026-01-02", "B", 20.0),
        ])
        result = smooth_positions(current, None, prices, capital=100_000, exposure=None, dead_zone=0.01)

        day2 = result[result["date"] == pd.Timestamp("2026-01-02")]
        assert day2["weight"].sum() == pytest.approx(1.0, abs=1e-10)
        a_w = day2[day2["code"] == "A"]["weight"].iloc[0]
        assert a_w == pytest.approx(0.50, abs=1e-10)

    def test_dead_zone_persists_over_multiple_days(self):
        """Stock A held at 5% on day 1, tiny drifts on days 2-3.
        Dead zone should hold A at 5% all 3 days, then release on day 4
        when drift exceeds threshold."""
        current = _positions_df([
            _pos("2026-01-01", "A", 0.05, 500),
            _pos("2026-01-01", "B", 0.95, 4750),
            _pos("2026-01-02", "A", 0.04, 400),   # drift=0.01 < dead_zone=0.02
            _pos("2026-01-02", "B", 0.96, 4800),
            _pos("2026-01-03", "A", 0.03, 300),   # drift=0.02 = dead_zone, still held
            _pos("2026-01-03", "B", 0.97, 4850),
            _pos("2026-01-04", "A", 0.00, 0),     # drift=0.05 > dead_zone, exits
            _pos("2026-01-04", "B", 1.00, 5000),
        ])
        prices = _prices_df([
            _price("2026-01-01", "A", 10.0), _price("2026-01-01", "B", 20.0),
            _price("2026-01-02", "A", 10.0), _price("2026-01-02", "B", 20.0),
            _price("2026-01-03", "A", 10.0), _price("2026-01-03", "B", 20.0),
            _price("2026-01-04", "A", 10.0), _price("2026-01-04", "B", 20.0),
        ])
        result = smooth_positions(current, None, prices, capital=100_000, exposure=None, dead_zone=0.02)

        # Days 1-3: A should be present (held by dead zone)
        for d in ["2026-01-01", "2026-01-02", "2026-01-03"]:
            day = result[result["date"] == pd.Timestamp(d)]
            assert "A" in day["code"].values, f"A should be present on {d}"

        # Day 4: A should exit (drift exceeded threshold)
        day4 = result[result["date"] == pd.Timestamp("2026-01-04")]
        assert "A" not in day4["code"].values, "A should exit on day 4"

    def test_weights_sum_to_one_after_dead_zone_modification(self):
        """When dead zone modifies some weights, output still sums to 1.0."""
        current = _positions_df([
            _pos("2026-01-01", "A", 0.30, 3000),
            _pos("2026-01-01", "B", 0.30, 1500),
            _pos("2026-01-01", "C", 0.40, 1333),
            # Day 2: A drifts slightly (held), B and C change more
            _pos("2026-01-02", "A", 0.29, 2900),
            _pos("2026-01-02", "B", 0.35, 1750),
            _pos("2026-01-02", "C", 0.36, 1200),
            # Day 3: larger changes
            _pos("2026-01-03", "A", 0.25, 2500),
            _pos("2026-01-03", "B", 0.40, 2000),
            _pos("2026-01-03", "C", 0.35, 1166),
        ])
        prices = _prices_df([
            _price("2026-01-01", "A", 10.0), _price("2026-01-01", "B", 20.0), _price("2026-01-01", "C", 30.0),
            _price("2026-01-02", "A", 10.0), _price("2026-01-02", "B", 20.0), _price("2026-01-02", "C", 30.0),
            _price("2026-01-03", "A", 10.0), _price("2026-01-03", "B", 20.0), _price("2026-01-03", "C", 30.0),
        ])
        result = smooth_positions(current, None, prices, capital=100_000, exposure=None, dead_zone=0.02)

        for d in ["2026-01-01", "2026-01-02", "2026-01-03"]:
            day_sum = result[result["date"] == pd.Timestamp(d)]["weight"].sum()
            assert day_sum == pytest.approx(1.0, abs=1e-10), f"Weights should sum to 1.0 on {d}"


# ── Cross-period stitching ───────────────────────────────────────────


class TestCrossPeriodStitching:
    """Tests for cold-start from previous period's last day."""

    def test_cold_start_fills_init_state(self):
        """prev period has stock A at 5%. Current period has A at 50%.
        Day 1 delta = 45% > dead_zone, so A should update to 50%."""
        current = _positions_df([
            _pos("2026-04-01", "A", 0.50, 5000),
            _pos("2026-04-01", "B", 0.50, 2500),
        ])
        prev = _positions_df([
            _pos("2026-03-31", "A", 0.05, 500),
            _pos("2026-03-31", "B", 0.95, 4750),
        ])
        prices = _prices_df([
            _price("2026-04-01", "A", 10.0),
            _price("2026-04-01", "B", 20.0),
        ])
        result = smooth_positions(current, prev, prices, capital=100_000, exposure=None, dead_zone=0.01)

        assert len(result) == 2
        a_w = result[result["code"] == "A"]["weight"].iloc[0]
        assert a_w == pytest.approx(0.50, abs=1e-10)

    def test_cross_period_stock_not_in_current_period(self):
        """Prev period has stock A at 5%. Current period NEVER has A.
        A should be reindexed into weight_matrix and preserved by dead zone.
        Caller is responsible for including prev period's prices (walk_forward
        does this by extracting from the full data DataFrame)."""
        current = _positions_df([
            _pos("2026-04-01", "B", 0.50, 2500),
            _pos("2026-04-01", "C", 0.50, 1666),
            _pos("2026-04-02", "B", 0.50, 2500),
            _pos("2026-04-02", "C", 0.50, 1666),
        ])
        prev = _positions_df([
            _pos("2026-03-31", "A", 0.05, 500),
            _pos("2026-03-31", "B", 0.45, 2250),
            _pos("2026-03-31", "C", 0.50, 1666),
        ])
        # Caller includes prev period's last-day prices for ffill seed
        prices = _prices_df([
            _price("2026-03-31", "A", 10.0),
            _price("2026-03-31", "B", 20.0),
            _price("2026-03-31", "C", 30.0),
            _price("2026-04-01", "B", 20.0),
            _price("2026-04-01", "C", 30.0),
            _price("2026-04-02", "B", 20.0),
            _price("2026-04-02", "C", 30.0),
        ])

        # With dead_zone=0.06, A's delta (0.05) < 0.06, so A is preserved
        result = smooth_positions(current, prev, prices, capital=100_000, exposure=None, dead_zone=0.06)

        # A should appear on day 1 (preserved by dead zone)
        day1 = result[result["date"] == pd.Timestamp("2026-04-01")]
        assert "A" in day1["code"].values
        a_w = day1[day1["code"] == "A"]["weight"].iloc[0]
        assert a_w > 0
        # A's close should be forward-filled from 2026-03-31
        a_shares = day1[day1["code"] == "A"]["shares"].iloc[0]
        assert a_shares > 0

    def test_ffill_price_for_resurrected_stock(self):
        """Stock A (weight 3%) dropped out of prices but preserved by dead zone.
        close should be forward-filled from last known price (10.0)."""
        current = _positions_df([
            _pos("2026-01-01", "A", 0.03, 300),
            _pos("2026-01-01", "B", 0.47, 2350),
            _pos("2026-01-01", "C", 0.50, 1666),
            # Day 2: A dropped by strategy
            _pos("2026-01-02", "B", 0.50, 2500),
            _pos("2026-01-02", "C", 0.50, 1666),
        ])
        prices = _prices_df([
            _price("2026-01-01", "A", 10.0),
            _price("2026-01-01", "B", 20.0),
            _price("2026-01-01", "C", 30.0),
            # No A on day 2
            _price("2026-01-02", "B", 20.0),
            _price("2026-01-02", "C", 30.0),
        ])
        # dead_zone=0.05 > delta=0.03, so A is preserved
        result = smooth_positions(current, None, prices, capital=100_000, exposure=None, dead_zone=0.05)

        day2 = result[result["date"] == pd.Timestamp("2026-01-02")]
        assert "A" in day2["code"].values, "Stock A should be preserved by dead zone"
        a_row = day2[day2["code"] == "A"].iloc[0]
        # Shares should be computed using forward-filled close=10.0
        expected_shares = int(np.floor(100_000 * a_row["weight"] / 10.0 / 100)) * 100
        assert a_row["shares"] == expected_shares


# ── Shares consistency ───────────────────────────────────────────────


class TestSharesConsistency:
    """Verify shares = floor(capital * weight / close / 100) * 100."""

    def test_shares_match_formula(self):
        current = _positions_df([
            _pos("2026-01-01", "A", 0.30, 3000),
            _pos("2026-01-01", "B", 0.70, 3500),
            _pos("2026-01-02", "A", 0.40, 4000),
            _pos("2026-01-02", "B", 0.60, 3000),
        ])
        prices = _prices_df([
            _price("2026-01-01", "A", 10.0),
            _price("2026-01-01", "B", 20.0),
            _price("2026-01-02", "A", 12.0),
            _price("2026-01-02", "B", 18.0),
        ])
        capital = 200_000
        result = smooth_positions(current, None, prices, capital=capital, exposure=None, dead_zone=0.01)

        for _, row in result.iterrows():
            close = prices[
                (prices["date"] == row["date"]) & (prices["code"] == row["code"])
            ]["close"].iloc[0]
            expected = int(np.floor(capital * row["weight"] / close / 100)) * 100
            assert row["shares"] == expected, f"Shares mismatch for {row['code']} on {row['date']}"

    def test_shares_with_exposure(self):
        """When exposure=0.5, capital is halved for shares calculation."""
        current = _positions_df([
            _pos("2026-01-01", "A", 1.00, 5000),
        ])
        prices = _prices_df([
            _price("2026-01-01", "A", 10.0),
        ])
        exposure = pd.Series({pd.Timestamp("2026-01-01"): 0.5})
        capital = 100_000

        result = smooth_positions(current, None, prices, capital=capital, exposure=exposure, dead_zone=0.01)

        # With exposure=0.5, effective capital = 50000
        expected_shares = int(np.floor(50_000 * 1.0 / 10.0 / 100)) * 100
        assert result["shares"].iloc[0] == expected_shares


# ── Normalization ────────────────────────────────────────────────────


class TestNormalization:
    """Verify weights are normalized to daily total exposure."""

    def test_weights_always_sum_to_one(self):
        """Weights always sum to 1.0 regardless of exposure.
        Exposure only affects shares via capital scaling."""
        current = _positions_df([
            _pos("2026-01-01", "A", 0.50, 5000),
            _pos("2026-01-01", "B", 0.50, 2500),
            _pos("2026-01-02", "A", 0.50, 5000),
            _pos("2026-01-02", "B", 0.50, 2500),
        ])
        prices = _prices_df([
            _price("2026-01-01", "A", 10.0),
            _price("2026-01-01", "B", 20.0),
            _price("2026-01-02", "A", 10.0),
            _price("2026-01-02", "B", 20.0),
        ])
        exposure = pd.Series({
            pd.Timestamp("2026-01-01"): 1.0,
            pd.Timestamp("2026-01-02"): 0.5,
        })
        result = smooth_positions(current, None, prices, capital=100_000, exposure=exposure, dead_zone=0.01)

        day1_sum = result[result["date"] == pd.Timestamp("2026-01-01")]["weight"].sum()
        day2_sum = result[result["date"] == pd.Timestamp("2026-01-02")]["weight"].sum()

        # Weights always sum to 1.0 (relative allocation)
        assert day1_sum == pytest.approx(1.0, abs=1e-10)
        assert day2_sum == pytest.approx(1.0, abs=1e-10)

        # But shares should differ: day 2 has exposure=0.5 → half the shares
        day1_shares = result[result["date"] == pd.Timestamp("2026-01-01")]["shares"].sum()
        day2_shares = result[result["date"] == pd.Timestamp("2026-01-02")]["shares"].sum()
        assert day2_shares < day1_shares
