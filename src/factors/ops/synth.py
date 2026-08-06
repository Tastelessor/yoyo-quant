"""factors/ops/synth.py — Phase C 合成信号纯函数。

把多个因子（通常是 Phase A 去冗余后的代表因子）合成单一信号：
每日截面 rank 归一化 → 带符号权重加权平均 → 综合得分。
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def combine_factor_scores(
    factor_df: pd.DataFrame,
    factors: list[str],
    weights: dict[str, float] | None = None,
) -> pd.Series:
    """每日截面 rank 归一化 → 加权平均 → 综合得分。

    Parameters
    ----------
    factor_df : DataFrame
        宽表，含 ``date``、``code`` 与 ``factors`` 列。
    factors : list[str]
        参与合成的因子列名。
    weights : dict[str, float] | None
        因子权重（带符号：负权重 = 反向因子，内部用 1-rank）。
        None = 等权。

    Returns
    -------
    Series
        与 ``factor_df`` 行对齐的综合得分，name="synth_score"；
        某行全部因子为 NaN 时为 NaN。
    """
    if not factors:
        raise ValueError("factors 不能为空")
    missing = [f for f in factors if f not in factor_df.columns]
    if missing:
        raise ValueError(f"factor_df 缺少列: {missing}")
    if weights is None:
        weights = {f: 1.0 for f in factors}

    # 每日截面 rank（pct 0-1）
    ranks = pd.DataFrame(
        {f: factor_df.groupby("date")[f].rank(pct=True) for f in factors}
    )
    w = np.array([weights.get(f, 0.0) for f in factors], dtype=float)
    dirs = np.sign(w)
    mags = np.abs(w)

    eff = ranks.to_numpy(dtype=float)
    for i, f in enumerate(factors):
        if dirs[i] < 0:
            eff[:, i] = 1.0 - eff[:, i]

    valid = ~np.isnan(eff)
    num = np.nansum(eff * mags[None, :], axis=1)
    den = np.where(valid, mags[None, :], 0.0).sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        score = np.where(den > 0, num / np.where(den > 0, den, 1.0), np.nan)
    return pd.Series(score, index=factor_df.index, name="synth_score")


def scores_to_signals(
    factor_df: pd.DataFrame,
    score: pd.Series,
    *,
    rebalance: int = 20,
    top_n: int = 10,
    bottom_n: int = 5,
) -> pd.DataFrame:
    """综合得分 → (date, code, signal, confidence)。

    每个再平衡日：截面得分排序 → top_n 买入（signal=1，confidence=得分）
    → bottom_n 卖出（signal=-1，confidence=0.5）；持仓延续到下一再平衡日；
    前一期持仓未再买入的股票在再平衡日卖出。得分 NaN 的股票不入选。

    Parameters
    ----------
    factor_df : DataFrame
        含 ``date``、``code`` 列（与 score 行对齐）。
    score : Series
        综合得分（与 factor_df 行对齐）。
    rebalance : int
        再平衡周期（交易日）。
    top_n / bottom_n : int
        每期买入/卖出股票数。二者不能同时为 0。

    Returns
    -------
    DataFrame
        列：date, code, signal（int 1/-1/0）, confidence（float）。
    """
    if top_n <= 0 and bottom_n <= 0:
        raise ValueError("top_n 与 bottom_n 至少一个 > 0")
    df = factor_df[["date", "code"]].copy()
    df["__score__"] = score.to_numpy(dtype=float)
    dates = sorted(df["date"].unique())

    signal = pd.Series(0, index=df.index, dtype=int)
    confidence = pd.Series(0.0, index=df.index)
    prev_holdings: set[str] = set()

    for i in range(0, len(dates), rebalance):
        rb_date = dates[i]
        nxt = min(i + rebalance, len(dates))
        hold_dates = dates[i:nxt]

        day = df[df["date"] == rb_date].dropna(subset=["__score__"])
        day = day.sort_values("__score__", ascending=False)
        buys = set(day.head(top_n)["code"]) if top_n > 0 else set()
        sells = set(day.tail(bottom_n)["code"]) if bottom_n > 0 else set()
        score_by_code = dict(zip(day["code"], day["__score__"]))

        for hd in hold_dates:
            h_mask = df["date"] == hd
            for c in buys:
                m = h_mask & (df["code"] == c)
                signal[m] = 1
                confidence[m] = float(score_by_code.get(c, 0.5))
            for c in sells - buys:
                m = h_mask & (df["code"] == c)
                signal[m] = -1
                confidence[m] = 0.5
        # 退出持仓：上一期买入但本期未买入 → 在再平衡日卖出
        for c in prev_holdings - buys:
            m = (df["date"] == rb_date) & (df["code"] == c)
            signal[m] = -1
            confidence[m] = 0.5
        prev_holdings = buys

    return pd.DataFrame(
        {
            "date": df["date"],
            "code": df["code"],
            "signal": signal,
            "confidence": confidence,
        }
    )
