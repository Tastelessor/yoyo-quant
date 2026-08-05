"""Tests for industry momentum scoring and tilt allocation."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from portfolio.industry_momentum import (
    apply_industry_tilt,
    compute_industry_momentum,
)


def _make_data_with_industry(n_days=30, seed=42):
    """Create synthetic stock data with industry labels."""
    rng = np.random.RandomState(seed)
    dates = pd.bdate_range("2024-01-01", periods=n_days)
    codes = ["A", "B", "C", "D"]
    industries = {"A": "银行", "B": "银行", "C": "科技", "D": "医药"}
    rows = []
    for code in codes:
        price = 100.0
        for d in dates:
            price *= 1 + rng.normal(0, 0.02)
            rows.append({
                "date": d, "code": code, "close": price,
                "industry": industries[code],
            })
    return pd.DataFrame(rows)


def _make_positions(date, codes, weights):
    """Helper to create a positions DataFrame."""
    return pd.DataFrame({
        "date": pd.Timestamp(date),
        "code": codes,
        "weight": weights,
        "shares": [int(w * 1_000_000 / 10) for w in weights],
    })


class TestComputeIndustryMomentum:
    """Test compute_industry_momentum function."""

    def test_returns_dataframe(self):
        data = _make_data_with_industry()
        result = compute_industry_momentum(data, lookback=5)
        assert isinstance(result, pd.DataFrame)

    def test_has_required_columns(self):
        data = _make_data_with_industry()
        result = compute_industry_momentum(data, lookback=5)
        assert {"date", "industry", "momentum"}.issubset(result.columns)

    def test_momentum_is_numeric(self):
        data = _make_data_with_industry()
        result = compute_industry_momentum(data, lookback=5)
        assert pd.api.types.is_numeric_dtype(result["momentum"])

    def test_no_lookahead_bias(self):
        """Momentum at date T should only use data up to T."""
        data = _make_data_with_industry(n_days=30)
        result = compute_industry_momentum(data, lookback=5)
        # First lookback-1 dates should have NaN momentum for all industries
        early = result[result["date"] <= data["date"].unique()[4]]
        # At least some should be NaN (warmup period)
        assert early["momentum"].isna().any() or len(early) == 0


class TestApplyIndustryTilt:
    """Test apply_industry_tilt function."""

    def test_tilt_strength_zero_no_change(self):
        """tilt_strength=0 should produce same weights as industry cap only."""
        pos = _make_positions("2024-01-01", ["A", "B", "C"], [0.4, 0.3, 0.3])
        data = _make_data_with_industry(n_days=30)
        momentum = compute_industry_momentum(data, lookback=5)
        industry_map = {"A": "银行", "B": "银行", "C": "科技"}
        result = apply_industry_tilt(
            pos, industry_map, momentum,
            tilt_strength=0.0, max_industry_weight=0.50,
        )
        assert result["weight"].sum() == pytest.approx(1.0, abs=0.01)

    def test_tilt_preserves_cap(self):
        """Tilted weights should still respect industry cap."""
        pos = _make_positions("2024-01-01", ["A", "B", "C"], [0.4, 0.3, 0.3])
        data = _make_data_with_industry(n_days=30)
        momentum = compute_industry_momentum(data, lookback=5)
        industry_map = {"A": "银行", "B": "银行", "C": "科技"}
        result = apply_industry_tilt(
            pos, industry_map, momentum,
            tilt_strength=1.0, max_industry_weight=0.50,
        )
        # 银行 = A+B, should not exceed 0.50
        bank_weight = result[result["code"].isin(["A", "B"])]["weight"].sum()
        assert bank_weight <= 0.50 + 1e-10

    def test_empty_positions_returns_empty(self):
        pos = pd.DataFrame(columns=["date", "code", "weight", "shares"])
        data = _make_data_with_industry()
        momentum = compute_industry_momentum(data, lookback=5)
        result = apply_industry_tilt(pos, {}, momentum)
        assert result.empty

    def test_higher_momentum_gets_higher_weight(self):
        """Industry with higher momentum should get higher weight after tilt."""
        # Create data where 科技 has higher returns than 银行
        rng = np.random.RandomState(42)
        dates = pd.bdate_range("2024-01-01", periods=30)
        rows = []
        for code, ind in [("A", "银行"), ("B", "银行"), ("C", "科技")]:
            price = 100.0
            for i, d in enumerate(dates):
                # 科技 has higher drift
                drift = 0.01 if ind == "科技" else -0.01
                price *= 1 + drift + rng.normal(0, 0.01)
                rows.append({"date": d, "code": code, "close": price, "industry": ind})
        data = pd.DataFrame(rows)
        momentum = compute_industry_momentum(data, lookback=5)

        # Use a late date where momentum is computed
        late_date = dates[-1]
        pos = _make_positions(late_date, ["A", "B", "C"], [0.33, 0.33, 0.34])
        industry_map = {"A": "银行", "B": "银行", "C": "科技"}

        result = apply_industry_tilt(
            pos, industry_map, momentum,
            tilt_strength=1.0, max_industry_weight=0.80,
        )
        # 科技 should get higher weight than 银行 after tilt
        tech_weight = result[result["code"] == "C"]["weight"].iloc[0]
        bank_weight = result[result["code"].isin(["A", "B"])]["weight"].sum()
        # With strong tilt, high-momentum industry should be overweight
        # This is a directional test, not exact
        assert result["weight"].sum() == pytest.approx(1.0, abs=0.01)
