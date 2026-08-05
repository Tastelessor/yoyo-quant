"""Tests for src/factors/quality.py — quality factor passthrough functions."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from factors.quality import calc_cashflow_quality, calc_roe_level, calc_roe_stability


@pytest.fixture
def sample_df():
    return pd.DataFrame(
        {
            "date": pd.date_range("2025-01-01", periods=5),
            "code": ["A"] * 5,
            "roe_level": [10.0, 12.0, 8.0, 15.0, 11.0],
            "roe_stability": [-1.5, -0.8, -2.0, -0.5, -1.0],
            "cashflow_quality": [5.0, 3.0, 8.0, 2.0, 6.0],
        }
    )


class TestCalcRoeLevel:
    def test_returns_series(self, sample_df):
        result = calc_roe_level(sample_df)
        assert isinstance(result, pd.Series)

    def test_length_matches(self, sample_df):
        result = calc_roe_level(sample_df)
        assert len(result) == 5

    def test_preserves_values(self, sample_df):
        result = calc_roe_level(sample_df)
        np.testing.assert_array_almost_equal(
            result.values, [10.0, 12.0, 8.0, 15.0, 11.0]
        )

    def test_missing_column_raises(self):
        df = pd.DataFrame({"date": [1], "code": ["A"]})
        with pytest.raises(KeyError):
            calc_roe_level(df)


class TestCalcRoeStability:
    def test_returns_series(self, sample_df):
        result = calc_roe_stability(sample_df)
        assert isinstance(result, pd.Series)

    def test_preserves_values(self, sample_df):
        result = calc_roe_stability(sample_df)
        np.testing.assert_array_almost_equal(
            result.values, [-1.5, -0.8, -2.0, -0.5, -1.0]
        )

    def test_missing_column_raises(self):
        df = pd.DataFrame({"date": [1], "code": ["A"]})
        with pytest.raises(KeyError):
            calc_roe_stability(df)


class TestCalcCashflowQuality:
    def test_returns_series(self, sample_df):
        result = calc_cashflow_quality(sample_df)
        assert isinstance(result, pd.Series)

    def test_preserves_values(self, sample_df):
        result = calc_cashflow_quality(sample_df)
        np.testing.assert_array_almost_equal(
            result.values, [5.0, 3.0, 8.0, 2.0, 6.0]
        )

    def test_missing_column_raises(self):
        df = pd.DataFrame({"date": [1], "code": ["A"]})
        with pytest.raises(KeyError):
            calc_cashflow_quality(df)
