"""tests/factors/test_synth.py — Phase C 合成信号纯函数单测（Task 1-3 共用文件）。"""
import numpy as np
import pandas as pd
import pytest

from factors.ops.synth import (
    combine_factor_scores,
    compute_ic_weights,
    scores_to_signals,
)

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

# ---------------------------------------------------------------------------
# Task 2: scores_to_signals
# ---------------------------------------------------------------------------


def test_scores_to_signals_basic_rebalance_rotation():
    dates = pd.bdate_range("2024-01-02", periods=6)
    rows = []
    for d in dates:
        for c in ["A", "B", "C"]:
            rows.append({"date": d, "code": c})
    df = pd.DataFrame(rows)
    # 截面得分：A 最高、C 最低（每个交易日相同）
    score = pd.Series([0.9, 0.5, 0.1] * 6, index=df.index)
    out = scores_to_signals(df, score, rebalance=3, top_n=1, bottom_n=1)
    assert list(out.columns) == ["date", "code", "signal", "confidence"]
    assert out["signal"].dtype == int
    assert out["confidence"].dtype == float
    # 第一期（第 0-2 天，9 行）：买入 A（signal=1, conf=0.9），卖出 C（signal=-1, 0.5）
    first = out.iloc[:9]
    a_signals = first[first["code"] == "A"]["signal"].tolist()
    assert a_signals == [1, 1, 1]
    c_signals = first[first["code"] == "C"]["signal"].tolist()
    assert c_signals == [-1, -1, -1]
    b_signals = first[first["code"] == "B"]["signal"].tolist()
    assert b_signals == [0, 0, 0]
    a_conf = first[first["code"] == "A"]["confidence"].tolist()
    assert all(abs(v - 0.9) < 1e-9 for v in a_conf)


def test_scores_to_signals_nan_scores_not_selected():
    df = pd.DataFrame(
        {
            "date": ["2024-01-02"] * 3,
            "code": ["A", "B", "C"],
        }
    )
    score = pd.Series([0.9, np.nan, 0.1], index=df.index)
    out = scores_to_signals(df, score, rebalance=1, top_n=1, bottom_n=1)
    assert out.loc[out["code"] == "A", "signal"].iloc[0] == 1
    assert out.loc[out["code"] == "B", "signal"].iloc[0] == 0  # NaN 不入选
    assert out.loc[out["code"] == "C", "signal"].iloc[0] == -1


def test_scores_to_signals_top_bottom_zero_raises():
    df = pd.DataFrame({"date": ["2024-01-02"], "code": ["A"]})
    score = pd.Series([0.5], index=df.index)
    with pytest.raises(ValueError):
        scores_to_signals(df, score, rebalance=1, top_n=0, bottom_n=0)


def test_scores_to_signals_prev_holding_exits_on_rebalance():
    # 两期 buys 不同：第一期 A 最高 → 买入 A；第二期得分互换 → B 最高买入、
    # A 未再买入且本期非最低 → 仅由「退出持仓」分支处理（再平衡日卖出）
    dates = pd.bdate_range("2024-01-02", periods=4)
    rows = []
    for d in dates:
        for c in ["A", "B", "C"]:
            rows.append({"date": d, "code": c})
    df = pd.DataFrame(rows)
    score = pd.Series(
        [0.9, 0.5, 0.1] * 2 + [0.5, 0.9, 0.1] * 2, index=df.index
    )
    out = scores_to_signals(df, score, rebalance=2, top_n=1, bottom_n=1)
    # 第一期（第 0-1 天）：A 买入（signal=1, conf=0.9）、C 卖出
    p1 = out.iloc[:6]
    assert p1[p1["code"] == "A"]["signal"].tolist() == [1, 1]
    assert p1[p1["code"] == "C"]["signal"].tolist() == [-1, -1]
    # 再平衡日（第 2 天）：B 买入；A 退出持仓 → signal=-1, confidence=0.5
    rb = out[out["date"] == dates[2]]
    a = rb[rb["code"] == "A"].iloc[0]
    assert a["signal"] == -1
    assert abs(a["confidence"] - 0.5) < 1e-9
    b = rb[rb["code"] == "B"].iloc[0]
    assert b["signal"] == 1
    assert abs(b["confidence"] - 0.9) < 1e-9
    # 退出后下一日 A 恢复中性（不再是持仓）
    assert out[(out["date"] == dates[3]) & (out["code"] == "A")]["signal"].iloc[0] == 0

# ---------------------------------------------------------------------------
# Task 3: compute_ic_weights
# ---------------------------------------------------------------------------


def test_ic_weights_from_state_mean_ic_with_sign():
    dates = pd.bdate_range("2024-01-01", periods=10)
    rows = []
    for d in dates:
        rows.append(
            {
                "date": d,
                "factor": "f_positive",
                "fwd_window": 5,
                "ic": 0.03,
                "rolling_ic": 0.03,
                "rolling_ir": 0.5,
                "t_stat": 3.0,
                "state": "active",
                "sustain_days": 10,
            }
        )
        rows.append(
            {
                "date": d,
                "factor": "f_negative",
                "fwd_window": 5,
                "ic": -0.01,
                "rolling_ic": -0.01,
                "rolling_ir": -0.2,
                "t_stat": -1.5,
                "state": "active",
                "sustain_days": 10,
            }
        )
    state = pd.DataFrame(rows)
    w = compute_ic_weights(
        state, ["f_positive", "f_negative"], as_of=pd.Timestamp("2024-01-10")
    )
    # mean(ic) = [0.03, -0.01] → w = [0.03/0.04, -0.01/0.04] = [0.75, -0.25]
    assert abs(w["f_positive"] - 0.75) < 1e-9
    assert abs(w["f_negative"] + 0.25) < 1e-9


def test_ic_weights_lookback_trims_and_na_skips():
    dates = pd.bdate_range("2024-01-01", periods=70)
    rows = []
    for i, d in enumerate(dates):
        rows.append(
            {
                "date": d,
                "factor": "f",
                "fwd_window": 5,
                "ic": 0.02 if i >= 10 else np.nan,  # 前 10 天 NaN
                "rolling_ic": 0.02,
                "rolling_ir": 0.4,
                "t_stat": 2.0,
                "state": "active",
                "sustain_days": 10,
            }
        )
    state = pd.DataFrame(rows)
    w = compute_ic_weights(state, ["f"], as_of=pd.Timestamp("2024-03-01"), lookback=30)
    # 有效 ic 共 60 天，tail(30) → 30 个 0.02 → mean=0.02 → 单因子 w=1.0
    assert abs(w["f"] - 1.0) < 1e-9


def test_ic_weights_all_invalid_falls_back_to_equal():
    state = pd.DataFrame(
        {
            "date": [pd.Timestamp("2024-01-02")] * 2,
            "factor": ["f1", "f2"],
            "fwd_window": [5, 5],
            "ic": [np.nan, np.nan],
            "rolling_ic": [np.nan, np.nan],
            "rolling_ir": [np.nan, np.nan],
            "t_stat": [np.nan, np.nan],
            "state": ["active", "active"],
            "sustain_days": [1, 1],
        }
    )
    w = compute_ic_weights(state, ["f1", "f2"], as_of=pd.Timestamp("2024-01-02"))
    assert w == {"f1": 0.5, "f2": 0.5}
