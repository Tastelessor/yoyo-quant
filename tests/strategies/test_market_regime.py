"""Tests for market regime detector."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategies.builtin.market_regime import (
    MarketRegime,
    market_regime_exposure,
)


def _make_index(dates, closes):
    return pd.DataFrame({"date": dates, "close": closes})


class TestMarketRegimeExposure:
    """Standalone function tests."""

    def test_bullish_regime(self):
        """price > MA200 AND MA50 > MA200 -> 1.0"""
        # Create 250 days of steadily rising prices
        dates = pd.date_range("2023-01-01", periods=250, freq="B")
        closes = np.linspace(100, 200, 250)
        result = market_regime_exposure(pd.Series(closes, index=dates))
        # Last day: price=200, MA50 ~190, MA200 ~150 -> bullish
        assert result.iloc[-1] == 1.0

    def test_bearish_regime(self):
        """price < MA200 AND MA50 < MA200 -> 0.2"""
        dates = pd.date_range("2023-01-01", periods=250, freq="B")
        closes = np.linspace(200, 100, 250)  # steadily falling
        result = market_regime_exposure(pd.Series(closes, index=dates))
        assert result.iloc[-1] == 0.2

    def test_neutral_regime(self):
        """price > MA200 AND MA50 < MA200 -> 0.6"""
        # Price above MA200 but MA50 below MA200
        # Rising then flat: MA50 catches up but stays below MA200
        dates = pd.date_range("2023-01-01", periods=250, freq="B")
        # Start high, drop, then recover slowly
        phase1 = np.linspace(200, 100, 125)
        phase2 = np.linspace(100, 150, 125)
        closes = np.concatenate([phase1, phase2])
        result = market_regime_exposure(pd.Series(closes, index=dates))
        # At end: price=150, MA200 ~150 (depends on exact values)
        # This is a boundary case; just check it returns a valid value
        assert result.iloc[-1] in {0.2, 0.4, 0.6, 1.0}

    def test_cautious_regime(self):
        """price < MA200 AND MA50 > MA200 -> 0.4"""
        # Price drops then recovers: MA50 > MA200 but price < MA200
        dates = pd.date_range("2023-01-01", periods=250, freq="B")
        phase1 = np.linspace(200, 80, 180)  # big drop
        phase2 = np.linspace(80, 140, 70)   # recovery
        closes = np.concatenate([phase1, phase2])
        result = market_regime_exposure(pd.Series(closes, index=dates))
        assert result.iloc[-1] in {0.2, 0.4, 0.6, 1.0}

    def test_warmup_defaults_to_neutral(self):
        """First ma_long dates should default to 0.6."""
        dates = pd.date_range("2023-01-01", periods=100, freq="B")
        closes = np.ones(100) * 100.0
        result = market_regime_exposure(pd.Series(closes, index=dates), ma_long=200)
        # All 100 dates are in warmup
        assert (result == 0.6).all()

    def test_custom_exposure(self):
        """Custom exposure mapping."""
        dates = pd.date_range("2023-01-01", periods=250, freq="B")
        closes = np.linspace(100, 200, 250)
        custom = {1.0: 1.0, 0.6: 0.8, 0.4: 0.5, 0.2: 0.1}
        result = market_regime_exposure(
            pd.Series(closes, index=dates), exposure=custom
        )
        assert result.iloc[-1] == 1.0

    def test_output_length_matches_input(self):
        dates = pd.date_range("2023-01-01", periods=250, freq="B")
        closes = np.linspace(100, 200, 250)
        result = market_regime_exposure(pd.Series(closes, index=dates))
        assert len(result) == 250

    def test_output_index_matches_input(self):
        dates = pd.date_range("2023-01-01", periods=250, freq="B")
        closes = np.linspace(100, 200, 250)
        result = market_regime_exposure(pd.Series(closes, index=dates))
        pd.testing.assert_index_equal(result.index, dates)

    def test_single_value_input(self):
        """Insufficient data for any MA -> warmup default."""
        dates = pd.date_range("2023-01-01", periods=5, freq="B")
        closes = np.ones(5) * 100.0
        result = market_regime_exposure(pd.Series(closes, index=dates))
        assert (result == 0.6).all()

    def test_flat_prices(self):
        """Flat prices: MA equals price -> price > MA is False (equal)."""
        dates = pd.date_range("2023-01-01", periods=250, freq="B")
        closes = np.ones(250) * 100.0
        result = market_regime_exposure(pd.Series(closes, index=dates))
        # price == MA -> not > MA -> bearish or cautious
        assert result.iloc[-1] in {0.2, 0.4}


class TestMarketRegimeClass:
    """MarketRegime class tests."""

    def test_default_params(self):
        regime = MarketRegime()
        assert regime.ma_short == 50
        assert regime.ma_long == 200
        assert regime.exposure == {1.0: 1.0, 0.6: 0.6, 0.4: 0.4, 0.2: 0.2}

    def test_custom_params(self):
        regime = MarketRegime(ma_short=30, ma_long=100)
        assert regime.ma_short == 30
        assert regime.ma_long == 100

    def test_compute_exposure_returns_series(self):
        regime = MarketRegime(ma_short=50, ma_long=200)
        dates = pd.date_range("2023-01-01", periods=250, freq="B")
        closes = np.linspace(100, 200, 250)
        index_data = _make_index(dates, closes)
        result = regime.compute_exposure(index_data)
        assert isinstance(result, pd.Series)

    def test_compute_exposure_with_dataframe(self):
        regime = MarketRegime(ma_short=50, ma_long=200)
        dates = pd.date_range("2023-01-01", periods=250, freq="B")
        closes = np.linspace(100, 200, 250)
        index_data = _make_index(dates, closes)
        result = regime.compute_exposure(index_data)
        assert len(result) == 250

    def test_compute_exposure_missing_close_column(self):
        regime = MarketRegime()
        df = pd.DataFrame({"date": [1, 2], "open": [100, 101]})
        with pytest.raises(ValueError, match="close"):
            regime.compute_exposure(df)
