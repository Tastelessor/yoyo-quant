"""Tests for src/factors/earnings.py — earnings factor functions."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.factors.earnings import calc_earnings_acceleration, calc_earnings_surprise


class TestCalcEarningsSurprise:
    def test_returns_series(self):
        df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=5),
            "code": ["A"] * 5,
            "earnings_surprise": [0.1, 0.2, 0.3, 0.4, 0.5],
        })
        result = calc_earnings_surprise(df)
        assert isinstance(result, pd.Series)

    def test_length_matches_input(self):
        n = 10
        df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=n),
            "code": ["A"] * n,
            "earnings_surprise": np.arange(n, dtype=float),
        })
        result = calc_earnings_surprise(df)
        assert len(result) == n

    def test_preserves_values(self):
        vals = [0.5, -0.3, 0.0, 1.2, -1.5]
        df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=5),
            "code": ["A"] * 5,
            "earnings_surprise": vals,
        })
        result = calc_earnings_surprise(df)
        np.testing.assert_array_almost_equal(result.values, vals)

    def test_no_data_column_raises(self):
        df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=3),
            "code": ["A"] * 3,
        })
        with pytest.raises(KeyError):
            calc_earnings_surprise(df)


class TestCalcEarningsAcceleration:
    def test_returns_series(self):
        df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=5),
            "code": ["A"] * 5,
            "earnings_acceleration": [0.0, 0.1, -0.2, 0.3, 0.0],
        })
        result = calc_earnings_acceleration(df)
        assert isinstance(result, pd.Series)

    def test_length_matches_input(self):
        n = 8
        df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=n),
            "code": ["A"] * n,
            "earnings_acceleration": np.zeros(n),
        })
        result = calc_earnings_acceleration(df)
        assert len(result) == n

    def test_preserves_values(self):
        vals = [0.3, -0.5, 0.0, 0.8, -0.1]
        df = pd.DataFrame({
            "date": pd.date_range("2025-01-01", periods=5),
            "code": ["A"] * 5,
            "earnings_acceleration": vals,
        })
        result = calc_earnings_acceleration(df)
        np.testing.assert_array_almost_equal(result.values, vals)
