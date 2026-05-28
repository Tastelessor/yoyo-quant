"""Tests for factor industry neutralization."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.factors.neutralize import demean_by_industry, neutralize_factors

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_factor_df(rows: list[tuple]) -> pd.DataFrame:
    """Helper: build factor DataFrame from (date, code, factor_val) tuples."""
    return pd.DataFrame(rows, columns=["date", "code", "f1"])


@pytest.fixture
def basic_data():
    """3 stocks in 2 industries, 1 date."""
    # Industry A: stocks 001 (f1=10), 002 (f1=20) → mean=15
    # Industry B: stock 003 (f1=30) → single stock, min_peers=1 → demean to 0
    factor_df = _make_factor_df(
        [
            ("2024-01-01", "001", 10.0),
            ("2024-01-01", "002", 20.0),
            ("2024-01-01", "003", 30.0),
        ]
    )
    factor_df["date"] = pd.to_datetime(factor_df["date"])
    industry_map = {"001": "A", "002": "A", "003": "B"}
    return factor_df, industry_map


# ---------------------------------------------------------------------------
# Core demean tests
# ---------------------------------------------------------------------------


class TestDemeanBasic:
    def test_demean_basic(self, basic_data):
        """3 stocks in 2 industries: A has 2 stocks, B has 1 (min_peers=1)."""
        factor_df, industry_map = basic_data
        result = demean_by_industry(factor_df, industry_map, ["f1"], min_peers=1)

        # Industry A: 10-15=-5, 20-15=5
        # Industry B: 30-30=0 (single stock)
        assert result.loc[0, "f1"] == pytest.approx(-5.0)
        assert result.loc[1, "f1"] == pytest.approx(5.0)
        assert result.loc[2, "f1"] == pytest.approx(0.0)

    def test_demean_single_industry(self):
        """All stocks in one industry → each value minus group mean."""
        factor_df = _make_factor_df(
            [
                ("2024-01-01", "001", 10.0),
                ("2024-01-01", "002", 20.0),
                ("2024-01-01", "003", 30.0),
            ]
        )
        factor_df["date"] = pd.to_datetime(factor_df["date"])
        industry_map = {"001": "X", "002": "X", "003": "X"}

        # mean = 20, demeaned: -10, 0, +10
        result = demean_by_industry(factor_df, industry_map, ["f1"])
        assert result["f1"].values == pytest.approx([-10.0, 0.0, 10.0])

    def test_demean_two_industries_different_means(self):
        """Two industries with different means: spread removed, order preserved."""
        factor_df = _make_factor_df(
            [
                ("2024-01-01", "001", 10.0),
                ("2024-01-01", "002", 20.0),
                ("2024-01-01", "003", 30.0),
                ("2024-01-01", "004", 100.0),
                ("2024-01-01", "005", 200.0),
                ("2024-01-01", "006", 300.0),
            ]
        )
        factor_df["date"] = pd.to_datetime(factor_df["date"])
        industry_map = {
            "001": "A",
            "002": "A",
            "003": "A",
            "004": "B",
            "005": "B",
            "006": "B",
        }

        result = demean_by_industry(factor_df, industry_map, ["f1"])

        # Industry A mean=20: -10, 0, +10
        # Industry B mean=200: -100, 0, +100
        assert result["f1"].values == pytest.approx(
            [-10.0, 0.0, 10.0, -100.0, 0.0, 100.0]
        )

    def test_demean_preserves_order_within_industry(self):
        """Within an industry, highest raw factor remains highest after demean."""
        factor_df = _make_factor_df(
            [
                ("2024-01-01", "001", 5.0),
                ("2024-01-01", "002", 15.0),
                ("2024-01-01", "003", 25.0),
                ("2024-01-01", "004", 100.0),
                ("2024-01-01", "005", 200.0),
                ("2024-01-01", "006", 300.0),
            ]
        )
        factor_df["date"] = pd.to_datetime(factor_df["date"])
        industry_map = {
            "001": "A",
            "002": "A",
            "003": "A",
            "004": "B",
            "005": "B",
            "006": "B",
        }

        result = demean_by_industry(factor_df, industry_map, ["f1"])
        # Within A: 003 > 002 > 001 (10 > 0 > -10)
        assert result.loc[2, "f1"] > result.loc[1, "f1"] > result.loc[0, "f1"]
        # Within B: 006 > 005 > 004 (100 > 0 > -100)
        assert result.loc[5, "f1"] > result.loc[4, "f1"] > result.loc[3, "f1"]


# ---------------------------------------------------------------------------
# Date isolation
# ---------------------------------------------------------------------------


class TestDateIsolation:
    def test_demean_per_date_isolation(self):
        """Factor values on date A should not affect date B."""
        factor_df = _make_factor_df(
            [
                ("2024-01-01", "001", 10.0),
                ("2024-01-01", "002", 20.0),
                ("2024-01-02", "001", 100.0),
                ("2024-01-02", "002", 200.0),
            ]
        )
        factor_df["date"] = pd.to_datetime(factor_df["date"])
        industry_map = {"001": "A", "002": "A"}

        result = demean_by_industry(factor_df, industry_map, ["f1"])

        # Date 1: mean=15, demeaned: -5, +5
        # Date 2: mean=150, demeaned: -50, +50
        assert result.loc[0, "f1"] == pytest.approx(-5.0)
        assert result.loc[1, "f1"] == pytest.approx(5.0)
        assert result.loc[2, "f1"] == pytest.approx(-50.0)
        assert result.loc[3, "f1"] == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_demean_unknown_industry(self):
        """Stocks not in industry_map go to __unknown__ group."""
        factor_df = _make_factor_df(
            [
                ("2024-01-01", "001", 10.0),
                ("2024-01-01", "002", 20.0),
                ("2024-01-01", "999", 30.0),  # not in map
            ]
        )
        factor_df["date"] = pd.to_datetime(factor_df["date"])
        industry_map = {"001": "A", "002": "A"}

        result = demean_by_industry(factor_df, industry_map, ["f1"], min_peers=1)
        # 999 goes to __unknown__ (single stock), demeaned to 0
        assert result.loc[2, "f1"] == pytest.approx(0.0)

    def test_demean_nan_handling(self):
        """NaN remains NaN; non-NaN values in same group are correctly demeaned."""
        factor_df = _make_factor_df(
            [
                ("2024-01-01", "001", 10.0),
                ("2024-01-01", "002", np.nan),
                ("2024-01-01", "003", 30.0),
            ]
        )
        factor_df["date"] = pd.to_datetime(factor_df["date"])
        industry_map = {"001": "A", "002": "A", "003": "A"}

        result = demean_by_industry(factor_df, industry_map, ["f1"])
        # mean of non-NaN = (10+30)/2 = 20
        assert result.loc[0, "f1"] == pytest.approx(-10.0)
        assert np.isnan(result.loc[1, "f1"])
        assert result.loc[2, "f1"] == pytest.approx(10.0)

    def test_min_peers_degrades_small_industry(self):
        """Single-stock industry with min_peers=3 → degraded to unknown group."""
        factor_df = _make_factor_df(
            [
                ("2024-01-01", "001", 10.0),
                ("2024-01-01", "002", 20.0),
                ("2024-01-01", "003", 30.0),
                ("2024-01-01", "004", 40.0),
            ]
        )
        factor_df["date"] = pd.to_datetime(factor_df["date"])
        # Industry A: 2 stocks, Industry B: 1 stock
        industry_map = {"001": "A", "002": "A", "003": "B", "004": "B"}

        # min_peers=3: B has only 1 stock (003) + 004 is also B but only 2 total
        # Actually B has 2 stocks (003, 004), still < 3, so both degrade to unknown
        result = demean_by_industry(factor_df, industry_map, ["f1"], min_peers=3)
        # A has 2 stocks < 3, also degrades
        # All 4 stocks end up in __unknown__, mean = 25
        assert result["f1"].values == pytest.approx([-15.0, -5.0, 5.0, 15.0])

    def test_min_peers_disabled(self):
        """min_peers=1: single-stock industry gets demeaned to 0."""
        factor_df = _make_factor_df(
            [
                ("2024-01-01", "001", 10.0),
                ("2024-01-01", "002", 20.0),
                ("2024-01-01", "003", 30.0),
            ]
        )
        factor_df["date"] = pd.to_datetime(factor_df["date"])
        industry_map = {"001": "A", "002": "A", "003": "B"}

        result = demean_by_industry(factor_df, industry_map, ["f1"], min_peers=1)
        # A: mean=15, demeaned: -5, +5
        # B: single stock, demeaned to 0
        assert result["f1"].values == pytest.approx([-5.0, 5.0, 0.0])

    def test_demean_empty_df(self):
        """Empty input → empty output."""
        factor_df = pd.DataFrame(
            {
                "date": pd.Series(dtype="datetime64[ns]"),
                "code": pd.Series(dtype=str),
                "f1": pd.Series(dtype=float),
            }
        )
        result = demean_by_industry(factor_df, {}, ["f1"])
        assert len(result) == 0
        assert list(result.columns) == ["date", "code", "f1"]

    def test_demean_preserves_non_factor_columns(self):
        """Non-factor columns (date, code) are unchanged."""
        factor_df = pd.DataFrame(
            {
                "date": pd.to_datetime(["2024-01-01", "2024-01-01"]),
                "code": ["001", "002"],
                "f1": [10.0, 20.0],
                "extra": [100, 200],
            }
        )
        industry_map = {"001": "A", "002": "A"}
        result = demean_by_industry(factor_df, industry_map, ["f1"])

        assert list(result.columns) == ["date", "code", "f1", "extra"]
        assert result["extra"].tolist() == [100, 200]
        assert result["code"].tolist() == ["001", "002"]

    def test_demean_does_not_mutate_input(self):
        """Input DataFrame is not modified."""
        factor_df = _make_factor_df(
            [
                ("2024-01-01", "001", 10.0),
                ("2024-01-01", "002", 20.0),
            ]
        )
        factor_df["date"] = pd.to_datetime(factor_df["date"])
        original_values = factor_df["f1"].copy()

        demean_by_industry(factor_df, {"001": "A", "002": "A"}, ["f1"])

        pd.testing.assert_series_equal(factor_df["f1"], original_values)

    def test_min_peers_less_than_1_raises(self):
        """min_peers < 1 should raise ValueError."""
        factor_df = _make_factor_df(
            [("2024-01-01", "001", 10.0), ("2024-01-01", "002", 20.0)]
        )
        factor_df["date"] = pd.to_datetime(factor_df["date"])
        with pytest.raises(ValueError, match="min_peers must be >= 1"):
            demean_by_industry(factor_df, {"001": "A"}, ["f1"], min_peers=0)
        with pytest.raises(ValueError, match="min_peers must be >= 1"):
            demean_by_industry(factor_df, {"001": "A"}, ["f1"], min_peers=-1)


# ---------------------------------------------------------------------------
# Dispatcher tests
# ---------------------------------------------------------------------------


class TestNeutralizeFactors:
    def test_neutralize_dispatches_demean(self):
        """neutralize_factors(method='demean') calls demean_by_industry."""
        factor_df = _make_factor_df(
            [
                ("2024-01-01", "001", 10.0),
                ("2024-01-01", "002", 20.0),
                ("2024-01-01", "003", 30.0),
            ]
        )
        factor_df["date"] = pd.to_datetime(factor_df["date"])
        industry_map = {"001": "A", "002": "A", "003": "A"}

        # mean=20, demeaned: -10, 0, +10
        result = neutralize_factors(factor_df, industry_map, ["f1"], method="demean")
        assert result["f1"].values == pytest.approx([-10.0, 0.0, 10.0])

    def test_neutralize_unknown_method_raises(self):
        """Unknown method raises ValueError."""
        factor_df = _make_factor_df(
            [
                ("2024-01-01", "001", 10.0),
            ]
        )
        factor_df["date"] = pd.to_datetime(factor_df["date"])

        with pytest.raises(ValueError, match="Unknown neutralization method"):
            neutralize_factors(factor_df, {}, ["f1"], method="xxx")

    def test_neutralize_forwards_kwargs(self):
        """neutralize_factors forwards **kwargs (e.g. min_peers)."""
        factor_df = _make_factor_df(
            [
                ("2024-01-01", "001", 10.0),
                ("2024-01-01", "002", 20.0),
                ("2024-01-01", "003", 30.0),
            ]
        )
        factor_df["date"] = pd.to_datetime(factor_df["date"])
        industry_map = {"001": "A", "002": "A", "003": "B"}

        # min_peers=1: B has 1 stock → demeaned to 0
        result = neutralize_factors(
            factor_df, industry_map, ["f1"], method="demean", min_peers=1
        )
        assert result.loc[2, "f1"] == pytest.approx(0.0)

        # min_peers=3: B degrades to unknown, all 3 in one group, mean=20
        result2 = neutralize_factors(
            factor_df, industry_map, ["f1"], method="demean", min_peers=3
        )
        assert result2["f1"].values == pytest.approx([-10.0, 0.0, 10.0])


# ---------------------------------------------------------------------------
# Statistical validation
# ---------------------------------------------------------------------------


class TestStatisticalProperties:
    def test_demean_r_squared_drop(self):
        """R² of factor~industry should drop from >0 to ≤1e-12 after demeaning."""
        np.random.seed(42)
        n_stocks = 100
        industries = ["A"] * 30 + ["B"] * 30 + ["C"] * 40
        codes = [f"{i:03d}" for i in range(n_stocks)]
        dates = pd.to_datetime(["2024-01-01"] * n_stocks)

        # Create factor values with industry bias
        base = np.random.randn(n_stocks)
        industry_effect = {"A": 5.0, "B": -3.0, "C": 1.0}
        f1 = base + [industry_effect[ind] for ind in industries]

        factor_df = pd.DataFrame({"date": dates, "code": codes, "f1": f1})
        industry_map = dict(zip(codes, industries))

        def _r_squared(y, groups):
            """Manual R²: 1 - SS_res / SS_tot using group means as predictor."""
            y = np.asarray(y, dtype=float)
            grand_mean = y.mean()
            ss_tot = np.sum((y - grand_mean) ** 2)
            group_labels = np.unique(groups)
            y_pred = np.empty_like(y)
            for g in group_labels:
                mask = groups == g
                y_pred[mask] = y[mask].mean()
            ss_res = np.sum((y - y_pred) ** 2)
            return 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

        ind_arr = np.array(industries)
        r2_before = _r_squared(f1, ind_arr)
        assert r2_before > 0.05, f"R² before should be > 0, got {r2_before}"

        # Neutralize
        result = demean_by_industry(factor_df, industry_map, ["f1"])

        r2_after = _r_squared(result["f1"].values, ind_arr)
        assert r2_after <= 1e-12, (
            f"R² after neutralization should be ~0, got {r2_after}"
        )

    def test_demean_large_cross_section(self):
        """100 stocks, 10 industries, 60 days: each group mean ≈ 0."""
        np.random.seed(123)
        n_stocks = 100
        n_days = 60
        n_industries = 10

        codes = [f"{i:03d}" for i in range(n_stocks)]
        industry_names = [f"Ind_{i % n_industries}" for i in range(n_stocks)]
        industry_map = dict(zip(codes, industry_names))

        rows = []
        for d in pd.date_range("2024-01-01", periods=n_days):
            for code in codes:
                rows.append((d, code, np.random.randn()))
        factor_df = pd.DataFrame(rows, columns=["date", "code", "f1"])

        result = demean_by_industry(factor_df, industry_map, ["f1"])

        # Each (date, industry) group should have mean ≈ 0
        result["_ind"] = result["code"].map(lambda c: industry_map[c])
        group_means = result.groupby(["date", "_ind"])["f1"].mean()
        assert group_means.abs().max() < 1e-10, (
            f"Max group mean should be ~0, got {group_means.abs().max()}"
        )

    def test_demean_with_real_like_data(self):
        """30 stocks, 60 days: verify shape, no NaN introduction, output types."""
        np.random.seed(456)
        n_stocks = 30
        n_days = 60

        codes = [f"{i:06d}" for i in range(n_stocks)]
        industries = [f"Ind_{i % 5}" for i in range(n_stocks)]
        industry_map = dict(zip(codes, industries))

        rows = []
        for d in pd.date_range("2024-01-01", periods=n_days):
            for code in codes:
                rows.append((d, code, np.random.randn() * 10))
        factor_df = pd.DataFrame(rows, columns=["date", "code", "f1"])

        result = demean_by_industry(factor_df, industry_map, ["f1"])

        assert result.shape == factor_df.shape
        assert result["date"].dtype == "datetime64[ns]"
        assert result["f1"].dtype == np.float64
        # No NaN introduced (original had no NaN)
        assert result["f1"].isna().sum() == 0
