"""tests/factors/test_synth.py — Phase C 合成信号纯函数单测（Task 1-3 共用文件）。"""
import numpy as np
import pandas as pd
import pytest

from factors.ops.synth import combine_factor_scores

# ---------------------------------------------------------------------------
# Task 1: combine_factor_scores
# ---------------------------------------------------------------------------


def test_combine_scores_equal_weight_daily_cross_section():
    df = pd.DataFrame(
        {
            "date": ["2024-01-02"] * 3 + ["2024-01-03"] * 3,
            "code": ["A", "B", "C"] * 2,
            "f1": [1.0, 2.0, 3.0, 3.0, 1.0, 2.0],
            "f2": [3.0, 1.0, 2.0, 1.0, 3.0, 2.0],
        }
    )
    score = combine_factor_scores(df, ["f1", "f2"])
    # 01-02: f1 rank=[1/3,2/3,1], f2 rank=[1,1/3,2/3] → avg=[2/3,1/2,5/6]
    # 01-03: f1 rank=[2/3,1/3,1]? 不：f1=[3,1,2] → rank=[1,1/3,2/3]
    #        f2=[1,3,2] → rank=[1/3,1,2/3] → avg=[2/3,2/3,2/3]
    expected = pd.Series(
        [2 / 3, 1 / 2, 5 / 6, 2 / 3, 2 / 3, 2 / 3],
        index=df.index,
        name="synth_score",
    )
    pd.testing.assert_series_equal(score, expected)


def test_combine_scores_with_symbolic_weights():
    df = pd.DataFrame(
        {
            "date": ["2024-01-02"] * 3,
            "code": ["A", "B", "C"],
            "f1": [1.0, 2.0, 3.0],   # rank=[1/3,2/3,1]
            "f2": [3.0, 1.0, 2.0],   # rank=[1,1/3,2/3]
        }
    )
    # f1 权重 +2（正向），f2 权重 -1（反向 → 用 1-rank）
    score = combine_factor_scores(df, ["f1", "f2"], weights={"f1": 2.0, "f2": -1.0})
    # eff_f1=[1/3,2/3,1], eff_f2=[0,2/3,1/3]（1-rank）
    # num = 2*eff_f1 + 1*eff_f2 = [2/3, 2, 7/3]
    # den = 3 → score = [2/9, 2/3, 7/9]
    expected = pd.Series([2 / 9, 2 / 3, 7 / 9], index=df.index, name="synth_score")
    pd.testing.assert_series_equal(score, expected)


def test_combine_scores_all_nan_row_is_nan():
    df = pd.DataFrame(
        {
            "date": ["2024-01-02", "2024-01-02"],
            "code": ["A", "B"],
            "f1": [1.0, np.nan],
            "f2": [2.0, np.nan],
        }
    )
    score = combine_factor_scores(df, ["f1", "f2"])
    assert np.isnan(score.iloc[1])
    assert not np.isnan(score.iloc[0])


def test_combine_scores_partial_nan_row_reweights():
    df = pd.DataFrame(
        {
            "date": ["2024-01-02", "2024-01-02"],
            "code": ["A", "B"],
            "f1": [1.0, 2.0],   # rank=[0.5,1]
            "f2": [np.nan, 1.0],  # B 行有效
        }
    )
    score = combine_factor_scores(df, ["f1", "f2"])
    # A 行只有 f1 有效 → 分母=1 → 0.5
    # B 行两因子有效 → avg(1, 1)=1
    expected = pd.Series([0.5, 1.0], index=df.index, name="synth_score")
    pd.testing.assert_series_equal(score, expected)


def test_combine_scores_empty_factors_raises():
    df = pd.DataFrame({"date": ["2024-01-02"], "code": ["A"], "f1": [1.0]})
    with pytest.raises(ValueError):
        combine_factor_scores(df, [])


def test_combine_scores_missing_column_raises():
    df = pd.DataFrame({"date": ["2024-01-02"], "code": ["A"], "f1": [1.0]})
    with pytest.raises(ValueError):
        combine_factor_scores(df, ["f1", "f_missing"])
