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
