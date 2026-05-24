"""Tests for exposure-scaled equal_weight allocator."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.portfolio.allocator import equal_weight


def _make_signals(dates, codes, capital=1_000_000):
    """Create simple buy signals for testing."""
    rows = []
    for d in dates:
        for c in codes:
            rows.append({"date": d, "code": c, "signal": 1, "confidence": 0.8})
    return pd.DataFrame(rows)


def _make_prices(dates, codes, price=100.0):
    """Create price data for testing."""
    rows = []
    for d in dates:
        for c in codes:
            rows.append({"date": d, "code": c, "close": price})
    return pd.DataFrame(rows)


class TestEqualWeightBackwardCompat:
    """Ensure existing behavior without exposure param is unchanged."""

    def test_no_exposure_produces_same_result(self):
        dates = pd.date_range("2023-01-01", periods=5, freq="B")
        codes = ["000001", "000002"]
        signals = _make_signals(dates, codes)
        prices = _make_prices(dates, codes, price=100.0)

        result = equal_weight(signals, prices, capital=1_000_000)
        assert len(result) > 0
        assert set(result.columns) == {"date", "code", "weight", "shares"}
        # Each stock gets equal weight
        day1 = result[result["date"] == dates[0]]
        assert len(day1) == 2
        np.testing.assert_allclose(day1["weight"].values, 0.5, atol=1e-10)

    def test_empty_signals_no_exposure(self):
        signals = pd.DataFrame(columns=["date", "code", "signal", "confidence"])
        prices = pd.DataFrame(columns=["date", "code", "close"])
        result = equal_weight(signals, prices)
        assert result.empty


class TestExposureScaling:
    """Tests for exposure parameter in equal_weight."""

    def test_exposure_scales_shares(self):
        dates = pd.date_range("2023-01-01", periods=3, freq="B")
        codes = ["000001"]
        signals = _make_signals(dates, codes)
        prices = _make_prices(dates, codes, price=100.0)

        # Full exposure
        result_full = equal_weight(signals, prices, capital=1_000_000)
        # Half exposure
        exposure = pd.Series([0.5, 0.5, 0.5], index=dates)
        result_half = equal_weight(
            signals, prices, capital=1_000_000, exposure=exposure
        )

        # Half exposure should produce roughly half the shares
        full_shares = result_full["shares"].iloc[0]
        half_shares = result_half["shares"].iloc[0]
        assert half_shares <= full_shares
        assert half_shares > 0

    def test_zero_exposure_produces_zero_shares(self):
        dates = pd.date_range("2023-01-01", periods=3, freq="B")
        codes = ["000001"]
        signals = _make_signals(dates, codes)
        prices = _make_prices(dates, codes, price=100.0)

        exposure = pd.Series([0.0, 0.0, 0.0], index=dates)
        result = equal_weight(
            signals, prices, capital=1_000_000, exposure=exposure
        )
        # Zero exposure -> zero capital -> zero shares
        if not result.empty:
            assert (result["shares"] == 0).all()

    def test_exposure_per_date(self):
        """Different exposure on different dates."""
        dates = pd.date_range("2023-01-01", periods=3, freq="B")
        codes = ["000001"]
        signals = _make_signals(dates, codes)
        prices = _make_prices(dates, codes, price=100.0)

        exposure = pd.Series([1.0, 0.5, 0.2], index=dates)
        result = equal_weight(
            signals, prices, capital=1_000_000, exposure=exposure
        )

        # Day 1: full exposure -> 10000 shares
        day1 = result[result["date"] == dates[0]]
        assert day1["shares"].iloc[0] == 10000

        # Day 2: half exposure -> 5000 shares
        day2 = result[result["date"] == dates[1]]
        assert day2["shares"].iloc[0] == 5000

        # Day 3: 20% exposure -> 2000 shares
        day3 = result[result["date"] == dates[2]]
        assert day3["shares"].iloc[0] == 2000

    def test_missing_date_in_exposure_defaults_to_1(self):
        """If a date is not in exposure Series, default to full exposure."""
        dates = pd.date_range("2023-01-01", periods=3, freq="B")
        codes = ["000001"]
        signals = _make_signals(dates, codes)
        prices = _make_prices(dates, codes, price=100.0)

        # Only provide exposure for first 2 dates
        exposure = pd.Series([0.5, 0.5], index=dates[:2])
        result = equal_weight(
            signals, prices, capital=1_000_000, exposure=exposure
        )

        # Day 3 not in exposure -> defaults to 1.0 -> 10000 shares
        day3 = result[result["date"] == dates[2]]
        assert day3["shares"].iloc[0] == 10000

    def test_exposure_weight因地制配正确(self):
        """Weight should also reflect exposure scaling."""
        dates = pd.date_range("2023-01-01", periods=2, freq="B")
        codes = ["000001", "000002"]
        signals = _make_signals(dates, codes)
        prices = _make_prices(dates, codes, price=100.0)

        exposure = pd.Series([0.6, 0.6], index=dates)
        result = equal_weight(
            signals, prices, capital=1_000_000, exposure=exposure
        )

        # Each stock gets 0.5 weight (equal weight), but shares are scaled
        day1 = result[result["date"] == dates[0]]
        assert len(day1) == 2
        np.testing.assert_allclose(day1["weight"].values, 0.5, atol=1e-10)
        # 600000 * 0.5 / 100 = 3000 shares each
        assert (day1["shares"] == 3000).all()
