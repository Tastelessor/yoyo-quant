"""因子相关性分析（Phase A）：滚动截面 rank 相关矩阵 + 聚类去冗余。

纯函数、无状态，对齐 ``factors.ops.evaluation`` 的契约风格。
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _require_cols(df: pd.DataFrame, cols: tuple[str, ...], who: str) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"{who}: 缺少列 {missing}")


def compute_corr_matrix(
    factor_df: pd.DataFrame,
    factors: list[str],
    *,
    window: int = 60,
    method: str = "spearman",
    agg: str = "mean",
    min_obs: int = 20,
) -> pd.DataFrame:
    """计算因子两两的滚动截面秩相关矩阵。

    Parameters
    ----------
    factor_df : DataFrame
        宽表，含 ``date`` / ``code`` 与每个因子一列，任意行序。
    factors : list[str]
        参与分析的因子列名。
    window : int
        只取最近 ``window`` 个交易日（按 date 去重排序取尾部）。
    method : str
        相关性方法，透传给 ``Series.corr``，默认 ``spearman``。
    agg : str
        每日相关序列的聚合方式：``mean`` / ``median``。
    min_obs : int
        单日截面有效样本数下限，低于该值的日期跳过。

    Returns
    -------
    DataFrame
        对称矩阵，index=columns=factors；对角线 1.0；数据不足的因子对为 NaN。
    """
    if not isinstance(window, int) or window < 1:
        raise ValueError(f"window 必须为正整数，收到 {window!r}")
    if agg not in {"mean", "median"}:
        raise ValueError(f"agg 必须为 'mean' 或 'median'，收到 {agg!r}")
    cols = ("date", "code") + tuple(factors)
    _require_cols(factor_df, cols, "compute_corr_matrix")

    dates = sorted(factor_df["date"].unique())[-window:]
    sub = factor_df[factor_df["date"].isin(dates)]

    mat = pd.DataFrame(index=factors, columns=factors, dtype=np.float64)
    for i, f1 in enumerate(factors):
        for f2 in factors[i + 1 :]:
            daily: list[float] = []
            for _d, grp in sub.groupby("date"):
                pair = grp[[f1, f2]].dropna()
                if len(pair) < min_obs:
                    continue
                r = pair[f1].corr(pair[f2], method=method)
                if not np.isnan(r):
                    daily.append(float(r))
            if daily:
                if agg == "mean":
                    val = float(np.mean(daily))
                else:
                    val = float(np.median(daily))
                mat.loc[f1, f2] = mat.loc[f2, f1] = val
    np.fill_diagonal(mat.to_numpy(), 1.0)
    return mat
