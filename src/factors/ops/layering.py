"""factors/ops/layering.py — 分层标签纯函数（size × liquidity）。

每日截面三分位 → 每只股票当日的 size / liquidity 层标签。
分层是元数据（每股票每天一个标签），不是独立股票池。

输入为 ``fetch_fundamentals`` 输出的基本面面板（date / code /
circ_mv / turnover_rate），与 ``factors.ops.evaluation`` 一样是
纯函数、无状态、输出与输入逐行对齐。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

_SIZE_LABELS = ["small", "mid", "large"]
_LIQ_LABELS = ["low", "mid", "high"]


def _require_cols(df: pd.DataFrame, cols: tuple[str, ...], who: str) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"{who}: 缺少列 {missing}")


def _tercile_labels(series: pd.Series, labels: list[str], bins: int = 3) -> pd.Series:
    """单列每日截面分位 → 层标签（对应值 NaN → NaN）。

    优先 ``pd.qcut``；因有效样本过少 / 取值退化抛 ValueError 时，
    用 rank 分位降级（等距 1/bins 断点）兜底，仍产出 bins 档标签。
    """
    out = pd.Series(np.nan, index=series.index, dtype=object)
    valid = series.dropna()
    if len(valid) == 0:
        return out
    try:
        buckets = pd.qcut(valid, bins, labels=labels, duplicates="drop")
    except ValueError:
        # 有效样本过少/取值退化：用 rank 分位降级（等距 1/bins 断点）
        r = valid.rank(pct=True)
        edges = np.linspace(0.0, 1.0, bins + 1)
        buckets = pd.cut(r, edges, labels=labels, include_lowest=True)
    out.loc[valid.index] = buckets
    return out


def compute_size_liquidity_layers(
    basic_df: pd.DataFrame,
    *,
    bins: int = 3,
) -> pd.DataFrame:
    """每日截面三分位 → size/liquidity 层标签。

    Parameters
    ----------
    basic_df : DataFrame
        含 ``date`` / ``code`` / ``circ_mv``（流通市值）/ ``turnover_rate``
        （换手率）。
    bins : int
        分位数桶数，默认 3（tercile）。仅支持 2/3。

    Returns
    -------
    DataFrame
        与 ``basic_df`` 行对齐，列：date, code, size_layer, liq_layer；
        size_layer ∈ {small, mid, large}、liq_layer ∈ {low, mid, high}；
        对应维度值为 NaN 时该维层为 NaN。

    Notes
    -----
    分层按**每日截面**（``groupby("date")`` 分组后各组独立三分位），
    不是全局分位——日期间取值整体平移不影响当日层归属；分组结果经
    ``transform`` 映射回原行序，保证与 ``basic_df`` 逐行对齐。
    """
    if bins not in (2, 3):
        raise ValueError(f"bins 仅支持 2/3，收到 {bins!r}")
    _require_cols(
        basic_df,
        ("date", "code", "circ_mv", "turnover_rate"),
        "compute_size_liquidity_layers",
    )
    size_labels = _SIZE_LABELS[:bins] if bins == 3 else ["small", "large"]
    liq_labels = _LIQ_LABELS[:bins] if bins == 3 else ["low", "high"]
    result = basic_df[["date", "code"]].copy()
    # 每日截面：先按 date 分组，各组独立三分位，再映射回原行序
    result["size_layer"] = basic_df.groupby("date", sort=False)["circ_mv"].transform(
        lambda s: _tercile_labels(s, size_labels, bins=bins)
    )
    result["liq_layer"] = basic_df.groupby("date", sort=False)[
        "turnover_rate"
    ].transform(lambda s: _tercile_labels(s, liq_labels, bins=bins))
    return result
