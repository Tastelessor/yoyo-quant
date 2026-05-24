"""Tests for pipeline diagnostics."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.analysis.pipeline_diagnostics import (
    forward_return_analysis,
    full_diagnosis,
    signal_stage_counts,
    signal_spread,
)


@pytest.fixture
def sample_data() -> pd.DataFrame:
    np.random.seed(42)
    n = 60
    codes = ["A", "B", "C"]
    frames = []
    for code in codes:
        close = 100 + np.cumsum(np.random.randn(n) * 0.5)
        frames.append(pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=n, freq="B"),
            "code": code,
            "open": close - 0.2,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": [1_000_000] * n,
        }))
    return pd.concat(frames, ignore_index=True)


@pytest.fixture
def sample_signals(sample_data: pd.DataFrame) -> pd.DataFrame:
    sig = pd.Series(0, index=sample_data.index, dtype=int)
    sig.iloc[::3] = 1
    sig.iloc[1::3] = -1
    return pd.DataFrame({
        "date": sample_data["date"],
        "code": sample_data["code"],
        "signal": sig,
        "confidence": 0.5,
    })


class TestSignalStageCounts:
    def test_returns_dataframe(self, sample_data, sample_signals) -> None:
        result = signal_stage_counts(sample_data, sample_signals, sample_signals, sample_signals)
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 3

    def test_counts_match(self, sample_data, sample_signals) -> None:
        result = signal_stage_counts(sample_data, sample_signals, sample_signals, sample_signals)
        assert result["buy"].sum() > 0
        assert result["sell"].sum() > 0


class TestForwardReturnAnalysis:
    def test_returns_dataframe(self, sample_data, sample_signals) -> None:
        result = forward_return_analysis(sample_data, sample_signals)
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 3  # buy, sell, hold

    def test_has_required_columns(self, sample_data, sample_signals) -> None:
        result = forward_return_analysis(sample_data, sample_signals)
        assert "signal_type" in result.columns
        assert "count" in result.columns
        assert "fwd_ret_5d_mean" in result.columns
        assert "hit_rate_5d" in result.columns


class TestSignalSpread:
    def test_good_signal(self) -> None:
        df = pd.DataFrame({
            "signal_type": ["buy", "sell", "hold"],
            "count": [100, 100, 100],
            "fwd_ret_5d_mean": [0.01, -0.01, 0.0],
            "hit_rate_5d": [0.55, 0.45, 0.50],
        })
        result = signal_spread(df, window=5)
        assert result["quality"] == "good"
        assert result["spread"] > 0

    def test_inverted_signal(self) -> None:
        df = pd.DataFrame({
            "signal_type": ["buy", "sell", "hold"],
            "count": [100, 100, 100],
            "fwd_ret_5d_mean": [-0.01, 0.01, 0.0],
            "hit_rate_5d": [0.45, 0.55, 0.50],
        })
        result = signal_spread(df, window=5)
        assert result["quality"] == "inverted"


class TestFullDiagnosis:
    def test_returns_all_keys(self, sample_data, sample_signals) -> None:
        result = full_diagnosis(
            sample_data, sample_signals, sample_signals, sample_signals,
        )
        assert "stage_counts" in result
        assert "forward_returns" in result
        assert "spread" in result
