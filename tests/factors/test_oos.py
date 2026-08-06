"""tests/factors/test_oos.py — Phase B 纯函数单测（Task 1-3 共用文件）。"""
# Task 1 只交付 generate_oos_windows。Task 2-3 追加时在此处加回
# select_top_factors / bootstrap_t_distribution / compute_test_period_stats
# 的 import（及其测试所需的 numpy/pytest），提前 import 会导致收集期 ImportError。
import pandas as pd

from factors.ops.oos import generate_oos_windows

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
