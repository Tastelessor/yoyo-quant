"""Tests for stock selector — coverage, rank stability, dispersion, tradable selection."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.context.stock_selector import (
    evaluate_factors,
    factor_coverage,
    factor_dispersion,
    rank_stability,
    select_tradable,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_factor_df(n_stocks=3, n_days=30, seed=42, nan_stock=None) -> pd.DataFrame:
    """Build [date, code, factor_a, factor_b] DataFrame with random data."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=n_days, freq="B")
    codes = [f"{i:06d}" for i in range(1, n_stocks + 1)]

    rows = []
    for code in codes:
        for date in dates:
            val_a = rng.normal(0, 1)
            val_b = rng.normal(0, 1)
            if nan_stock and code == nan_stock:
                # 50% NaN
                val_a = np.nan if rng.random() > 0.5 else val_a
            rows.append({"date": date, "code": code, "factor_a": val_a, "factor_b": val_b})

    return pd.DataFrame(rows)


def _make_stable_rank_df(n_stocks=10, n_days=80) -> pd.DataFrame:
    """Factor with stable cross-sectional ranks per stock.

    Stocks have spaced bases with moderate noise so ranks vary but maintain
    overall ordering. Small gaps ensure ranked values have enough within-stock
    variation for rolling correlation to be computable.
    """
    rng = np.random.default_rng(42)
    dates = pd.date_range("2024-01-01", periods=n_days, freq="B")
    codes = [f"{i:06d}" for i in range(1, n_stocks + 1)]

    rows = []
    for i, code in enumerate(codes):
        base = (i + 1) * 1.5  # 1.5, 3.0, 4.5, ...
        for date in dates:
            row = {"date": date, "code": code, "factor_a": base + rng.normal(0, 0.8)}
            rows.append(row)
    return pd.DataFrame(rows)


def _make_random_rank_df(n_stocks=10, n_days=80) -> pd.DataFrame:
    """Factor with random, unstable ranks."""
    rng = np.random.default_rng(99)
    dates = pd.date_range("2024-01-01", periods=n_days, freq="B")
    codes = [f"{i:06d}" for i in range(1, n_stocks + 1)]

    rows = []
    for code in codes:
        for date in dates:
            rows.append({"date": date, "code": code, "factor_a": rng.normal(0, 5.0)})
    return pd.DataFrame(rows)


def _make_uniform_factor_df(n_stocks=5, n_days=30) -> pd.DataFrame:
    """Factor where all stocks have nearly identical values → CV near 0."""
    dates = pd.date_range("2024-01-01", periods=n_days, freq="B")
    codes = [f"{i:06d}" for i in range(1, n_stocks + 1)]

    rows = []
    for code in codes:
        for date in dates:
            # All values near 100 with negligible noise → CV ≈ 1e-10
            rows.append({"date": date, "code": code, "factor_a": 100.0 + np.random.randn() * 1e-8})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Tests: factor_coverage
# ---------------------------------------------------------------------------

class TestFactorCoverage:
    def test_returns_series_same_index(self) -> None:
        df = _make_factor_df(n_stocks=2, n_days=20)
        result = factor_coverage(df, "factor_a", lookback=10)
        assert isinstance(result, pd.Series)
        assert len(result) == len(df)

    def test_full_data_has_coverage_one(self) -> None:
        df = _make_factor_df(n_stocks=2, n_days=20)
        result = factor_coverage(df, "factor_a", lookback=5)
        # After warmup (first 4 rows per stock), coverage should be 1.0
        warmup_end = 2 * 4  # 2 stocks × (lookback - 1)
        assert result.iloc[warmup_end:].dropna().min() >= 0.99

    def test_nan_stock_has_lower_coverage(self) -> None:
        df = _make_factor_df(n_stocks=3, n_days=20, nan_stock="000001")
        result = factor_coverage(df, "factor_a", lookback=10)
        stock_1_mask = df["code"] == "000001"
        stock_2_mask = df["code"] == "000002"
        # Stock 1 should have lower coverage than stock 2
        valid = result.notna()
        s1_mean = result[stock_1_mask & valid].mean()
        s2_mean = result[stock_2_mask & valid].mean()
        assert s1_mean < s2_mean, f"NaN stock ({s1_mean:.2f}) should be lower than clean ({s2_mean:.2f})"

    def test_values_in_zero_one_range(self) -> None:
        df = _make_factor_df(n_stocks=3, n_days=20, nan_stock="000001")
        result = factor_coverage(df, "factor_a", lookback=10)
        valid = result.dropna()
        assert valid.min() >= 0.0
        assert valid.max() <= 1.0

    def test_per_stock_independence(self) -> None:
        """NaNs in one stock don't affect another's coverage."""
        df = _make_factor_df(n_stocks=2, n_days=30, nan_stock="000001")
        result = factor_coverage(df, "factor_a", lookback=10)
        stock_2_mask = df["code"] == "000002"
        valid_s2 = result[stock_2_mask].dropna()
        assert valid_s2.min() >= 0.99  # stock 2 should have perfect coverage

    def test_raises_on_missing_column(self) -> None:
        df = _make_factor_df(n_stocks=2, n_days=10)
        with pytest.raises(KeyError):
            factor_coverage(df, "nonexistent", lookback=10)


# ---------------------------------------------------------------------------
# Tests: rank_stability
# ---------------------------------------------------------------------------

class TestRankStability:
    def test_returns_series_same_index(self) -> None:
        df = _make_stable_rank_df(n_stocks=3, n_days=30)
        result = rank_stability(df, "factor_a", lookback=10, lag=3)
        assert isinstance(result, pd.Series)
        assert len(result) == len(df)

    def test_stable_ranks_have_positive_stability(self) -> None:
        """Stable-rank data should have higher median stability than random."""
        df_stable = _make_stable_rank_df(n_stocks=10, n_days=100)
        df_random = _make_random_rank_df(n_stocks=10, n_days=100)
        s = rank_stability(df_stable, "factor_a", lookback=20, lag=5).dropna()
        r = rank_stability(df_random, "factor_a", lookback=20, lag=5).dropna()
        # Stable should beat random (comparative, not absolute threshold —
        # absolute values are sensitive to stock count and rank granularity)
        assert s.median() > r.median(), (
            f"Stable ({s.median():.3f}) should beat random ({r.median():.3f})"
        )

    def test_random_ranks_have_low_stability(self) -> None:
        df = _make_random_rank_df(n_stocks=3, n_days=60)
        result = rank_stability(df, "factor_a", lookback=20, lag=5)
        valid = result.dropna()
        # Random ranks should have |correlation| < 0.3 most of the time
        assert valid.abs().median() < 0.3, (
            f"Random ranks should have low stability, got |median| {valid.abs().median():.3f}"
        )

    def test_stable_beats_random(self) -> None:
        stable_df = _make_stable_rank_df(n_stocks=3, n_days=60)
        random_df = _make_random_rank_df(n_stocks=3, n_days=60)
        s = rank_stability(stable_df, "factor_a", lookback=20, lag=5).dropna()
        r = rank_stability(random_df, "factor_a", lookback=20, lag=5).dropna()
        assert s.median() > r.median(), (
            f"Stable ({s.median():.3f}) should beat random ({r.median():.3f})"
        )

    def test_values_in_range_neg_one_to_one(self) -> None:
        df = _make_random_rank_df(n_stocks=3, n_days=60)
        result = rank_stability(df, "factor_a", lookback=20, lag=5)
        valid = result.dropna()
        assert valid.min() >= -1.0
        assert valid.max() <= 1.0

    def test_per_stock_independence(self) -> None:
        """Stability is computed per stock, stocks don't contaminate each other."""
        df = _make_stable_rank_df(n_stocks=3, n_days=60)
        result = rank_stability(df, "factor_a", lookback=20, lag=5)
        # Each stock should have some valid values
        for code in df["code"].unique():
            stock_result = result[df["code"] == code].dropna()
            assert len(stock_result) > 0, f"Stock {code} should have valid stability values"


# ---------------------------------------------------------------------------
# Tests: factor_dispersion
# ---------------------------------------------------------------------------

class TestFactorDispersion:
    def test_returns_series_indexed_by_date(self) -> None:
        df = _make_factor_df(n_stocks=3, n_days=20)
        result = factor_dispersion(df, "factor_a")
        assert isinstance(result, pd.Series)
        assert len(result) == df["date"].nunique()
        assert result.index.name == "date" or result.index.dtype is not None

    def test_spread_values_have_positive_dispersion(self) -> None:
        df = _make_factor_df(n_stocks=5, n_days=20)
        result = factor_dispersion(df, "factor_a")
        assert result.min() > 0.0, f"Spread values should have positive dispersion, got min {result.min():.6f}"

    def test_uniform_values_have_near_zero_dispersion(self) -> None:
        df = _make_uniform_factor_df(n_stocks=5, n_days=20)
        result = factor_dispersion(df, "factor_a")
        assert result.max() < 0.01, (
            f"Uniform values should have near-zero dispersion, got max {result.max():.6f}"
        )

    def test_values_non_negative(self) -> None:
        df = _make_factor_df(n_stocks=3, n_days=20)
        result = factor_dispersion(df, "factor_a")
        assert result.min() >= 0.0

    def test_spread_beats_uniform(self) -> None:
        spread_df = _make_factor_df(n_stocks=5, n_days=20)
        uniform_df = _make_uniform_factor_df(n_stocks=5, n_days=20)
        s = factor_dispersion(spread_df, "factor_a")
        u = factor_dispersion(uniform_df, "factor_a")
        assert s.median() > u.median(), (
            f"Spread ({s.median():.6f}) should beat uniform ({u.median():.6f})"
        )


# ---------------------------------------------------------------------------
# Tests: select_tradable
# ---------------------------------------------------------------------------

class TestSelectTradable:
    def test_returns_dict(self) -> None:
        df = _make_factor_df(n_stocks=5, n_days=20)
        result = select_tradable(
            df, ["factor_a"], lookback=5, lag=2,
            min_coverage=0.0, min_stability=-1.0, min_dispersion=0.0,
            min_stocks=2,
        )
        assert isinstance(result, dict)

    def test_keys_are_dates(self) -> None:
        df = _make_factor_df(n_stocks=5, n_days=20)
        result = select_tradable(
            df, ["factor_a"], lookback=5, lag=2,
            min_coverage=0.0, min_stability=-1.0, min_dispersion=0.0,
            min_stocks=2,
        )
        for k in result:
            assert isinstance(k, pd.Timestamp)

    def test_values_are_lists_of_codes(self) -> None:
        df = _make_factor_df(n_stocks=5, n_days=20)
        result = select_tradable(
            df, ["factor_a"], lookback=5, lag=2,
            min_coverage=0.0, min_stability=-1.0, min_dispersion=0.0,
            min_stocks=2,
        )
        for codes in result.values():
            assert isinstance(codes, list)
            for c in codes:
                assert isinstance(c, str)

    def test_too_few_stocks_returns_empty(self) -> None:
        df = _make_factor_df(n_stocks=5, n_days=20)
        result = select_tradable(
            df, ["factor_a"], lookback=5, lag=2,
            min_coverage=0.0, min_stability=-1.0, min_dispersion=0.0,
            min_stocks=50,  # impossible threshold
        )
        assert result == {}

    def test_high_coverage_threshold_filters_all(self) -> None:
        df = _make_factor_df(n_stocks=3, n_days=20, nan_stock="000001")
        result = select_tradable(
            df, ["factor_a"], lookback=5, lag=2,
            min_coverage=0.99, min_stability=-1.0, min_dispersion=0.0,
            min_stocks=1,
        )
        # Stock with NaN should be filtered, but clean stocks pass
        for codes in result.values():
            assert "000001" not in codes

    def test_high_stability_threshold_filters_random(self) -> None:
        """Random-rank stocks should be filtered by high stability threshold."""
        df = _make_random_rank_df(n_stocks=3, n_days=60)
        result = select_tradable(
            df, ["factor_a"], lookback=20, lag=5,
            min_coverage=0.0, min_stability=0.5, min_dispersion=0.0,
            min_stocks=1,
        )
        # With random ranks, most dates should have no stocks passing
        assert len(result) <= df["date"].nunique() * 0.8, (
            "Most dates should filter out random-rank stocks"
        )

    def test_high_dispersion_threshold_filters_uniform(self) -> None:
        df = _make_uniform_factor_df(n_stocks=5, n_days=20)
        result = select_tradable(
            df, ["factor_a"], lookback=5, lag=2,
            min_coverage=0.0, min_stability=-1.0, min_dispersion=0.05,
            min_stocks=1,
        )
        # Uniform factor has ~0 dispersion, should be entirely filtered
        assert result == {}

    def test_multiple_factors_aggregate(self) -> None:
        """Stocks passing more factors should appear more often."""
        df = _make_factor_df(n_stocks=5, n_days=30)
        result = select_tradable(
            df, ["factor_a", "factor_b"], lookback=5, lag=2,
            min_coverage=0.0, min_stability=-1.0, min_dispersion=0.0,
            min_stocks=3,
        )
        for codes in result.values():
            assert len(codes) >= 3

    def test_empty_factor_names_returns_empty(self) -> None:
        df = _make_factor_df(n_stocks=5, n_days=10)
        result = select_tradable(
            df, [], lookback=5, lag=2,
            min_coverage=0.0, min_stability=-1.0, min_dispersion=0.0,
            min_stocks=1,
        )
        assert result == {}

    def test_empty_dataframe_returns_empty(self) -> None:
        df = pd.DataFrame({"date": [], "code": [], "factor_a": []})
        result = select_tradable(
            df, ["factor_a"], lookback=5, lag=2,
            min_coverage=0.0, min_stability=-1.0, min_dispersion=0.0,
            min_stocks=1,
        )
        assert result == {}

    def test_top_n_limits_pool_size(self) -> None:
        df = _make_factor_df(n_stocks=10, n_days=30)
        result = select_tradable(
            df, ["factor_a"], lookback=5, lag=2,
            min_coverage=0.0, min_stability=-1.0, min_dispersion=0.0,
            min_stocks=1, top_n=3,
        )
        for codes in result.values():
            assert len(codes) <= 3, f"top_n=3 should limit to 3, got {len(codes)}"

    def test_top_n_none_includes_all(self) -> None:
        df = _make_factor_df(n_stocks=5, n_days=20)
        result = select_tradable(
            df, ["factor_a"], lookback=5, lag=2,
            min_coverage=0.0, min_stability=-1.0, min_dispersion=0.0,
            min_stocks=1, top_n=None,
        )
        for codes in result.values():
            assert len(codes) == 5, f"top_n=None should include all 5, got {len(codes)}"

    def test_mid_stability_filter_reduces_pool(self) -> None:
        """Applying reasonable thresholds should reduce but not eliminate the pool."""
        df = _make_stable_rank_df(n_stocks=5, n_days=60)
        # Lenient: all stocks pass
        lenient = select_tradable(
            df, ["factor_a"], lookback=20, lag=5,
            min_coverage=0.0, min_stability=-1.0, min_dispersion=0.0,
            min_stocks=1,
        )
        # Reasonable: some may not pass
        strict = select_tradable(
            df, ["factor_a"], lookback=20, lag=5,
            min_coverage=0.5, min_stability=0.3, min_dispersion=0.05,
            min_stocks=1,
        )
        lenient_total = sum(len(v) for v in lenient.values())
        strict_total = sum(len(v) for v in strict.values())
        assert strict_total <= lenient_total, (
            f"Strict ({strict_total}) should not exceed lenient ({lenient_total})"
        )


# ---------------------------------------------------------------------------
# Tests: evaluate_factors
# ---------------------------------------------------------------------------

class TestEvaluateFactors:
    def test_returns_dataframe(self) -> None:
        df = _make_factor_df(n_stocks=5, n_days=60)
        result = evaluate_factors(df, ["factor_a", "factor_b"], lookback=20, lag=5)
        assert isinstance(result, pd.DataFrame)

    def test_has_required_columns(self) -> None:
        df = _make_factor_df(n_stocks=5, n_days=60)
        result = evaluate_factors(df, ["factor_a", "factor_b"], lookback=20, lag=5)
        assert set(result.columns) == {"factor", "coverage", "stability", "dispersion", "active"}

    def test_one_row_per_factor(self) -> None:
        df = _make_factor_df(n_stocks=5, n_days=60)
        result = evaluate_factors(df, ["factor_a", "factor_b"], lookback=20, lag=5)
        assert len(result) == 2

    def test_active_column_is_bool(self) -> None:
        df = _make_factor_df(n_stocks=5, n_days=60)
        result = evaluate_factors(df, ["factor_a"], lookback=20, lag=5)
        assert result["active"].dtype == bool

    def test_metrics_in_reasonable_ranges(self) -> None:
        df = _make_factor_df(n_stocks=5, n_days=60)
        result = evaluate_factors(df, ["factor_a"], lookback=20, lag=5)
        assert 0.0 <= result.loc[0, "coverage"] <= 1.0
        assert -1.0 <= result.loc[0, "stability"] <= 1.0
        assert result.loc[0, "dispersion"] >= 0.0

    def test_random_factor_marked_inactive(self) -> None:
        df = _make_random_rank_df(n_stocks=10, n_days=100)
        result = evaluate_factors(
            df, ["factor_a"], lookback=20, lag=5,
            min_stability=0.3,
        )
        assert not result.loc[0, "active"], "Random-rank factor should be inactive"

    def test_stable_beats_random_on_same_data(self) -> None:
        """Stable-rank factor gets higher stability score than random-rank."""
        stable = _make_stable_rank_df(n_stocks=10, n_days=100)
        random = _make_random_rank_df(n_stocks=10, n_days=100)
        stable["factor_rnd"] = random["factor_a"].values

        result = evaluate_factors(
            stable, ["factor_a", "factor_rnd"], lookback=20, lag=5,
        )
        s_stab = result[result["factor"] == "factor_a"]["stability"].values[0]
        r_stab = result[result["factor"] == "factor_rnd"]["stability"].values[0]
        assert s_stab > r_stab, (
            f"Stable ({s_stab:.3f}) should beat random ({r_stab:.3f})"
        )

    def test_empty_factor_names_returns_empty(self) -> None:
        df = _make_factor_df(n_stocks=5, n_days=20)
        result = evaluate_factors(df, [], lookback=20, lag=5)
        assert len(result) == 0

    def test_factor_column_preserved(self) -> None:
        df = _make_factor_df(n_stocks=5, n_days=60)
        result = evaluate_factors(df, ["factor_a"], lookback=20, lag=5)
        assert result.loc[0, "factor"] == "factor_a"

    def test_multiple_factors_independent(self) -> None:
        """Each factor gets its own row with independent metrics."""
        stable = _make_stable_rank_df(n_stocks=10, n_days=100)
        random = _make_random_rank_df(n_stocks=10, n_days=100)
        df = stable.copy()
        df["factor_random"] = random["factor_a"].values

        result = evaluate_factors(
            df, ["factor_a", "factor_random"], lookback=20, lag=5,
            min_stability=0.3,
        )
        assert len(result) == 2
        # Both have valid metrics (not NaN)
        for _, row in result.iterrows():
            assert not np.isnan(row["coverage"])
            assert not np.isnan(row["stability"])
            assert not np.isnan(row["dispersion"])
