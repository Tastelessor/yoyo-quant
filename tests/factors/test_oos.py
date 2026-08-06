"""tests/factors/test_oos.py — Phase B 纯函数单测（Task 1-3 共用文件）。"""
# Task 1 只交付 generate_oos_windows；Task 2 加回 select_top_factors /
# compute_test_period_stats（及 numpy）；Task 3 最后追加
# bootstrap_t_distribution，至此 import 清单完整（四个函数）。
import numpy as np
import pandas as pd

from factors.ops.oos import (
    bootstrap_t_distribution,
    compute_test_period_stats,
    generate_oos_windows,
    select_top_factors,
)

# ---------------------------------------------------------------------------
# Task 1: generate_oos_windows
# ---------------------------------------------------------------------------


def test_generate_oos_windows_basic():
    dates = pd.bdate_range("2024-01-01", periods=26 * 20)  # ~26 个月
    windows = generate_oos_windows(dates, train_months=12, test_months=1)
    assert len(windows) > 0
    for train, test in windows:
        assert len(train) > 0 and len(test) > 0
        assert train[-1] < test[0]  # 严格不相交且 train 紧贴 test
        assert set(train) <= set(dates) and set(test) <= set(dates)


def test_generate_oos_windows_train_test_disjoint_and_aligned():
    dates = pd.bdate_range("2024-01-01", periods=600)
    windows = generate_oos_windows(dates, train_months=12, test_months=1)
    for train, test in windows:
        assert len(train.intersection(test)) == 0
        # test 起点是 train 终点之后的第一个实际交易日
        assert test[0] == dates[dates > train[-1]][0]


def test_generate_oos_windows_too_short_returns_empty():
    dates = pd.bdate_range("2024-01-01", periods=200)  # ~9 个月 < 13
    assert generate_oos_windows(dates, train_months=12, test_months=1) == []


def test_generate_oos_windows_empty_returns_empty():
    assert generate_oos_windows(pd.DatetimeIndex([])) == []


# ---------------------------------------------------------------------------
# Task 2: select_top_factors + compute_test_period_stats
# ---------------------------------------------------------------------------


def test_select_top_factors_basic():
    stats = pd.DataFrame({"factor": ["a", "b", "c"], "t_stat": [1.5, -3.2, 2.1]})
    assert select_top_factors(stats, top_k=2) == ["b", "c"]  # |t| 降序


def test_select_top_factors_min_t():
    stats = pd.DataFrame({"factor": ["a", "b"], "t_stat": [0.8, 3.0]})
    assert select_top_factors(stats, top_k=5, min_t=1.0) == ["b"]


def test_select_top_factors_nan_last():
    stats = pd.DataFrame({"factor": ["a", "b"], "t_stat": [2.0, np.nan]})
    assert select_top_factors(stats, top_k=5) == ["a"]


def test_select_top_factors_empty():
    assert select_top_factors(pd.DataFrame({"factor": [], "t_stat": []}), 5) == []


def test_compute_test_period_stats_normal():
    ic = pd.Series(np.linspace(0.01, 0.05, 20))
    st = compute_test_period_stats(ic)
    assert st["ic_n"] == 20
    assert st["ic_t"] > 2 and st["sig"] is True


def test_compute_test_period_stats_insufficient():
    ic = pd.Series([0.01, 0.02, 0.03])
    st = compute_test_period_stats(ic, min_days=5)
    assert np.isnan(st["ic_t"]) and st["sig"] is False


def test_compute_test_period_stats_constant():
    ic = pd.Series([0.02] * 10)
    st = compute_test_period_stats(ic)
    assert st["ic_t"] == float("inf") and st["sig"] is True


# ---------------------------------------------------------------------------
# Task 3: bootstrap_t_distribution
# ---------------------------------------------------------------------------


def test_bootstrap_t_distribution_deterministic_and_length():
    rng = np.random.default_rng(0)
    ic = pd.Series(rng.normal(0, 1, 120))
    a = bootstrap_t_distribution(ic, 50, 20, seed=7)
    b = bootstrap_t_distribution(ic, 50, 20, seed=7)
    assert np.array_equal(a, b)
    assert len(a) == 50
    assert np.all(np.isfinite(a))
    # 白噪声打乱后 |t| 的中位数应明显小于 2（非显著）
    assert np.quantile(np.abs(a), 0.5) < 2.0


def test_bootstrap_null_smaller_than_original_trend_t():
    ic = pd.Series(np.arange(60) / 10.0)  # 强趋势序列：原尾部窗口 t 巨大
    null = bootstrap_t_distribution(ic, 100, 20, seed=3)
    w = ic.iloc[-20:]
    t_orig = w.mean() / w.std(ddof=1) * np.sqrt(len(w))
    assert t_orig > np.quantile(np.abs(null), 0.99)
