"""RSI reversal strategy tests."""

import numpy as np
import pandas as pd
import pytest

from strategies.builtin.rsi_reversal import RSIReversalStrategy


@pytest.fixture
def trending_up():
    """Steady uptrend — RSI should go above overbought."""
    dates = pd.date_range("2024-01-02", periods=30, freq="B")
    close = 100.0 + np.arange(30) * 0.5  # steady rise
    return pd.DataFrame(
        {
            "date": dates,
            "code": "000001",
            "open": close - 0.2,
            "high": close + 0.3,
            "low": close - 0.3,
            "close": close,
            "volume": [1_000_000] * 30,
        }
    )


@pytest.fixture
def trending_down():
    """Steady downtrend — RSI should go below oversold."""
    dates = pd.date_range("2024-01-02", periods=30, freq="B")
    close = 100.0 - np.arange(30) * 0.5
    return pd.DataFrame(
        {
            "date": dates,
            "code": "000001",
            "open": close + 0.2,
            "high": close + 0.3,
            "low": close - 0.3,
            "close": close,
            "volume": [1_000_000] * 30,
        }
    )


@pytest.fixture
def flat_market():
    """Flat market — RSI ~50, no signals."""
    dates = pd.date_range("2024-01-02", periods=30, freq="B")
    return pd.DataFrame(
        {
            "date": dates,
            "code": "000001",
            "open": 100.0,
            "high": 100.5,
            "low": 99.5,
            "close": 100.0,
            "volume": [1_000_000] * 30,
        }
    )


class TestRSIReversalStrategy:
    def test_name(self):
        s = RSIReversalStrategy()
        assert s.name == "rsi_reversal"

    def test_returns_dataframe(self, trending_down):
        s = RSIReversalStrategy(window=14)
        result = s.generate_signal(trending_down)
        assert isinstance(result, pd.DataFrame)
        assert len(result) == len(trending_down)

    def test_has_required_columns(self, trending_down):
        s = RSIReversalStrategy(window=14)
        result = s.generate_signal(trending_down)
        assert set(result.columns) == {"date", "code", "signal", "confidence"}

    def test_signal_values_valid(self, trending_down):
        s = RSIReversalStrategy(window=14)
        result = s.generate_signal(trending_down)
        assert set(result["signal"].unique()).issubset({-1, 0, 1})

    def test_confidence_range(self, trending_down):
        s = RSIReversalStrategy(window=14)
        result = s.generate_signal(trending_down)
        valid = result["confidence"].dropna()
        assert (valid >= 0).all()
        assert (valid <= 1).all()

    def test_buy_on_oversold(self, trending_down):
        """Downtrend → RSI drops → should trigger buy when oversold."""
        s = RSIReversalStrategy(window=14, oversold=30, overbought=70)
        result = s.generate_signal(trending_down)
        buy_signals = result[result["signal"] == 1]
        assert len(buy_signals) > 0

    def test_sell_on_overbought(self, trending_up):
        """Uptrend → RSI rises → should trigger sell when overbought."""
        s = RSIReversalStrategy(window=14, oversold=30, overbought=70)
        result = s.generate_signal(trending_up)
        sell_signals = result[result["signal"] == -1]
        assert len(sell_signals) > 0

    def test_no_signal_flat(self, flat_market):
        """Flat market → RSI ~50 → no signals."""
        s = RSIReversalStrategy(window=14, oversold=30, overbought=70)
        result = s.generate_signal(flat_market)
        assert (result["signal"] == 0).all()

    def test_uses_factors_rsi_if_provided(self, trending_down):
        """If factors has 'rsi' column, use it instead of computing."""
        s = RSIReversalStrategy(window=14, oversold=30, overbought=70)
        # Provide pre-computed RSI that's always oversold
        factors = pd.DataFrame({"rsi": [20.0] * len(trending_down)})
        result = s.generate_signal(trending_down, factors=factors)
        # All should be buy signals
        assert (result["signal"] == 1).all()

    def test_custom_thresholds(self, trending_up):
        """Tighter thresholds → more signals."""
        tight = RSIReversalStrategy(window=14, oversold=40, overbought=60)
        result = tight.generate_signal(trending_up)
        # Should have some sell signals with lower overbought threshold
        assert (result["signal"] == -1).any()
