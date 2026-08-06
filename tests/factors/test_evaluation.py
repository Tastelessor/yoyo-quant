"""Tests for factor evaluation: IC / IR / forward returns / quantile returns."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from factors.ops.evaluation import (
    compute_forward_returns,
    compute_ic,
    compute_ir,
    compute_quantile_returns,
    evaluate_factor,
    evaluate_factors,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_price_df(
    n_stocks: int = 10, n_days: int = 20, seed: int = 42
) -> pd.DataFrame:
    """Synthetic price panel: n_stocks stocks x n_days days of random-walk close."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=n_days, freq="B")
    codes = [f"{100 + i:06d}" for i in range(n_stocks)]
    rows = []
    for code in codes:
        close = 100.0 * np.cumprod(1 + rng.normal(0, 0.01, n_days))
        for d, c in zip(dates, close):
            rows.append((d, code, float(c)))
    return pd.DataFrame(rows, columns=["date", "code", "close"])


def _monotonic_factor_df(price_df: pd.DataFrame) -> pd.DataFrame:
    """factor = 2 * fwd_ret_1d + 100 → spearman IC = 1 on every valid day."""
    fr = compute_forward_returns(price_df, windows=(1,))[1]
    factor_df = price_df[["date", "code"]].copy()
    factor_df["perfect"] = fr * 2 + 100.0
    factor_df["inverse"] = -fr * 2 + 100.0
    return factor_df


# ---------------------------------------------------------------------------
# Forward returns
# ---------------------------------------------------------------------------


class TestForwardReturns:
    def test_basic_window_1(self):
        """window=1: fwd_ret = next-day pct_change, last row NaN."""
        price_df = pd.DataFrame(
            {
                "date": pd.DatetimeIndex(
                    np.tile(pd.date_range("2024-01-01", periods=4, freq="B").values, 2)
                ),
                "code": ["A"] * 4 + ["B"] * 4,
                "close": [100.0, 110.0, 121.0, 133.1]
                + [100.0, 105.0, 110.25, 115.7625],
            }
        )
        result = compute_forward_returns(price_df, windows=(1,))
        assert set(result.keys()) == {1}
        sr = result[1]
        assert isinstance(sr, pd.Series)
        assert sr.name == "fwd_ret_1d"
        assert len(sr) == len(price_df)
        # stock A: day0 = (110-100)/100 = 0.10, day1 = 0.10, day2 = 0.10, day3 NaN
        np.testing.assert_allclose(
            sr.values[:4], [0.10, 0.10, 0.10, np.nan], equal_nan=True
        )
        np.testing.assert_allclose(
            sr.values[4:], [0.05, 0.05, 0.05, np.nan], equal_nan=True
        )

    def test_window_5(self):
        """window=5: pct_change(5).shift(-5), first row valid, last 5 NaN."""
        price_df = _make_price_df(n_stocks=2, n_days=8, seed=7)
        result = compute_forward_returns(price_df, windows=(5,))
        sr = result[5]
        by_code = (
            pd.DataFrame({"code": price_df["code"], "ret": sr.values})
            .groupby("code")["ret"]
            .apply(
                lambda s: (
                    np.isnan(s.iloc[-5:]).all() and not np.isnan(s.iloc[:-5]).any()
                )
            )
        )
        assert by_code.all()

    def test_aligned_to_input_order(self):
        """返回值与输入 price_df 逐行对齐（内部排序计算后映射回输入顺序）。"""
        price_df = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=3, freq="B").repeat(2),
                "code": ["B", "A", "B", "A", "B", "A"],
                "close": [100.0, 100.0, 110.0, 110.0, 121.0, 121.0],
            }
        )
        result = compute_forward_returns(price_df, windows=(1,))[1]
        # 每只股票 close 100→110→121；按输入行序逐行对齐
        np.testing.assert_allclose(
            result.values, [0.10, 0.10, 0.10, 0.10, np.nan, np.nan], equal_nan=True
        )

    def test_exclude_untradable(self):
        """exclude_untradable=True：limit_up/limit_down/is_suspended 行收益置 NaN。"""
        price_df = _make_price_df(n_stocks=3, n_days=6, seed=1)
        price_df["limit_up"] = False
        price_df["is_suspended"] = False
        price_df.loc[0, "limit_up"] = True
        price_df.loc[3, "is_suspended"] = True
        result = compute_forward_returns(
            price_df, windows=(1,), exclude_untradable=True
        )[1]
        assert np.isnan(result.iloc[0])
        assert np.isnan(result.iloc[3])
        assert not np.isnan(result.iloc[1])

    def test_default_no_exclude(self):
        """默认不剔除：limit_up 行收益仍有效。"""
        price_df = _make_price_df(n_stocks=2, n_days=5, seed=2)
        price_df["limit_up"] = False
        price_df.loc[0, "limit_up"] = True
        result = compute_forward_returns(price_df, windows=(1,))[1]
        assert not np.isnan(result.iloc[0])

    def test_missing_close_raises(self):
        price_df = pd.DataFrame({"date": ["2024-01-01"], "code": ["A"], "open": [1.0]})
        with pytest.raises(ValueError):
            compute_forward_returns(price_df, windows=(1,))


# ---------------------------------------------------------------------------
# IC
# ---------------------------------------------------------------------------


class TestIC:
    def test_perfect_positive_ic(self):
        """factor 是 fwd_ret 的严格单调函数 → 每日 spearman IC ≈ 1。"""
        price_df = _make_price_df(n_stocks=6, n_days=15, seed=3)
        factor_df = _monotonic_factor_df(price_df)
        fr = compute_forward_returns(price_df, windows=(1,))[1]
        ic = compute_ic(factor_df, "perfect", fr)
        assert isinstance(ic, pd.Series)
        assert len(ic) == 14  # 最后一天无 fwd_ret，跳过
        np.testing.assert_allclose(ic.values, 1.0, atol=1e-9)

    def test_perfect_negative_ic(self):
        price_df = _make_price_df(n_stocks=6, n_days=15, seed=3)
        factor_df = _monotonic_factor_df(price_df)
        fr = compute_forward_returns(price_df, windows=(1,))[1]
        ic = compute_ic(factor_df, "inverse", fr)
        np.testing.assert_allclose(ic.values, -1.0, atol=1e-9)

    def test_noisy_ic_around_zero(self):
        """随机因子（固定 seed）→ |IC 均值| 应很小。"""
        rng = np.random.default_rng(42)
        price_df = _make_price_df(n_stocks=10, n_days=30, seed=5)
        fr = compute_forward_returns(price_df, windows=(1,))[1]
        factor_df = price_df[["date", "code"]].copy()
        factor_df["noise"] = rng.normal(0, 1, len(price_df))
        ic = compute_ic(factor_df, "noise", fr)
        assert abs(ic.mean()) < 0.3

    def test_index_is_sorted_dates_and_name(self):
        price_df = _make_price_df(n_stocks=4, n_days=10, seed=6)
        factor_df = _monotonic_factor_df(price_df)
        fr = compute_forward_returns(price_df, windows=(1,))[1]
        ic = compute_ic(factor_df, "perfect", fr)
        assert ic.index.is_monotonic_increasing
        assert ic.name == "perfect_ic"

    def test_min_obs_skips_sparse_days(self):
        """截面有效样本 < min_obs 的日子不出现在 IC 时序。"""
        price_df = _make_price_df(n_stocks=3, n_days=6, seed=8)
        factor_df = _monotonic_factor_df(price_df)
        fr = compute_forward_returns(price_df, windows=(1,))[1]
        ic = compute_ic(factor_df, "perfect", fr, min_obs=3)
        assert len(ic) == 5  # 每日期面 3 样本 == min_obs，仍保留
        ic2 = compute_ic(factor_df, "perfect", fr, min_obs=4)
        assert len(ic2) == 0  # 3 样本 < 4，全部跳过

    def test_nan_in_factor_drops_pair(self):
        """factor 或 ret 为 NaN 的行从该日截面剔除，不影响其他样本。"""
        price_df = _make_price_df(n_stocks=4, n_days=6, seed=9)
        factor_df = _monotonic_factor_df(price_df)
        fr = compute_forward_returns(price_df, windows=(1,))[1]
        factor_df.loc[0, "perfect"] = np.nan  # 第一天第一只股票缺失
        ic = compute_ic(factor_df, "perfect", fr, min_obs=2)
        assert len(ic) == 5  # 6 天 - 最后一天无收益；第一天剩 3 样本 >= 2 仍保留

    def test_pearson_method(self):
        price_df = _make_price_df(n_stocks=6, n_days=10, seed=10)
        factor_df = _monotonic_factor_df(price_df)
        fr = compute_forward_returns(price_df, windows=(1,))[1]
        ic = compute_ic(factor_df, "perfect", fr, method="pearson")
        np.testing.assert_allclose(ic.values, 1.0, atol=1e-9)

    def test_missing_factor_column_raises(self):
        price_df = _make_price_df(n_stocks=3, n_days=5, seed=11)
        fr = compute_forward_returns(price_df, windows=(1,))[1]
        with pytest.raises(ValueError):
            compute_ic(price_df, "nope", fr)


# ---------------------------------------------------------------------------
# IR
# ---------------------------------------------------------------------------


class TestIR:
    def test_ir_is_mean_over_std(self):
        ic = pd.Series([0.1, 0.2, 0.3])
        expected = ic.mean() / ic.std(ddof=1)
        assert compute_ir(ic) == pytest.approx(expected)

    def test_ir_empty_is_nan(self):
        assert np.isnan(compute_ir(pd.Series([], dtype=float)))

    def test_ir_single_value_is_nan(self):
        assert np.isnan(compute_ir(pd.Series([0.1])))

    def test_ir_constant_ic_is_inf(self):
        """IC 恒定（std=0）→ IR 无定义但非缺失，返回 inf。"""
        assert compute_ir(pd.Series([0.1, 0.1, 0.1, 0.1])) == float("inf")


# ---------------------------------------------------------------------------
# Quantile returns
# ---------------------------------------------------------------------------


class TestQuantileReturns:
    def _monotonic_panel(
        self, n_stocks: int = 10, n_days: int = 6
    ) -> tuple[pd.DataFrame, pd.Series]:
        """因子值按股票单调，每日收益单调于因子 → 分层收益单调递增。"""
        dates = pd.date_range("2024-01-01", periods=n_days, freq="B")
        factor_df, price_df = [], []
        for i, code in enumerate([f"{100 + i:06d}" for i in range(n_stocks)]):
            level = float(i)
            close = 100.0
            for d in dates:
                factor_df.append((d, code, level))
                price_df.append((d, code, close))
                close *= 1 + (level + 1) / 1000.0
        factor_df = pd.DataFrame(factor_df, columns=["date", "code", "f"])
        price_df = pd.DataFrame(price_df, columns=["date", "code", "close"])
        fr = compute_forward_returns(price_df, windows=(1,))[1]
        return factor_df, fr

    def test_quantile_returns_monotonic(self):
        factor_df, fr = self._monotonic_panel()
        out = compute_quantile_returns(factor_df, "f", fr, n_quantiles=5)
        assert set(out.keys()) == {"quantile_returns", "summary", "long_short"}
        qr = out["quantile_returns"]
        assert list(qr.columns) == ["q1", "q2", "q3", "q4", "q5"]
        assert qr.index.is_monotonic_increasing
        means = [
            out["summary"].loc[out["summary"]["quantile"] == q, "mean_return"].iloc[0]
            for q in ["q1", "q2", "q3", "q4", "q5"]
        ]
        assert means == sorted(means)  # q1 < q2 < ... < q5
        assert means[0] < means[-1]

    def test_long_short_positive(self):
        factor_df, fr = self._monotonic_panel()
        out = compute_quantile_returns(factor_df, "f", fr, n_quantiles=5)
        ls = out["long_short"]
        assert list(ls.columns) == ["date", "ls_return"]
        # 最后一天无 forward return → NaN，跳过
        assert (ls["ls_return"].dropna() > 0).all()

    def test_rebalance_days_sampling(self):
        """rebalance_days=3：仅 dates[0], dates[3] 有层收益，其余 NaN。"""
        factor_df, fr = self._monotonic_panel(n_days=6)
        out = compute_quantile_returns(
            factor_df, "f", fr, n_quantiles=2, rebalance_days=3
        )
        qr = out["quantile_returns"]
        valid_days = qr.loc[qr["q1"].notna()].index
        expected = pd.Index(
            factor_df["date"].drop_duplicates().sort_values().iloc[[0, 3]]
        )
        pd.testing.assert_index_equal(valid_days, expected, check_names=False)

    def test_binary_quantiles(self):
        factor_df, fr = self._monotonic_panel(n_stocks=4)
        out = compute_quantile_returns(factor_df, "f", fr, n_quantiles=2)
        assert list(out["quantile_returns"].columns) == ["q1", "q2"]
        assert out["summary"]["quantile"].tolist() == ["q1", "q2"]

    def test_too_few_stocks_raises(self):
        """截面股票数 < n_quantiles 无法分层 → 抛 ValueError。"""
        factor_df, fr = self._monotonic_panel(n_stocks=3)
        with pytest.raises(ValueError):
            compute_quantile_returns(factor_df, "f", fr, n_quantiles=5)


# ---------------------------------------------------------------------------
# evaluate_factor / evaluate_factors
# ---------------------------------------------------------------------------


class TestEvaluateFactor:
    def test_full_structure(self):
        price_df = _make_price_df(n_stocks=8, n_days=25, seed=12)
        factor_df = _monotonic_factor_df(price_df)
        out = evaluate_factor(factor_df, "perfect", price_df, windows=(1, 5))
        assert set(out.keys()) == {"ic", "ic_series", "quantiles"}
        assert out["ic"]["window"].tolist() == [1, 5]
        for col in ["ic_mean", "ic_std", "ic_ir", "ic_positive_ratio"]:
            assert col in out["ic"].columns
        assert set(out["ic_series"].keys()) == {1, 5}
        assert set(out["quantiles"].keys()) == {1, 5}
        assert isinstance(out["quantiles"][1]["summary"], pd.DataFrame)

    def test_price_df_optional_uses_close(self):
        """price_df=None 时从 factor_df 的 close 列构造。"""
        price_df = _make_price_df(n_stocks=5, n_days=12, seed=13)
        factor_df = _monotonic_factor_df(price_df)
        factor_df["close"] = price_df["close"].values
        out = evaluate_factor(factor_df, "perfect", windows=(1,))
        assert out["ic"]["ic_mean"].iloc[0] == pytest.approx(1.0)

    def test_misaligned_price_df_raises(self):
        """factor_df 与 price_df 行序不一致 → 抛 ValueError（防静默错位）。"""
        price_df = _make_price_df(n_stocks=4, n_days=8, seed=16)
        factor_df = _monotonic_factor_df(price_df)
        shuffled = price_df.sample(frac=1, random_state=0).reset_index(drop=True)
        with pytest.raises(ValueError):
            evaluate_factor(factor_df, "perfect", shuffled)

    def test_window_beyond_data(self):
        """window 超出数据长度：ic 行保留 NaN，不抛错。"""
        price_df = _make_price_df(n_stocks=4, n_days=6, seed=17)
        factor_df = _monotonic_factor_df(price_df)
        out = evaluate_factor(factor_df, "perfect", price_df, windows=(999,))
        assert out["ic"]["window"].tolist() == [999]
        assert np.isnan(out["ic"]["ic_mean"].iloc[0])
        assert out["quantiles"][999] is None

    def test_missing_close_raises(self):
        price_df = _make_price_df(n_stocks=4, n_days=8, seed=14)
        factor_df = _monotonic_factor_df(price_df)  # 无 close 列
        with pytest.raises(ValueError):
            evaluate_factor(factor_df, "perfect")


class TestEvaluateFactors:
    def test_batch_table_structure(self):
        price_df = _make_price_df(n_stocks=8, n_days=25, seed=15)
        factor_df = _monotonic_factor_df(price_df)
        factor_df["noise"] = np.random.default_rng(1).normal(0, 1, len(factor_df))
        result = evaluate_factors(
            factor_df, ["perfect", "inverse", "noise"], price_df, windows=(1, 5)
        )
        assert list(result.columns) == [
            "factor",
            "window",
            "ic_mean",
            "ic_std",
            "ic_ir",
            "ic_positive_ratio",
            "ls_mean",
            "ls_ir",
        ]
        # 每因子每窗口一行，共 3*2=6 行；按因子顺序 + window 升序
        assert len(result) == 6
        assert (
            result["factor"].tolist()
            == ["perfect"] * 2 + ["inverse"] * 2 + ["noise"] * 2
        )
        assert result["window"].tolist() == [1, 5, 1, 5, 1, 5]
        # 值正确：perfect 因子 ic_mean≈1，inverse≈-1
        assert result.loc[0, "ic_mean"] == pytest.approx(1.0)
        assert result.loc[2, "ic_mean"] == pytest.approx(-1.0)
        # long-short 价差方向正确
        assert result.loc[0, "ls_mean"] > 0
        assert result.loc[2, "ls_mean"] < 0

    def test_window_beyond_data_yields_nan_row(self):
        """批量评估中 window 超出数据长度：该行全 NaN，不抛错、表结构稳定。"""
        price_df = _make_price_df(n_stocks=8, n_days=6, seed=18)
        factor_df = _monotonic_factor_df(price_df)
        result = evaluate_factors(factor_df, ["perfect"], price_df, windows=(1, 999))
        assert len(result) == 2
        assert result["window"].tolist() == [1, 999]
        assert np.isnan(result.loc[1, "ic_mean"])
        assert np.isnan(result.loc[1, "ls_mean"])
