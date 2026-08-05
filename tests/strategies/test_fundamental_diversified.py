"""Tests for fundamental_diversified strategy."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.strategies.builtin.fundamental_diversified import (
    DEFAULT_WEIGHTS,
    FundamentalDiversifiedStrategy,
    fundamental_diversified_signal,
)
from src.strategies.registry import get_strategy

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def diversified_data() -> pd.DataFrame:
    """30 stocks, 60 days. Deterministic factor ordering:
    - close is constant → amihud is 0 for all stocks (no ranking noise)
    - earnings_surprise spreads [-1, 1] across stocks → dominates ranking
    - roe_stability is co-monotonic with earnings_surprise → never flips order
    """
    codes = [f"{i:06d}" for i in range(1, 31)]
    frames = []
    for i, code in enumerate(codes):
        es = (i - 15) / 15.0  # range [-1, 1], strictly increasing in i
        frames.append(
            pd.DataFrame(
                {
                    "date": pd.date_range("2024-01-01", periods=60, freq="B"),
                    "code": code,
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.0,
                    "volume": 1_000_000,
                    "total_mv": 1e10,
                    "earnings_surprise": es,
                    "roe_stability": es * 0.5,
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


@pytest.fixture
def single_stock() -> pd.DataFrame:
    """Single stock — not enough for cross-sectional ranking."""
    return pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=60, freq="B"),
            "code": "000001",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1_000_000,
            "total_mv": 1e10,
            "earnings_surprise": 0.5,
            "roe_stability": 0.2,
        }
    )


def _factor_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Pre-computed factors DataFrame matching the default weights."""
    return pd.DataFrame(
        {
            "date": df["date"],
            "code": df["code"],
            "earnings_surprise": df["earnings_surprise"],
            "amihud": np.zeros(len(df)),
            "roe_stability": df["roe_stability"],
        }
    )


# ---------------------------------------------------------------------------
# Tests: Strategy class
# ---------------------------------------------------------------------------


class TestFundamentalDiversifiedStrategy:
    def test_name(self):
        s = FundamentalDiversifiedStrategy()
        assert s.name == "fundamental_diversified"

    def test_registered_in_registry(self):
        s = get_strategy("fundamental_diversified")
        assert isinstance(s, FundamentalDiversifiedStrategy)

    def test_default_weights(self):
        assert set(DEFAULT_WEIGHTS) == {"earnings_surprise", "amihud", "roe_stability"}

    def test_returns_dataframe(self, diversified_data):
        s = FundamentalDiversifiedStrategy(rebalance=15, top_n=3, bottom_n=3)
        result = s.generate_signal(diversified_data)
        assert isinstance(result, pd.DataFrame)

    def test_has_required_columns(self, diversified_data):
        s = FundamentalDiversifiedStrategy(rebalance=15, top_n=3, bottom_n=3)
        result = s.generate_signal(diversified_data)
        assert set(result.columns) == {"date", "code", "signal", "confidence"}

    def test_signal_values_valid(self, diversified_data):
        s = FundamentalDiversifiedStrategy(rebalance=15, top_n=3, bottom_n=3)
        result = s.generate_signal(diversified_data)
        assert set(result["signal"].unique()).issubset({-1, 0, 1})

    def test_signal_dtype_is_int(self, diversified_data):
        s = FundamentalDiversifiedStrategy(rebalance=15, top_n=3, bottom_n=3)
        result = s.generate_signal(diversified_data)
        assert pd.api.types.is_integer_dtype(result["signal"])

    def test_confidence_range(self, diversified_data):
        s = FundamentalDiversifiedStrategy(rebalance=15, top_n=3, bottom_n=3)
        result = s.generate_signal(diversified_data)
        assert (result["confidence"] >= 0).all()
        assert (result["confidence"] <= 1).all()

    def test_uses_factors_if_provided(self, diversified_data):
        """Pre-computed factors should be preferred over inline computation."""
        s = FundamentalDiversifiedStrategy(rebalance=15, top_n=3, bottom_n=3)
        factors = _factor_frame(diversified_data)
        result = s.generate_signal(diversified_data, factors=factors)
        assert isinstance(result, pd.DataFrame)
        assert len(result) == len(diversified_data)

    def test_no_duplicate_rows(self, diversified_data):
        s = FundamentalDiversifiedStrategy(rebalance=15, top_n=3, bottom_n=3)
        result = s.generate_signal(diversified_data)
        assert len(result) == len(diversified_data)
        assert result.duplicated(["date", "code"]).sum() == 0

    def test_date_ascending_within_code(self, diversified_data):
        """Output is grouped by code; dates must be ascending within each code."""
        s = FundamentalDiversifiedStrategy(rebalance=15, top_n=3, bottom_n=3)
        result = s.generate_signal(diversified_data)
        per_code = result.groupby("code")["date"].apply(
            lambda s: s.is_monotonic_increasing
        )
        assert per_code.all()


# ---------------------------------------------------------------------------
# Tests: Signal function
# ---------------------------------------------------------------------------


class TestFundamentalDiversifiedSignal:
    def test_length_matches_input(self, diversified_data):
        result = fundamental_diversified_signal(
            diversified_data,
            rebalance=15,
            top_n=3,
            bottom_n=3,
        )
        assert len(result) == len(diversified_data)

    def test_buy_top_scored_stocks(self, diversified_data):
        """Highest earnings_surprise stocks should receive buy signals."""
        result = fundamental_diversified_signal(
            diversified_data,
            rebalance=15,
            top_n=5,
            bottom_n=0,
        )
        buy_signals = result[result["signal"] == 1]
        assert len(buy_signals) > 0
        # Top-5 by earnings_surprise (codes 26..30 of the 30)
        top_codes = {f"{i:06d}" for i in range(26, 31)}
        assert set(buy_signals["code"]).issubset(top_codes)

    def test_sell_bottom_scored_stocks(self, diversified_data):
        result = fundamental_diversified_signal(
            diversified_data,
            rebalance=15,
            top_n=0,
            bottom_n=5,
        )
        sell_signals = result[result["signal"] == -1]
        assert len(sell_signals) > 0
        bottom_codes = {f"{i:06d}" for i in range(1, 6)}
        assert set(sell_signals["code"]).issubset(bottom_codes)

    def test_no_signal_before_warmup(self, diversified_data):
        """Signals must be zero before the min_window warmup period."""
        result = fundamental_diversified_signal(
            diversified_data,
            rebalance=15,
            top_n=5,
            bottom_n=5,
        )
        dates = sorted(diversified_data["date"].unique())
        first_valid = dates[21]  # min_window = 21
        early = result["date"] < first_valid
        assert (result.loc[early, "signal"] == 0).all()
        # And the first rebalance date itself starts emitting signals
        on_first = result["date"] == first_valid
        assert (result.loc[on_first, "signal"] != 0).any()

    def test_no_signal_single_stock(self, single_stock):
        result = fundamental_diversified_signal(
            single_stock,
            rebalance=15,
            top_n=5,
            bottom_n=5,
        )
        assert (result["signal"] == 0).all()

    def test_no_signal_short_history(self):
        """Fewer than min_window=21 days → no rebalance dates → all zero."""
        df = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=10, freq="B"),
                "code": "000001",
                "close": 100.0,
                "volume": 1_000_000,
                "total_mv": 1e10,
                "earnings_surprise": 0.5,
                "roe_stability": 0.2,
            }
        )
        result = fundamental_diversified_signal(df, rebalance=15, top_n=5, bottom_n=5)
        assert (result["signal"] == 0).all()

    def test_empty_dataframe(self):
        df = pd.DataFrame(
            columns=["date", "code", "close", "volume", "earnings_surprise"]
        )
        result = fundamental_diversified_signal(df, rebalance=15, top_n=5, bottom_n=5)
        assert isinstance(result, pd.DataFrame)
        assert set(result.columns) == {"date", "code", "signal", "confidence"}
        assert len(result) == 0

    def test_custom_weights(self, diversified_data):
        weights = {"earnings_surprise": 1.0, "roe_stability": 1.0}
        result = fundamental_diversified_signal(
            diversified_data,
            rebalance=15,
            top_n=3,
            bottom_n=3,
            weights=weights,
        )
        assert isinstance(result, pd.DataFrame)
        assert set(result["signal"].unique()).issubset({-1, 0, 1})

    def test_missing_factor_columns_falls_back_to_zero(self):
        """No factor columns in data and no factors arg → empty signal."""
        df = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=60, freq="B"),
                "code": "000001",
                "close": 100.0,
            }
        )
        result = fundamental_diversified_signal(df, rebalance=15, top_n=5, bottom_n=5)
        assert (result["signal"] == 0).all()

    def test_industry_neutralization(self, diversified_data):
        """industry_map path should run without error and keep contract."""
        codes = [f"{i:06d}" for i in range(1, 31)]
        industry_map = {code: f"ind{(i % 3)}" for i, code in enumerate(codes)}
        result = fundamental_diversified_signal(
            diversified_data,
            rebalance=15,
            top_n=5,
            bottom_n=5,
            industry_map=industry_map,
            min_peers=3,
        )
        assert set(result.columns) == {"date", "code", "signal", "confidence"}
        assert len(result) == len(diversified_data)
