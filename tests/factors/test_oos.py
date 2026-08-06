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
# Task 3: bootstrap_t_distribution（路径②：AR(1) 残差打乱 + H0 重建）
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
    # 带噪声的强趋势：原尾部 t 巨大，但 H0 重建（残差中心化、均值归 0）
    # 后零分布应显著小于原 t —— 验证"去均值"消除均值抬升。
    rng = np.random.default_rng(0)
    ic = pd.Series(np.arange(60) / 10.0 + rng.normal(0, 0.5, 60))
    null = bootstrap_t_distribution(ic, 100, 20, seed=3)
    w = ic.iloc[-20:]
    t_orig = w.mean() / w.std(ddof=1) * np.sqrt(len(w))
    assert t_orig > 5.0  # 趋势确实显著
    assert np.quantile(np.abs(null), 0.99) < t_orig


def test_bootstrap_null_h0_zero_mean():
    # 路径②核心语义：正均值白噪声（均值 2）原 t 巨大，但残差中心化 +
    # 重建均值归 0 后，零分布应围绕 0（|t| 中位数小、q95 远小于原 t）。
    rng = np.random.default_rng(1)
    ic = pd.Series(rng.normal(2.0, 0.3, 120))
    null = bootstrap_t_distribution(ic, 200, 60, seed=5)
    w = ic.iloc[-60:]
    t_orig = w.mean() / w.std(ddof=1) * np.sqrt(len(w))
    assert t_orig > 5.0  # 均值漂移显著
    assert np.quantile(np.abs(null), 0.5) < 1.0  # 零分布中心化
    assert np.quantile(np.abs(null), 0.95) < t_orig


def test_bootstrap_null_ar1_phi_sensitive():
    # 零分布应反映 IC 的 AR(1) 结构：强正自相关（φ=0.9）重建序列的
    # 尾部窗口均值漂移被 φ 放大 → 零分布更肥尾 → q95 更高（自相关制造
    # 虚假显著性的幅度更大，门槛理应更严）。
    rng = np.random.default_rng(2)
    n = 240
    wn = rng.normal(0, 1, n)
    ar = np.empty(n)
    ar[0] = wn[0]
    for t in range(1, n):
        ar[t] = 0.9 * ar[t - 1] + wn[t]
    null_wn = bootstrap_t_distribution(pd.Series(wn), 100, 60, seed=9)
    null_ar = bootstrap_t_distribution(pd.Series(ar), 100, 60, seed=9)
    assert np.quantile(np.abs(null_ar), 0.95) > np.quantile(np.abs(null_wn), 0.95)


# ---------------------------------------------------------------------------
# Task 3 review fix: 非平凡零分布 + 短序列边界（防止退化实现静默通过）
# ---------------------------------------------------------------------------


def test_bootstrap_null_nontrivial_white_noise():
    # 防退化：恒返回常数（如全零 / 只打乱一次复用）时,取值唯一性与
    # q95 区间双断言必失败。注：numpy std() 对常数数组因浮点累加误差
    # 可能返回 ~1e-16,故用 np.unique 判取值数而非 std>0。
    rng = np.random.default_rng(0)
    ic = pd.Series(rng.normal(0, 1, 120))
    null = bootstrap_t_distribution(ic, 50, 20, seed=11)
    assert np.unique(null).size > 1  # 掐死全零 / 常数复用：零分布必须有内部波动
    q95 = np.quantile(null, 0.95)
    assert 0.5 < q95 < 5.0  # 白噪声 t 的 95 分位应落在合理区间（0 与 ∞ 都被排除）


def test_bootstrap_null_short_series_all_nan():
    # 短序列边界：有效样本数 < t_window 时返回全 NaN
    # （对齐 compute_test_period_stats 的 NaN 风格）
    ic = pd.Series([0.1, 0.2, 0.3, 0.4, 0.5])  # 仅 5 个有效样本
    out = bootstrap_t_distribution(ic, 10, 20, seed=1)
    assert len(out) == 10
    assert np.all(np.isnan(out))
