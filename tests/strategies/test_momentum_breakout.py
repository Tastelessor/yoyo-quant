"""Momentum breakout strategy tests."""

import numpy as np
import pandas as pd
import pytest

from src.strategies.builtin.momentum_breakout import MomentumBreakoutStrategy


@pytest.fixture
def volume_spike_up():
    """Normal volume then sudden spike with rising close."""
    dates = pd.date_range("2024-01-02", periods=25, freq="B")
    close = np.concatenate([np.full(20, 100.0), np.array([101, 102, 103, 104, 105], dtype=float)])
    volume = np.concatenate([np.full(20, 1_000_000), [3_000_000, 3_500_000, 4_000_000, 3_000_000, 2_500_000]])
    return pd.DataFrame(
        {
            "date": dates,
            "code": "000001",
            "open": close - 0.5,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": volume,
        }
    )


@pytest.fixture
def volume_spike_down():
    """Normal volume then sudden spike with falling close."""
    dates = pd.date_range("2024-01-02", periods=25, freq="B")
    close = np.concatenate([np.full(20, 100.0), np.array([99, 98, 97, 96, 95], dtype=float)])
    volume = np.concatenate([np.full(20, 1_000_000), [3_000_000, 3_500_000, 4_000_000, 3_000_000, 2_500_000]])
    return pd.DataFrame(
        {
            "date": dates,
            "code": "000001",
            "open": close + 0.5,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": volume,
        }
    )


@pytest.fixture
def no_volume_spike():
    """Constant volume, no breakout."""
    dates = pd.date_range("2024-01-02", periods=25, freq="B")
    return pd.DataFrame(
        {
            "date": dates,
            "code": "000001",
            "open": 100.0,
            "high": 100.5,
            "low": 99.5,
            "close": 100.0,
            "volume": [1_000_000] * 25,
        }
    )


class TestMomentumBreakoutStrategy:
    def test_name(self):
        s = MomentumBreakoutStrategy()
        assert s.name == "momentum_breakout"

    def test_returns_dataframe(self, volume_spike_up):
        s = MomentumBreakoutStrategy(vol_window=20, vol_threshold=1.5)
        result = s.generate_signal(volume_spike_up)
        assert isinstance(result, pd.DataFrame)
        assert len(result) == len(volume_spike_up)

    def test_has_required_columns(self, volume_spike_up):
        s = MomentumBreakoutStrategy(vol_window=20, vol_threshold=1.5)
        result = s.generate_signal(volume_spike_up)
        assert set(result.columns) == {"date", "code", "signal", "confidence"}

    def test_signal_values_valid(self, volume_spike_up):
        s = MomentumBreakoutStrategy(vol_window=20, vol_threshold=1.5)
        result = s.generate_signal(volume_spike_up)
        assert set(result["signal"].unique()).issubset({-1, 0, 1})

    def test_buy_on_volume_spike_up(self, volume_spike_up):
        """Volume spike + rising OBV → buy."""
        s = MomentumBreakoutStrategy(vol_window=20, vol_threshold=1.5)
        result = s.generate_signal(volume_spike_up)
        buy_signals = result[result["signal"] == 1]
        assert len(buy_signals) > 0

    def test_sell_on_volume_spike_down(self, volume_spike_down):
        """Volume spike + falling OBV → sell."""
        s = MomentumBreakoutStrategy(vol_window=20, vol_threshold=1.5)
        result = s.generate_signal(volume_spike_down)
        sell_signals = result[result["signal"] == -1]
        assert len(sell_signals) > 0

    def test_no_signal_no_spike(self, no_volume_spike):
        """No volume spike → no signals."""
        s = MomentumBreakoutStrategy(vol_window=20, vol_threshold=1.5)
        result = s.generate_signal(no_volume_spike)
        assert (result["signal"] == 0).all()

    def test_confidence_range(self, volume_spike_up):
        s = MomentumBreakoutStrategy(vol_window=20, vol_threshold=1.5)
        result = s.generate_signal(volume_spike_up)
        valid = result["confidence"].dropna()
        assert (valid >= 0).all()
        assert (valid <= 1).all()

    def test_custom_threshold(self, volume_spike_up):
        """Higher threshold → fewer signals."""
        low_thresh = MomentumBreakoutStrategy(vol_window=20, vol_threshold=1.5)
        high_thresh = MomentumBreakoutStrategy(vol_window=20, vol_threshold=3.0)
        r1 = low_thresh.generate_signal(volume_spike_up)
        r2 = high_thresh.generate_signal(volume_spike_up)
        # Higher threshold should produce fewer buy signals
        assert (r1["signal"] == 1).sum() >= (r2["signal"] == 1).sum()
