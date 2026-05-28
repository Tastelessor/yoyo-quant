"""Tests for drawdown circuit breaker."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.portfolio.circuit_breaker import DrawdownCircuitBreaker


def _equity(values, start="2023-01-01"):
    """Create equity Series from list of values."""
    dates = pd.bdate_range(start, periods=len(values), freq="B")
    return pd.Series(values, index=dates, dtype=float)


class TestDrawdownCircuitBreakerBasic:
    """Basic behavior tests."""

    def test_full_exposure_when_no_drawdown(self):
        """No drawdown -> full exposure."""
        cb = DrawdownCircuitBreaker(threshold=-0.15)
        equity = _equity([100, 101, 102, 103])
        exposure = cb.compute_exposure(equity)
        assert (exposure == 1.0).all()

    def test_compresses_exposure_on_drawdown(self):
        """Drawdown beyond threshold -> reduced exposure."""
        cb = DrawdownCircuitBreaker(threshold=-0.15)
        # Peak at 100, drops to 80 -> 20% drawdown
        equity = _equity([100, 95, 90, 85, 80])
        exposure = cb.compute_exposure(equity)
        # Last value: drawdown = -20%, should be compressed
        assert exposure.iloc[-1] < 1.0

    def test_exposure_decreases_with_deeper_drawdown(self):
        """Deeper drawdown -> lower exposure (both in ramp zone)."""
        # threshold=-0.20, recovery=-0.03 -> ramp zone is [-20%, -3%]
        # -12% and -25% are both in or past the ramp zone
        cb1 = DrawdownCircuitBreaker(threshold=-0.25, recovery_threshold=-0.03)
        cb2 = DrawdownCircuitBreaker(threshold=-0.25, recovery_threshold=-0.03)
        eq_shallow = _equity([100, 95, 90, 88])  # -12% drawdown, in ramp
        eq_deep = _equity([100, 95, 85, 75])     # -25% drawdown, below threshold

        exp_shallow = cb1.compute_exposure(eq_shallow)
        exp_deep = cb2.compute_exposure(eq_deep)

        assert exp_shallow.iloc[-1] > exp_deep.iloc[-1]

    def test_zero_exposure_at_max_drawdown(self):
        """Very deep drawdown -> minimum exposure."""
        cb = DrawdownCircuitBreaker(threshold=-0.10)
        # 50% drawdown
        equity = _equity([100, 80, 60, 50])
        exposure = cb.compute_exposure(equity)
        # Should be at or near minimum
        assert exposure.iloc[-1] <= 0.2


class TestDrawdownCircuitBreakerHysteresis:
    """Hysteresis (recovery lag) tests."""

    def test_does_not_recover_immediately(self):
        """After triggering, exposure stays low even if drawdown improves slightly."""
        cb = DrawdownCircuitBreaker(threshold=-0.10, recovery_threshold=-0.03)
        # Trigger at -15%, then recover to -8% (still above recovery threshold)
        equity = _equity([100, 90, 85, 92])  # -15% then -8%
        exposure = cb.compute_exposure(equity)
        # -8% is above recovery_threshold (-3%), so should still be compressed
        assert exposure.iloc[-1] < 1.0

    def test_recovers_when_shallow_drawdown(self):
        """Exposure recovers when drawdown returns above recovery threshold."""
        cb = DrawdownCircuitBreaker(threshold=-0.10, recovery_threshold=-0.03)
        # Trigger at -15%, then recover to -2% (below recovery threshold)
        equity = _equity([100, 85, 90, 95, 98])
        exposure = cb.compute_exposure(equity)
        # Last value: drawdown = -2%, should be recovering
        assert exposure.iloc[-1] > exposure.iloc[1]


class TestDrawdownCircuitBreakerGradual:
    """Gradual (continuous) exposure mapping tests."""

    def test_exposure_is_continuous(self):
        """Exposure should vary continuously with drawdown, not jump."""
        cb = DrawdownCircuitBreaker(threshold=-0.10)
        # Gradual decline
        values = [100]
        for i in range(20):
            values.append(values[-1] * 0.99)
        equity = _equity(values)
        exposure = cb.compute_exposure(equity)

        # Check no jumps > 0.3 between consecutive days
        diffs = exposure.diff().abs().dropna()
        assert (diffs < 0.35).all(), f"Exposure jumps too large: {diffs.max()}"

    def test_exposure_in_valid_range(self):
        """Exposure always in [min_exposure, 1.0]."""
        cb = DrawdownCircuitBreaker(threshold=-0.10)
        equity = _equity([100, 90, 80, 70, 60, 70, 80, 90, 95])
        exposure = cb.compute_exposure(equity)
        assert (exposure >= 0.0).all()
        assert (exposure <= 1.0).all()


class TestDrawdownCircuitBreakerEdgeCases:
    """Edge case tests."""

    def test_empty_equity(self):
        cb = DrawdownCircuitBreaker()
        equity = pd.Series(dtype=float)
        exposure = cb.compute_exposure(equity)
        assert exposure.empty

    def test_single_value(self):
        cb = DrawdownCircuitBreaker()
        equity = _equity([100])
        exposure = cb.compute_exposure(equity)
        assert len(exposure) == 1
        assert exposure.iloc[0] == 1.0

    def test_monotonically_increasing(self):
        """No drawdown in uptrend -> always full exposure."""
        cb = DrawdownCircuitBreaker(threshold=-0.10)
        equity = _equity([100, 102, 105, 110, 115, 120])
        exposure = cb.compute_exposure(equity)
        assert (exposure == 1.0).all()

    def test_custom_thresholds(self):
        """Custom threshold and recovery_threshold are respected."""
        cb = DrawdownCircuitBreaker(threshold=-0.20, recovery_threshold=-0.05)
        # -3% drawdown: above recovery_threshold (-5%), so full exposure
        equity = _equity([100, 97])
        exposure = cb.compute_exposure(equity)
        assert exposure.iloc[-1] == 1.0

        # -15% drawdown: in ramp zone between -20% and -5%
        cb2 = DrawdownCircuitBreaker(threshold=-0.20, recovery_threshold=-0.05)
        equity2 = _equity([100, 90, 85])
        exposure2 = cb2.compute_exposure(equity2)
        assert 0.1 < exposure2.iloc[-1] < 1.0

    def test_custom_min_exposure(self):
        """min_exposure parameter controls floor."""
        cb = DrawdownCircuitBreaker(threshold=-0.10, min_exposure=0.3)
        equity = _equity([100, 70, 50])  # 50% drawdown
        exposure = cb.compute_exposure(equity)
        assert exposure.iloc[-1] >= 0.3

    def test_drawdown_stays_compressed_across_periods(self):
        """If equity stays below peak, drawdown persists."""
        cb = DrawdownCircuitBreaker(threshold=-0.10)
        # First batch: peak at 100, drop to 85
        eq1 = _equity([100, 95, 90, 85])
        exp1 = cb.compute_exposure(eq1)
        assert exp1.iloc[-1] < 1.0

        # Second batch: stays at 85 (still -15% from peak)
        eq2 = _equity([85, 85, 85], start="2023-01-08")
        exp2 = cb.compute_exposure(eq2)
        # Should still be compressed because peak=100, current=85
        assert exp2.iloc[-1] < 1.0

    def test_recovers_after_new_peak(self):
        """New peak resets drawdown to 0."""
        cb = DrawdownCircuitBreaker(threshold=-0.10)
        # First: drop to 85
        eq1 = _equity([100, 90, 85])
        cb.compute_exposure(eq1)

        # Second: new peak at 110
        eq2 = _equity([90, 100, 110], start="2023-01-06")
        exp2 = cb.compute_exposure(eq2)
        assert exp2.iloc[-1] == 1.0


class TestDrawdownCircuitBreakerExposureFn:
    """Test the exposure_fn factory method."""

    def test_exposure_fn_returns_series(self):
        cb = DrawdownCircuitBreaker(threshold=-0.10)
        fn = cb.exposure_fn()
        dates = pd.bdate_range("2023-01-01", periods=5)
        result = fn(dates)
        assert isinstance(result, pd.Series)
        assert len(result) == 5

    def test_exposure_fn_full_by_default(self):
        """Without any equity update, exposure_fn returns 1.0."""
        cb = DrawdownCircuitBreaker(threshold=-0.10)
        fn = cb.exposure_fn()
        dates = pd.bdate_range("2023-01-01", periods=5)
        result = fn(dates)
        assert (result == 1.0).all()

    def test_exposure_fn_reflects_equity_state(self):
        """After update_equity, exposure_fn reflects drawdown."""
        cb = DrawdownCircuitBreaker(threshold=-0.10)
        fn = cb.exposure_fn()

        # First period: drawdown
        eq = _equity([100, 90, 80])
        cb.update_equity(eq)

        # Ask for exposure on future dates
        future_dates = pd.bdate_range("2023-01-06", periods=3)
        result = fn(future_dates)
        # Should be compressed because drawdown persists
        assert (result < 1.0).all()
